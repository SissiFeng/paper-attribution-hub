/* Installed before legacy admin modules; authorization remains server-side. */
(function () {
  var original = window.fetch.bind(window);
  window.fetch = function (input, init) {
    var url = new URL(typeof input === 'string' ? input : input.url, location.href);
    if (url.origin === location.origin && url.pathname.indexOf('/api/') === 0) {
      init = Object.assign({}, init);
      var headers = new Headers(init.headers || (input instanceof Request ? input.headers : undefined));
      headers.set('X-PAS-Request', '1'); init.headers = headers;
      init.credentials = 'same-origin'; init.cache = 'no-store';
    }
    return original(input, init);
  };
  function leave() { document.body.replaceChildren(); location.replace('/reading/'); }
  function check() {
    return original('/api/auth/me', { credentials: 'same-origin', cache: 'no-store' })
      .then(function (r) { if (!r.ok) throw new Error('unauthorized'); return r.json(); })
      .then(function (u) { if (u.role !== 'admin') leave(); }).catch(leave);
  }
  window.addEventListener('focus', check);
  window.addEventListener('pageshow', check);
  window.addEventListener('storage', function (e) { if (e.key === 'pas.identity.changed') check(); });
  setInterval(check, 60000);
  window.addEventListener('DOMContentLoaded', function () {
    var nav = document.createElement('aside'); nav.setAttribute('aria-label', 'PAS account');
    nav.style.cssText = 'position:fixed;bottom:12px;right:12px;z-index:2147483647;background:white;padding:8px 14px;border:1px solid #ccc;border-radius:8px;font:13px system-ui;color:#183b2b;display:flex;gap:14px';
    [['Reading room','/reading/'],['Manage access','/reading/?manage=members']].forEach(function (v) {
      var a=document.createElement('a'); a.textContent=v[0]; a.href=v[1]; nav.append(a);
    });
    document.body.append(nav);
  });
}());
