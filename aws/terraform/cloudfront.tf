# ---------------------------------------------------------------------------
# CloudFront — CDN for the React SPA frontend with SPA routing support
# ---------------------------------------------------------------------------

# Origin Access Control for S3 (replaces the deprecated OAI)
resource "aws_cloudfront_origin_access_control" "frontend" {
  name                              = "${local.name_prefix}-frontend-oac"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# S3 bucket policy — allow CloudFront OAC to read objects
data "aws_iam_policy_document" "frontend_oac" {
  statement {
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.frontend.arn}/*"]

    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.frontend.arn]
    }
  }
}

resource "aws_s3_bucket_policy" "frontend_oac" {
  bucket = aws_s3_bucket.frontend.id
  policy = data.aws_iam_policy_document.frontend_oac.json
}

# CloudFront Function for SPA routing
# The frontend uses BrowserRouter (HTML5 history API) — all non-file paths
# must serve index.html so React Router can handle them client-side.
resource "aws_cloudfront_function" "spa_routing" {
  name    = "${local.name_prefix}-spa-routing"
  runtime = "cloudfront-js-2.0"
  code    = <<-EOF
    function handler(event) {
      var request = event.request;
      var uri = request.uri;

      // If the URI contains a file extension, serve it as-is
      if (uri.includes('.')) {
        return request;
      }

      // Otherwise, serve index.html for SPA client-side routing
      request.uri = '/index.html';
      return request;
    }
  EOF
}

# CloudFront Function for same-origin API routing. Requests sent by the SPA to
# /api/* stay on the HTTPS CloudFront domain, then the prefix is removed before
# forwarding to the ALB.
resource "aws_cloudfront_function" "api_routing" {
  name    = "${local.name_prefix}-api-routing"
  runtime = "cloudfront-js-2.0"
  code    = <<-EOF
    function handler(event) {
      var request = event.request;

      if (request.uri === '/api') {
        request.uri = '/';
      } else if (request.uri.indexOf('/api/') === 0) {
        request.uri = request.uri.slice(4);
      }

      return request;
    }
  EOF
}

# --- CloudFront Distribution ---

resource "aws_cloudfront_distribution" "frontend" {
  enabled             = true
  default_root_object = "index.html"
  is_ipv6_enabled     = true
  price_class         = "PriceClass_100" # US, Canada, Europe — lower cost
  comment             = "${local.name_prefix} frontend"

  # Only set aliases if a domain is configured
  aliases = var.frontend_domain != "" ? [var.frontend_domain] : []

  origin {
    domain_name              = aws_s3_bucket.frontend.bucket_regional_domain_name
    origin_id                = "S3-${aws_s3_bucket.frontend.id}"
    origin_access_control_id = aws_cloudfront_origin_access_control.frontend.id
  }

  origin {
    domain_name = var.api_domain != "" ? var.api_domain : aws_lb.main.dns_name
    origin_id   = "ALB-${aws_lb.main.name}"

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = var.api_domain != "" ? "https-only" : "http-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  ordered_cache_behavior {
    path_pattern           = "/api/*"
    target_origin_id       = "ALB-${aws_lb.main.name}"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods         = ["GET", "HEAD", "OPTIONS"]
    compress               = true

    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.api_routing.arn
    }

    forwarded_values {
      query_string = true
      headers      = ["Authorization", "Content-Type", "Origin", "X-API-Key"]

      cookies {
        forward = "all"
      }
    }

    min_ttl     = 0
    default_ttl = 0
    max_ttl     = 0
  }

  default_cache_behavior {
    target_origin_id       = "S3-${aws_s3_bucket.frontend.id}"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true

    forwarded_values {
      query_string = false

      cookies {
        forward = "none"
      }
    }

    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.spa_routing.arn
    }

    # Cache: hashed assets (main.abc123.js) cached long, index.html cached short
    min_ttl     = 0
    default_ttl = 3600
    max_ttl     = 86400
  }

  # 404 → serve index.html with 200 (fallback for any missed SPA routes)
  custom_error_response {
    error_code         = 404
    response_code      = 200
    response_page_path = "/index.html"
  }

  # SSL — use us-east-1 ACM certificate if domain is set; CloudFront default cert otherwise
  viewer_certificate {
    cloudfront_default_certificate = var.frontend_domain == ""
    acm_certificate_arn            = var.frontend_domain != "" ? aws_acm_certificate.frontend[0].arn : null
    ssl_support_method             = var.frontend_domain != "" ? "sni-only" : null
    # AWS fixes this field to TLSv1 when using the CloudFront default
    # certificate. Custom certificates use the explicit modern policy.
    minimum_protocol_version = var.frontend_domain != "" ? "TLSv1.2_2021" : "TLSv1"
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  tags = merge(local.common_tags, { Name = "${local.name_prefix}-cf" })
}
