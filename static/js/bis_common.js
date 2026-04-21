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
 *
 * 3. Globaler Submit-Lock für Formulare: Jeder abgesendete POST/PUT/…-
 *    Form wird gegen Doppel-Submit gesichert. Submit-Buttons werden
 *    deaktiviert und zeigen einen Spinner, bis die Seite neu lädt oder
 *    der Safety-Timeout greift. Opt-Out per `data-bis-no-lock` am Form
 *    oder Button. Zusätzlich stehen `window.BIS.lockButton` und
 *    `window.BIS.unlockButton` als Helfer für AJAX-Buttons bereit.
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

  /* ------------------------------------------------------------------ */
  /*  Submit-Lock / Button-Lock                                         */
  /* ------------------------------------------------------------------ */

  // Safety-Timeout: Falls Redirect/AJAX hängt, werden Locks spätestens
  // nach dieser Zeit automatisch wieder aufgehoben, damit der User nicht
  // dauerhaft einen toten Button sieht.
  var LOCK_TIMEOUT_MS = 20000;

  var SPINNER_HTML =
    '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>' +
    '<span class="visually-hidden">Wird verarbeitet…</span>';

  function hasOptOut(el) {
    return el && el.hasAttribute && el.hasAttribute('data-bis-no-lock');
  }

  function getSubmitButtons(form) {
    var selectorInternal = 'button[type="submit"], input[type="submit"], button:not([type])';
    var list = Array.prototype.slice.call(form.querySelectorAll(selectorInternal));
    if (form.id) {
      var attr = '[form="' + form.id + '"]';
      var selectorExternal =
        'button[type="submit"]' + attr +
        ', input[type="submit"]' + attr +
        ', button:not([type])' + attr;
      var external = document.querySelectorAll(selectorExternal);
      for (var i = 0; i < external.length; i++) {
        if (list.indexOf(external[i]) === -1) list.push(external[i]);
      }
    }
    return list;
  }

  function lockButton(btn, opts) {
    if (!btn) return;
    opts = opts || {};
    if (btn.getAttribute('data-bis-locked') === '1') return;
    if (hasOptOut(btn)) return;

    // Breite fixieren, damit der Button beim Spinner-Tausch nicht springt.
    var width = btn.offsetWidth;
    if (width > 0 && !btn.style.width) {
      btn.setAttribute('data-bis-original-width', '');
      btn.style.width = width + 'px';
    }

    btn.setAttribute('data-bis-original-html', btn.innerHTML);
    btn.setAttribute('data-bis-locked', '1');

    if (opts.spinner !== false) {
      btn.innerHTML = SPINNER_HTML;
    }
    btn.disabled = true;
    btn.setAttribute('aria-busy', 'true');

    var timeout = opts.timeout === undefined ? LOCK_TIMEOUT_MS : opts.timeout;
    if (timeout && timeout > 0) {
      btn.__bisLockTimer = window.setTimeout(function () {
        unlockButton(btn);
      }, timeout);
    }
  }

  function unlockButton(btn) {
    if (!btn) return;
    if (btn.__bisLockTimer) {
      window.clearTimeout(btn.__bisLockTimer);
      btn.__bisLockTimer = null;
    }
    if (btn.getAttribute('data-bis-locked') !== '1') return;

    var originalHtml = btn.getAttribute('data-bis-original-html');
    if (originalHtml !== null) {
      btn.innerHTML = originalHtml;
      btn.removeAttribute('data-bis-original-html');
    }
    if (btn.hasAttribute('data-bis-original-width')) {
      btn.style.width = '';
      btn.removeAttribute('data-bis-original-width');
    }
    btn.disabled = false;
    btn.removeAttribute('aria-busy');
    btn.removeAttribute('data-bis-locked');
  }

  function shouldLockForm(form) {
    if (!form || !(form instanceof HTMLFormElement)) return false;
    if (hasOptOut(form)) return false;
    var method = (form.getAttribute('method') || 'GET').toUpperCase();
    // GET-Formulare (typisch: Filter/Suche) sind keine Dubletten-Quelle.
    return method !== 'GET';
  }

  function lockForm(form) {
    form.setAttribute('data-bis-submitting', '1');
    var buttons = getSubmitButtons(form);
    for (var i = 0; i < buttons.length; i++) {
      lockButton(buttons[i]);
    }
    form.__bisLockTimer = window.setTimeout(function () {
      unlockForm(form);
    }, LOCK_TIMEOUT_MS);
  }

  function unlockForm(form) {
    if (!form || !(form instanceof HTMLFormElement)) return;
    if (form.__bisLockTimer) {
      window.clearTimeout(form.__bisLockTimer);
      form.__bisLockTimer = null;
    }
    form.removeAttribute('data-bis-submitting');
    var buttons = getSubmitButtons(form);
    for (var i = 0; i < buttons.length; i++) {
      unlockButton(buttons[i]);
    }
  }

  // Submit-Handler in der Bubble-Phase: So laufen fremde submit-Handler
  // zuerst. Wenn einer von ihnen preventDefault() aufruft (AJAX-Submit),
  // überspringen wir den Lock – der Handler verwaltet den Button selbst
  // bzw. kann gezielt `BIS.lockButton` nutzen. Nur „echte" Full-Page-
  // POST-Submits werden gesperrt.
  document.addEventListener('submit', function (e) {
    var form = e.target;
    if (!shouldLockForm(form)) return;

    // Zweiter Submit während der erste noch läuft ? hart blocken.
    if (form.getAttribute('data-bis-submitting') === '1') {
      e.preventDefault();
      if (typeof e.stopImmediatePropagation === 'function') {
        e.stopImmediatePropagation();
      }
      return;
    }

    if (e.defaultPrevented) return;

    lockForm(form);
  });

  // Reset-Event räumt den Lock ab (falls jemand manuell form.reset() macht).
  document.addEventListener('reset', function (e) {
    if (e.target instanceof HTMLFormElement) {
      unlockForm(e.target);
    }
  });

  // BFCache: Beim „Zurück"-Navigieren restaurieren Browser die Seite
  // inklusive disabled-Buttons. Diese wieder freigeben.
  window.addEventListener('pageshow', function (e) {
    if (!e.persisted) return;
    var forms = document.querySelectorAll('form[data-bis-submitting="1"]');
    for (var i = 0; i < forms.length; i++) unlockForm(forms[i]);
    var btns = document.querySelectorAll('[data-bis-locked="1"]');
    for (var j = 0; j < btns.length; j++) unlockButton(btns[j]);
  });

  // Opt-In für Non-Submit-Buttons / Links: `data-bis-lock-once` sorgt
  // dafür, dass der Button beim ersten Klick gesperrt wird. Praktisch
  // für AJAX-Aktionen, die keinen Form-Submit auslösen.
  document.addEventListener('click', function (e) {
    var el = e.target.closest ? e.target.closest('[data-bis-lock-once]') : null;
    if (!el) return;

    if (el.getAttribute('data-bis-locked') === '1' || el.disabled) {
      e.preventDefault();
      if (typeof e.stopImmediatePropagation === 'function') {
        e.stopImmediatePropagation();
      }
      return;
    }

    // Submit-Buttons werden bereits vom Form-Submit-Lock bedient.
    if (el.tagName === 'BUTTON') {
      var t = (el.getAttribute('type') || 'submit').toLowerCase();
      if (t === 'submit' && el.form) return;
    }

    lockButton(el);
  }, true);

  window.BIS = window.BIS || {};
  window.BIS.escapeHtml = escapeHtml;
  window.BIS.csrfToken = csrfToken;
  window.BIS.lockButton = lockButton;
  window.BIS.unlockButton = unlockButton;
  window.BIS.lockForm = lockForm;
  window.BIS.unlockForm = unlockForm;
})();
