"""Standalone institution service delegates every protected read to PAS identity."""
import json
import os
import re
import urllib.error
import urllib.request
from fastapi import HTTPException, Request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def require_institution_admin(request: Request):
    if request.url.path == '/health' and request.method == 'GET':
        return
    token = request.cookies.get('__Host-pas-reader', '')
    if not re.fullmatch(r'[A-Za-z0-9_-]{32,128}', token):
        raise HTTPException(401, 'Sign in to PAS first.')
    authority = os.environ.get('PAS_AUTHORITY_URL', '')
    if not authority.startswith('https://'):
        raise HTTPException(503, 'PAS authorization is unavailable.')
    probe = urllib.request.Request(authority.rstrip('/') + '/api/access/check-admin',
        headers={'Cookie': '__Host-pas-reader=' + token})
    try:
        with urllib.request.build_opener(NoRedirect).open(probe, timeout=5) as response:
            if response.status != 200 or json.loads(response.read(4096)).get('authorized') is not True:
                raise HTTPException(503, 'PAS authorization is unavailable.')
    except urllib.error.HTTPError as exc:
        raise HTTPException(exc.code if exc.code in (401, 403) else 503, 'PAS admin authorization required.') from None
    except (OSError, ValueError):
        raise HTTPException(503, 'PAS authorization is unavailable.') from None
