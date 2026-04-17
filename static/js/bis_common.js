/*
 * BIS – gemeinsame JavaScript-Helfer.
 *
 * 1. Globaler fetch-Wrapper, der für state-changing Requests (POST, PUT,
 *    PATCH, DELETE) automatisch den CSRF-Token aus <meta name="csrf-token">
 *    als Header `X-CSRFToken` anhängt. Damit müssen bestehende fetch()-
 *    Aufrufe nicht einzeln angepasst werden.
 *
 * 2. `window.BIS.escapeHtml` – zentraler HTML-Escape für DOM-XSS-Schutz,
 *    wenn Strings per innerHTML eingefügt werden.
 */
(function () {
  'use strict';

  var csrfMeta = document.querySelector('meta[name="csrf-token"]');
  var csrfToken = csrfMeta ? csrfMeta.getAttribute('content') : '';

  function isStateChanging(method) {
    if (!method) return false;
    var m = String(method).toUpperCase();
    return m === 'POST' || m === 'PUT' || m === 'PATCH' || m === 'DELETE';
  }

  function isSameOrigin(url) {
    try {
      var u = new URL(url, window.location.origin);
      return u.origin === window.location.origin;
    } catch (e) {
      return true;
    }
  }

  if (window.fetch && csrfToken) {
    var originalFetch = window.fetch.bind(window);
    window.fetch = function (input, init) {
      init = init || {};
      var method = init.method || (typeof input === 'object' && input.method) || 'GET';
      var url = typeof input === 'string' ? input : (input && input.url) || '';

      if (isStateChanging(method) && isSameOrigin(url)) {
        var headers = new Headers(init.headers || (typeof input === 'object' ? input.headers : undefined));
        if (!headers.has('X-CSRFToken')) {
          headers.set('X-CSRFToken', csrfToken);
        }
        init.headers = headers;
        if (init.credentials === undefined) {
          init.credentials = 'same-origin';
        }
      }
      return originalFetch(input, init);
    };
  }

  var originalXhrOpen = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function (method, url) {
    this.__bis_method = method;
    this.__bis_url = url;
    return originalXhrOpen.apply(this, arguments);
  };
  var originalXhrSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.send = function () {
    try {
      if (csrfToken && isStateChanging(this.__bis_method) && isSameOrigin(this.__bis_url || '')) {
        this.setRequestHeader('X-CSRFToken', csrfToken);
      }
    } catch (e) {
      /* ignorieren – Header kann nach send() nicht mehr gesetzt werden */
    }
    return originalXhrSend.apply(this, arguments);
  };

  function escapeHtml(value) {
    if (value === null || value === undefined) return '';
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  window.BIS = window.BIS || {};
  window.BIS.escapeHtml = escapeHtml;
  window.BIS.csrfToken = csrfToken;
})();
