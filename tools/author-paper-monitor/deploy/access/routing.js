function handler(event) {
  var request = event.request;
  var uri = request.uri;
  // A DOI-based paper ID may contain dots; it is a route, not a static file.
  if (uri === '/papers' || uri.indexOf('/papers/') === 0 || uri === '/research') { request.uri = '/index.html'; return request; }
  if (uri === '/reading' || uri === '/reading/') { request.uri = '/reading/index.html'; return request; }
  if (uri === '/reading/index.html' || uri === '/reading/access-guard.js' || uri.indexOf('/reading/assets/') === 0) return request;
  if (uri.indexOf('/assets/') === 0 && /\.(js|css)$/.test(uri)) return request;
  // Static reports, data and compiled legacy assets all pass through PAS admin auth.
  if (uri.indexOf('/protected-legacy/') === 0) return { statusCode: 404, statusDescription: 'Not Found', headers: {'cache-control': {value:'no-store'}} };
  if (uri.indexOf('.') >= 0 && uri !== '/index.html') {
    return {statusCode:302,statusDescription:'Found',headers:{location:{value:'/api/access/files' + uri},'cache-control':{value:'no-store'}}};
  }
  request.uri = '/index.html';
  return request;
}
