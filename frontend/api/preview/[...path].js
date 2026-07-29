const ALLOWED_PATHS = [
  /^papers$/,
  /^papers\/[^/]+$/,
  /^papers\/[^/]+\/attribution-evidence-tree$/,
];

export default async function handler(request, response) {
  if (request.method !== "GET") {
    response.setHeader("Allow", "GET");
    return response.status(405).json({ detail: "Method not allowed" });
  }

  const backendUrl = process.env.PREVIEW_BACKEND_URL;
  const previewToken = process.env.PREVIEW_BACKEND_TOKEN;
  if (!backendUrl || !previewToken) {
    return response.status(503).json({ detail: "Preview proxy is not configured" });
  }

  const rawPath = request.query.path;
  const segments = Array.isArray(rawPath) ? rawPath : [rawPath];
  if (
    segments.some((segment) => !segment || segment === "." || segment === "..")
  ) {
    return response.status(404).json({ detail: "Not found" });
  }

  const path = segments.join("/");
  if (!ALLOWED_PATHS.some((pattern) => pattern.test(path))) {
    return response.status(404).json({ detail: "Not found" });
  }

  const upstream = new URL(
    segments.map(encodeURIComponent).join("/"),
    `${backendUrl.replace(/\/$/, "")}/`
  );
  for (const [key, value] of Object.entries(request.query)) {
    if (key === "path") continue;
    for (const item of Array.isArray(value) ? value : [value]) {
      upstream.searchParams.append(key, item);
    }
  }

  try {
    const upstreamResponse = await fetch(upstream, {
      headers: {
        Accept: "application/json",
        "X-Preview-Token": previewToken,
      },
    });
    const body = Buffer.from(await upstreamResponse.arrayBuffer());
    response.setHeader(
      "Content-Type",
      upstreamResponse.headers.get("content-type") ?? "application/json"
    );
    response.setHeader("Cache-Control", "private, no-store");
    return response.status(upstreamResponse.status).send(body);
  } catch {
    return response.status(502).json({ detail: "Preview backend unavailable" });
  }
}
