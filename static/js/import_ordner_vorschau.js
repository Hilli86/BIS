/**
 * Gemeinsame Vorschau für „Aus Import-Ordner“: Thumbnail + Modal (Bild / PDF / sonst).
 * Erwartet Bootstrap 5 und #importOrdnerVorschauModal in base.html.
 */
(function () {
  'use strict';

  var ANZEIGEN_BASE = '/api/import/anzeigen/';

  function previewUrl(filename) {
    return ANZEIGEN_BASE + encodeURIComponent(filename);
  }

  function escapeHtml(s) {
    var d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
  }

  function extOf(filename) {
    var i = filename.lastIndexOf('.');
    return i >= 0 ? filename.slice(i).toLowerCase() : '';
  }

  /**
   * Linker Block: Vorschaubild/Icon + Dateiname + Größe (für list-group-item).
   */
  window.importOrdnerRowLeftHtml = function (filename, sizeText) {
    var fnEsc = JSON.stringify(filename);
    var ext = extOf(filename);
    var url = previewUrl(filename);
    var imgExts = ['.png', '.jpg', '.jpeg', '.gif', '.webp'];
    var thumb = '';
    if (imgExts.indexOf(ext) !== -1) {
      thumb =
        '<div class="import-ordner-thumb-wrap flex-shrink-0" role="button" tabindex="0" title="Vorschau" onclick="openImportOrdnerVorschau(' +
        fnEsc +
        ')">' +
        '<img src="' +
        url +
        '" alt="" class="rounded border" width="56" height="56" style="object-fit:cover;display:block" loading="lazy">' +
        '</div>';
    } else if (ext === '.pdf') {
      thumb =
        '<div class="import-ordner-thumb-wrap flex-shrink-0 rounded border bg-danger bg-opacity-10 d-flex align-items-center justify-content-center" style="width:56px;height:56px;cursor:pointer" title="PDF anzeigen" onclick="openImportOrdnerVorschau(' +
        fnEsc +
        ')"><i class="bi bi-file-earmark-pdf text-danger fs-3"></i></div>';
    } else {
      thumb =
        '<div class="import-ordner-thumb-wrap flex-shrink-0 rounded border bg-secondary bg-opacity-10 d-flex align-items-center justify-content-center" style="width:56px;height:56px;cursor:pointer" title="Vorschau" onclick="openImportOrdnerVorschau(' +
        fnEsc +
        ')"><i class="bi bi-file-earmark fs-3 text-secondary"></i></div>';
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

  window.openImportOrdnerVorschau = function (filename) {
    var url = previewUrl(filename);
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
