/**
 * Gemeinsame Vorschau für „Aus Import-Ordner“: Thumbnail + Modal (Bild / PDF / sonst).
 * Erwartet Bootstrap 5 und #importOrdnerVorschauModal in base.html.
 */
(function () {
  'use strict';

  var ANZEIGEN_BASE = '/api/import/anzeigen/';

  function previewUrl(filename, importQuelle) {
    var u = ANZEIGEN_BASE + encodeURIComponent(filename);
    if (importQuelle === 'personal') {
      u += (u.indexOf('?') >= 0 ? '&' : '?') + 'quelle=personal';
    }
    return u;
  }

  /** Kombiniert gemeinsame und persönliche Import-Listen (API GET /api/import/dateien). */
  window.bisImportOrdnerMergeLists = function (data) {
    var a = (data.dateien || []).map(function (d) {
      return {
        name: d.name,
        size: d.size,
        size_bytes: d.size_bytes,
        import_quelle: 'import',
      };
    });
    var b = (data.dateien_personal || []).map(function (d) {
      return {
        name: d.name,
        size: d.size,
        size_bytes: d.size_bytes,
        import_quelle: 'personal',
      };
    });
    return a.concat(b);
  };

  /**
   * HTML für zwei Abschnitte (gemeinsam / persönlich). buildRowHtml(datei) → ein list-group-item.
   */
  window.bisImportOrdnerSectionenHtml = function (gefiltert, buildRowHtml) {
    var imp = gefiltert.filter(function (d) {
      return d.import_quelle !== 'personal';
    });
    var per = gefiltert.filter(function (d) {
      return d.import_quelle === 'personal';
    });
    var out = '';
    if (imp.length) {
      out +=
        '<h6 class="text-muted small text-uppercase mb-2">Gemeinsamer Import-Ordner</h6><div class="list-group mb-3">';
      imp.forEach(function (d) {
        out += buildRowHtml(d);
      });
      out += '</div>';
    }
    if (per.length) {
      out +=
        '<h6 class="text-muted small text-uppercase mb-2">Persönlicher Import-Ordner</h6><div class="list-group">';
      per.forEach(function (d) {
        out += buildRowHtml(d);
      });
      out += '</div>';
    }
    return out;
  };

  function escapeHtml(s) {
    var d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
  }

  function escapeAttr(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/"/g, '&quot;')
      .replace(/</g, '&lt;');
  }

  function extOf(filename) {
    var i = filename.lastIndexOf('.');
    return i >= 0 ? filename.slice(i).toLowerCase() : '';
  }

  /**
   * Linker Block: Vorschaubild/Icon + Dateiname + Größe (für list-group-item).
   * importQuelle: 'import' (default) oder 'personal' für Vorschau-URL.
   */
  window.importOrdnerRowLeftHtml = function (filename, sizeText, importQuelle) {
    var q = importQuelle === 'personal' ? 'personal' : 'import';
    var dataFn = escapeAttr(filename);
    var dataQ = escapeAttr(q);
    var ext = extOf(filename);
    var url = previewUrl(filename, q);
    var imgExts = ['.png', '.jpg', '.jpeg', '.gif', '.webp'];
    var dataAttrs =
      ' data-import-vorschau-fn="' +
      dataFn +
      '" data-import-vorschau-quelle="' +
      dataQ +
      '"';
    var thumb = '';
    if (imgExts.indexOf(ext) !== -1) {
      thumb =
        '<div class="import-ordner-thumb-wrap flex-shrink-0" role="button" tabindex="0" title="Vorschau" style="cursor:pointer"' +
        dataAttrs +
        '>' +
        '<img src="' +
        url +
        '" alt="" class="rounded border" width="56" height="56" style="object-fit:cover;display:block" loading="lazy">' +
        '</div>';
    } else if (ext === '.pdf') {
      thumb =
        '<div class="import-ordner-thumb-wrap flex-shrink-0 rounded border bg-danger bg-opacity-10 d-flex align-items-center justify-content-center" style="width:56px;height:56px;cursor:pointer" title="PDF anzeigen"' +
        dataAttrs +
        '><i class="bi bi-file-earmark-pdf text-danger fs-3"></i></div>';
    } else {
      thumb =
        '<div class="import-ordner-thumb-wrap flex-shrink-0 rounded border bg-secondary bg-opacity-10 d-flex align-items-center justify-content-center" style="width:56px;height:56px;cursor:pointer" title="Vorschau"' +
        dataAttrs +
        '><i class="bi bi-file-earmark fs-3 text-secondary"></i></div>';
    }
    return (
      '<div class="d-flex gap-2 align-items-center flex-grow-1 min-w-0">' +
      thumb +
      '<div class="min-w-0">' +
      '<strong class="d-block text-truncate" title="' +
      escapeHtml(filename) +
      '">' +
      escapeHtml(filename) +
      '</strong>' +
      '<small class="text-muted">' +
      escapeHtml(sizeText || '') +
      '</small>' +
      '</div></div>'
    );
  };

  window.openImportOrdnerVorschau = function (filename, importQuelle) {
    var q = importQuelle === 'personal' ? 'personal' : 'import';
    var url = previewUrl(filename, q);
    var ext = extOf(filename);
    var modalImg = document.getElementById('importOrdnerVorschauBild');
    var modalIframe = document.getElementById('importOrdnerVorschauPdf');
    var modalOther = document.getElementById('importOrdnerVorschauOther');
    var modalTitle = document.getElementById('importOrdnerVorschauTitel');
    var modal = document.getElementById('importOrdnerVorschauModal');

    if (!modal || typeof bootstrap === 'undefined') {
      window.open(url, '_blank', 'noopener,noreferrer');
      return;
    }

    if (modalTitle) modalTitle.textContent = filename;

    var imgExts = ['.png', '.jpg', '.jpeg', '.gif', '.webp'];
    if (modalImg) {
      modalImg.style.display = 'none';
      modalImg.removeAttribute('src');
    }
    if (modalIframe) {
      modalIframe.style.display = 'none';
      modalIframe.src = 'about:blank';
    }
    if (modalOther) {
      modalOther.style.display = 'none';
      modalOther.innerHTML = '';
    }

    if (imgExts.indexOf(ext) !== -1 && modalImg) {
      modalImg.src = url;
      modalImg.alt = filename;
      modalImg.style.display = 'inline-block';
    } else if (ext === '.pdf' && modalIframe) {
      modalIframe.src = url;
      modalIframe.style.display = 'block';
    } else if (modalOther) {
      modalOther.innerHTML =
        '<p class="mb-2 text-muted">Für diesen Dateityp gibt es keine eingebettete Vorschau.</p>' +
        '<a href="' +
        escapeHtml(url) +
        '" target="_blank" rel="noopener" class="btn btn-primary btn-sm">Datei in neuem Tab öffnen</a>';
      modalOther.style.display = 'block';
    }

    var bsModal = bootstrap.Modal.getOrCreateInstance(modal);
    bsModal.show();
  };

  /* Kein inline-onclick: JSON.stringify bricht doppelte Anführungszeichen im HTML-Attribut. */
  document.addEventListener('click', function (ev) {
    var t = ev.target;
    if (!t || !t.closest) {
      return;
    }
    var wrap = t.closest('.import-ordner-thumb-wrap[data-import-vorschau-fn]');
    if (!wrap) {
      return;
    }
    var fn = wrap.getAttribute('data-import-vorschau-fn');
    var qu = wrap.getAttribute('data-import-vorschau-quelle') || 'import';
    if (!fn) {
      return;
    }
    ev.preventDefault();
    window.openImportOrdnerVorschau(fn, qu);
  });

  document.addEventListener('keydown', function (ev) {
    if (ev.key !== 'Enter' && ev.key !== ' ') {
      return;
    }
    var w = ev.target && ev.target.closest ? ev.target.closest('.import-ordner-thumb-wrap[data-import-vorschau-fn]') : null;
    if (!w || ev.target !== w) {
      return;
    }
    ev.preventDefault();
    var fn2 = w.getAttribute('data-import-vorschau-fn');
    var qu2 = w.getAttribute('data-import-vorschau-quelle') || 'import';
    if (fn2) {
      window.openImportOrdnerVorschau(fn2, qu2);
    }
  });

  document.addEventListener('hidden.bs.modal', function (ev) {
    if (!ev.target || ev.target.id !== 'importOrdnerVorschauModal') return;
    var iframe = document.getElementById('importOrdnerVorschauPdf');
    if (iframe) iframe.src = 'about:blank';
    var img = document.getElementById('importOrdnerVorschauBild');
    if (img) {
      img.removeAttribute('src');
      img.style.display = 'none';
    }
  });
})();
