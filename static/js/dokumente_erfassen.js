/**
 * Dokumente erfassen: Kamera/Bild, OpenCV.js Kantenerkennung, Zuschnitt, Bearbeitung, Upload nach Import-Ordner.
 */
(function () {
  'use strict';

  /** @type {Promise<void>|null} */
  let opencvLoadingPromise = null;

  const boot = document.getElementById('dokumente-erfassen-boot');
  const UPLOAD_URL = boot && boot.dataset.uploadUrl ? boot.dataset.uploadUrl : '/api/import/hochladen';

  /** Freiraum um die Vorschau im Bereich „Dokumentrand anpassen“ (px je Seite), sichtbar als grauer Rand. */
  const ADJUST_VIEW_PADDING = 28;

  /**
   * Mindestanteil der Bildfläche für ein plausibles ganzes Blatt (filtert starke innere Rechtecke
   * wie Tabellenköpfe bei jscanify / Legacy).
   */
  const DOC_QUAD_MIN_AREA_RATIO = 0.18;

  /** Lokal (/static/vendor/…) zuerst (offline); sonst CDN-Fallbacks. data-opencv-local kommt aus dem Template. */
  const OPENCV_SCRIPT_URLS = (function () {
    const urls = [];
    const local =
      boot && typeof boot.dataset.opencvLocal === 'string'
        ? boot.dataset.opencvLocal.trim()
        : '';
    if (local) {
      urls.push(local);
    }
    urls.push(
      'https://cdn.jsdelivr.net/npm/@techstark/opencv-js@4.12.0-release.1/dist/opencv.js',
      'https://unpkg.com/@techstark/opencv-js@4.12.0-release.1/dist/opencv.js'
    );
    return urls;
  })();

  /** POST-URL mit Dateiname in der Query (zuverlässiger als nur multipart auf iOS/Android). Im persönlichen Import-Unterordner (Personalnummer). */
  function buildImportUploadUrl(filenameEncoded) {
    const sep = UPLOAD_URL.indexOf('?') >= 0 ? '&' : '?';
    return (
      UPLOAD_URL +
      sep +
      'filename=' +
      encodeURIComponent(filenameEncoded) +
      '&personal=1'
    );
  }

  const el = {
    video: document.getElementById('video-preview'),
    videoPlaceholder: document.getElementById('video-placeholder'),
    canvasCapture: document.getElementById('canvas-capture'),
    canvasAdjust: document.getElementById('canvas-adjust'),
    canvasResult: document.getElementById('canvas-result'),
    opencvStatus: document.getElementById('opencv-status'),
    saveMessage: document.getElementById('save-message'),
    btnStartCamera: document.getElementById('btn-start-camera'),
    btnStopCamera: document.getElementById('btn-stop-camera'),
    btnCapture: document.getElementById('btn-capture'),
    btnCaptureMobile: document.getElementById('btn-capture-mobile'),
    btnDetect: document.getElementById('btn-detect'),
    btnWarp: document.getElementById('btn-warp'),
    btnResetCorners: document.getElementById('btn-reset-corners'),
    btnSaveImport: document.getElementById('btn-save-import'),
    btnDownloadLocal: document.getElementById('btn-download-local'),
    fileInput: document.getElementById('file-input'),
    rangeBrightness: document.getElementById('range-brightness'),
    rangeContrast: document.getElementById('range-contrast'),
    rangeRotate: document.getElementById('range-rotate'),
    valBrightness: document.getElementById('val-brightness'),
    valContrast: document.getElementById('val-contrast'),
    valRotate: document.getElementById('val-rotate'),
    chkGrayscale: document.getElementById('chk-grayscale'),
    adjustWrap: document.getElementById('adjust-wrap'),
    saveFilename: document.getElementById('save-filename'),
    cameraTapHint: document.getElementById('camera-tap-hint'),
    filenameFocusSink: document.getElementById('filename-focus-sink'),
    collapseBearbeitung: document.getElementById('collapse-bearbeitung'),
    personalImportListe: document.getElementById('dokumente-personal-import-liste'),
    btnPersonalImportRefresh: document.getElementById('btn-dokumente-personal-import-refresh'),
  };

  const state = {
    stream: null,
    /** @type {HTMLCanvasElement|null} */
    sourceCanvas: null,
    /** @type {number[][]|null} tl,tr,br,bl in Quellbild-Pixelkoordinaten */
    corners: null,
    /** @type {HTMLCanvasElement|null} */
    warpedCanvas: null,
    cvReady: false,
    dragIndex: -1,
    adjustScale: 1,
    adjustOffsetX: 0,
    adjustOffsetY: 0,
    /** Nur Touch/Stift: body/html overflow gesperrt (Maus: sonst verschwindet Scrollbar → Layout-Sprung am Desktop) */
    adjustScrollLockActive: false,
    /** Gespiegelter Dateiname (Mobile: input.value erst nach blur zuverlässig; input-Event aktualisiert sofort) */
    saveFilenameMirror: '',
    /** Lazy nach OpenCV-Load: `new window.jscanify()` */
    jscanifyScanner: null,
  };

  function setOpencvStatus(text, isError) {
    if (!el.opencvStatus) return;
    el.opencvStatus.textContent = text || '';
    el.opencvStatus.classList.toggle('text-danger', !!isError);
  }

  function showCameraTapHint() {
    if (el.cameraTapHint) el.cameraTapHint.classList.remove('d-none');
  }

  function hideCameraTapHint() {
    if (el.cameraTapHint) el.cameraTapHint.classList.add('d-none');
  }

  function setCaptureButtonsDisabled(disabled) {
    if (el.btnCapture) el.btnCapture.disabled = disabled;
    if (el.btnCaptureMobile) el.btnCaptureMobile.disabled = disabled;
  }

  function isLikelyMobileBrowser() {
    return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent || '');
  }

  function scheduleAfterKeyboardFriendly(fn) {
    if (isLikelyMobileBrowser()) {
      window.setTimeout(fn, 80);
    } else {
      requestAnimationFrame(function () {
        requestAnimationFrame(fn);
      });
    }
  }

  /** Lokale Zeit (toISOString() wäre UTC und verschiebt die Uhrzeit). */
  function localTimestampForFilename() {
    const d = new Date();
    function pad(n) {
      return String(n).padStart(2, '0');
    }
    return (
      d.getFullYear() +
      '-' +
      pad(d.getMonth() + 1) +
      '-' +
      pad(d.getDate()) +
      'T' +
      pad(d.getHours()) +
      '-' +
      pad(d.getMinutes()) +
      '-' +
      pad(d.getSeconds())
    );
  }

  function loadOpenCv() {
    if (window.cv && typeof cv.Mat !== 'undefined') {
      if (cv.getBuildInformation) {
        state.cvReady = true;
        return Promise.resolve();
      }
      return new Promise(function (resolve) {
        cv['onRuntimeInitialized'] = function () {
          state.cvReady = true;
          resolve();
        };
      });
    }
    if (opencvLoadingPromise) {
      return opencvLoadingPromise;
    }
    opencvLoadingPromise = new Promise(function (resolve, reject) {
      function failAll() {
        opencvLoadingPromise = null;
        setOpencvStatus(
          'OpenCV.js konnte nicht geladen werden (Netzwerk oder Sicherheitsrichtlinie). Zuschnitt mit Standardrahmen möglich.',
          true
        );
        reject(new Error('opencv load'));
      }
      function tryUrl(index) {
        if (index >= OPENCV_SCRIPT_URLS.length) {
          failAll();
          return;
        }
        const script = document.createElement('script');
        script.src = OPENCV_SCRIPT_URLS[index];
        script.async = true;
        script.onload = function () {
          cv['onRuntimeInitialized'] = function () {
            state.cvReady = true;
            setOpencvStatus('Bildverarbeitung bereit.');
            resolve();
          };
        };
        script.onerror = function () {
          if (script.parentNode) {
            script.parentNode.removeChild(script);
          }
          tryUrl(index + 1);
        };
        document.head.appendChild(script);
      }
      tryUrl(0);
    });
    return opencvLoadingPromise;
  }

  function orderPoints(pts) {
    const sums = pts.map(function (p) {
      return p[0] + p[1];
    });
    const diffs = pts.map(function (p) {
      return p[1] - p[0];
    });
    const rect = [[0, 0], [0, 0], [0, 0], [0, 0]];
    rect[0] = pts[sums.indexOf(Math.min.apply(null, sums))];
    rect[2] = pts[sums.indexOf(Math.max.apply(null, sums))];
    rect[1] = pts[diffs.indexOf(Math.min.apply(null, diffs))];
    rect[3] = pts[diffs.indexOf(Math.max.apply(null, diffs))];
    return rect;
  }

  /** Standardrahmen leicht eingerückt (Vollbild wirkt bei Fehler oft wie „Tisch mit erkannt“). */
  function defaultCorners(w, h) {
    const xmax = Math.max(0, w - 1);
    const ymax = Math.max(0, h - 1);
    const inset = Math.max(10, Math.round(Math.min(w, h) * 0.042));
    if (inset * 2 + 4 >= w || inset * 2 + 4 >= h) {
      return [
        [0, 0],
        [xmax, 0],
        [xmax, ymax],
        [0, ymax],
      ];
    }
    return [
      [inset, inset],
      [xmax - inset, inset],
      [xmax - inset, ymax - inset],
      [inset, ymax - inset],
    ];
  }

  function approxToPoints(approx) {
    const pts = [];
    const rows = approx.rows;
    const useInt = approx.data32S && approx.data32S.length >= rows * 2;
    const buf = useInt ? approx.data32S : approx.data32F;
    if (buf && buf.length >= rows * 2) {
      for (let i = 0; i < rows; i++) {
        pts.push([buf[i * 2], buf[i * 2 + 1]]);
      }
      return pts;
    }
    for (let i = 0; i < rows; i++) {
      try {
        const p = approx.intPtr(i, 0);
        pts.push([p[0], p[1]]);
      } catch (e) {
        return null;
      }
    }
    return pts.length ? pts : null;
  }

  function quadAreaOrdered(pts) {
    const tl = pts[0];
    const tr = pts[1];
    const br = pts[2];
    const bl = pts[3];
    return (
      0.5 *
      Math.abs(
        tl[0] * tr[1] -
          tr[0] * tl[1] +
          tr[0] * br[1] -
          br[0] * tr[1] +
          br[0] * bl[1] -
          bl[0] * br[1] +
          bl[0] * tl[1] -
          tl[0] * bl[1]
      )
    );
  }

  function vertexAngleDeg(pa, pb, pc) {
    const v1x = pa[0] - pb[0];
    const v1y = pa[1] - pb[1];
    const v2x = pc[0] - pb[0];
    const v2y = pc[1] - pb[1];
    const dot = v1x * v2x + v1y * v2y;
    const cross = v1x * v2y - v1y * v2x;
    return (Math.atan2(Math.abs(cross), dot) * 180) / Math.PI;
  }

  /** Innenwinkel an tl,tr,br,bl (Reihenfolge wie orderPoints); filtert starke Falt-/Fragment-Trapezoide. */
  function isPlausiblePerspectiveQuad(pts) {
    const tl = pts[0];
    const tr = pts[1];
    const br = pts[2];
    const bl = pts[3];
    const angles = [
      vertexAngleDeg(bl, tl, tr),
      vertexAngleDeg(tl, tr, br),
      vertexAngleDeg(tr, br, bl),
      vertexAngleDeg(br, bl, tl),
    ];
    const minA = Math.min.apply(null, angles);
    const maxA = Math.max.apply(null, angles);
    return minA >= 33 && maxA <= 147;
  }

  function cross2(o, a, b) {
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  }

  /** tl→tr→br→bl konvex (keine Selbstüberschneidung). */
  function isConvexQuadOrdered(pts) {
    const tl = pts[0];
    const tr = pts[1];
    const br = pts[2];
    const bl = pts[3];
    const c1 = cross2(tl, tr, br);
    const c2 = cross2(tr, br, bl);
    const c3 = cross2(br, bl, tl);
    const c4 = cross2(bl, tl, tr);
    if (c1 * c2 <= 0 || c2 * c3 <= 0 || c3 * c4 <= 0 || c4 * c1 <= 0) {
      return false;
    }
    return true;
  }

  /** Sehr lange vs. sehr kurze Kante (Streifen entlang Faltlinie / Tischkante). */
  function hasExtremeEdgeLengthRatio(pts) {
    const tl = pts[0];
    const tr = pts[1];
    const br = pts[2];
    const bl = pts[3];
    function dist(a, b) {
      return Math.hypot(b[0] - a[0], b[1] - a[1]);
    }
    const e = [dist(tl, tr), dist(tr, br), dist(br, bl), dist(bl, tl)];
    const mn = Math.min.apply(null, e);
    const mx = Math.max.apply(null, e);
    if (mn < 1e-6) {
      return true;
    }
    return mx / mn > 11;
  }

  /**
   * Typischer Fehler: untere Blattecken stimmen, die obere Kante klebt an Falz/Schatten/Tabellenlinie
   * (unterer Streifen oder „Oben“ der Quad in der Bildmitte statt am Blattrand).
   */
  function isLikelyHorizontalFoldArtifact(pts, w, h) {
    const tl = pts[0];
    const tr = pts[1];
    const br = pts[2];
    const bl = pts[3];
    const ys = pts.map(function (p) {
      return p[1];
    });
    const yMin = Math.min.apply(null, ys);
    const yMax = Math.max.apply(null, ys);
    const span = yMax - yMin;
    const yTopAvg = (tl[1] + tr[1]) * 0.5;
    const yBotAvg = (bl[1] + br[1]) * 0.5;

    /* Nur obere Hälfte: untere Quad-Kante an Tabellenlinie/Falz (yMax oft < 0.64h → vor frühem return) */
    if (
      yMin < 0.26 * h &&
      yMax < 0.67 * h &&
      yBotAvg < 0.56 * h &&
      yTopAvg < 0.32 * h &&
      span < 0.62 * h
    ) {
      return true;
    }

    if (yMax < 0.64 * h) {
      return false;
    }

    if (
      yMax > 0.66 * h &&
      yMin > 0.2 * h &&
      yTopAvg > 0.36 * h &&
      yBotAvg > 0.62 * h &&
      span < 0.74 * h &&
      yBotAvg - yTopAvg < 0.58 * h
    ) {
      return true;
    }

    if (span > 0.58 * h) {
      return false;
    }
    if (yMin < 0.11 * h) {
      return false;
    }
    if (yMin > 0.45 * h && span < 0.58 * h) {
      return true;
    }

    return false;
  }

  /**
   * Mittlerer Grauwert-Unterschied über die Quad-Kanten (innen vs. außen); niedrig bei
   * „Rahmen liegt auf einheitlichem Tisch“ (Übergröße trotz hohem areaRatio).
   * @param {HTMLCanvasElement} canvasFull
   * @param {number[][]} pts [tl,tr,br,bl] in Pixeln von canvasFull
   * @returns {number} typ. 0–40, schwach < ~6
   */
  function borderContrastScore(canvasFull, pts) {
    const tw = Math.min(480, Math.max(140, canvasFull.width));
    const th = Math.max(1, Math.round(canvasFull.height * (tw / canvasFull.width)));
    const sx = tw / canvasFull.width;
    const sy = th / canvasFull.height;
    const ps = [
      [pts[0][0] * sx, pts[0][1] * sy],
      [pts[1][0] * sx, pts[1][1] * sy],
      [pts[2][0] * sx, pts[2][1] * sy],
      [pts[3][0] * sx, pts[3][1] * sy],
    ];
    const c = document.createElement('canvas');
    c.width = tw;
    c.height = th;
    const ctx = c.getContext('2d');
    if (!ctx) {
      return 20;
    }
    ctx.drawImage(canvasFull, 0, 0, tw, th);
    let id;
    try {
      id = ctx.getImageData(0, 0, tw, th);
    } catch (e) {
      return 20;
    }
    const buf = id.data;
    function lum(ix, iy) {
      ix = ix | 0;
      iy = iy | 0;
      if (ix < 0 || ix >= tw || iy < 0 || iy >= th) {
        return null;
      }
      const i = (iy * tw + ix) * 4;
      return 0.299 * buf[i] + 0.587 * buf[i + 1] + 0.114 * buf[i + 2];
    }
    const cx = (ps[0][0] + ps[1][0] + ps[2][0] + ps[3][0]) * 0.25;
    const cy = (ps[0][1] + ps[1][1] + ps[2][1] + ps[3][1]) * 0.25;
    const rin = 4;
    const rout = 10;
    const edges = [
      [ps[0], ps[1]],
      [ps[1], ps[2]],
      [ps[2], ps[3]],
      [ps[3], ps[0]],
    ];
    const perEdge = [];
    for (let e = 0; e < 4; e++) {
      const a = edges[e][0];
      const b = edges[e][1];
      let nx = -(b[1] - a[1]);
      let ny = b[0] - a[0];
      const nlen = Math.hypot(nx, ny) || 1;
      nx /= nlen;
      ny /= nlen;
      const mx = (a[0] + b[0]) * 0.5;
      const my = (a[1] + b[1]) * 0.5;
      if ((mx + nx * rout - cx) * nx + (my + ny * rout - cy) * ny < 0) {
        nx = -nx;
        ny = -ny;
      }
      let sum = 0;
      let cnt = 0;
      for (let s = 1; s <= 16; s++) {
        const t = s / 17;
        const px = a[0] + t * (b[0] - a[0]);
        const py = a[1] + t * (b[1] - a[1]);
        const li = lum(px - nx * rin, py - ny * rin);
        const lo = lum(px + nx * rout, py + ny * rout);
        if (li === null || lo === null) {
          continue;
        }
        sum += Math.abs(li - lo);
        cnt++;
      }
      perEdge.push(cnt > 0 ? sum / cnt : 0);
    }
    const mn = Math.min.apply(null, perEdge);
    const mean = (perEdge[0] + perEdge[1] + perEdge[2] + perEdge[3]) * 0.25;
    return 0.42 * mn + 0.58 * mean;
  }

  /**
   * Ecken, die dicht am Bildrand liegen und nach außen (vom Quad-Schwerpunkt weg) auf sehr dunkles
   * Material zeigen (Tastatur, Schattenfresse) – typisch bei „Rechnung“ mit Laptop oben links.
   * @returns {number} 0–4
   */
  function countDarkOutwardHitsNearFrame(canvasFull, pts) {
    const tw = Math.min(560, Math.max(160, canvasFull.width));
    const th = Math.max(1, Math.round(canvasFull.height * (tw / canvasFull.width)));
    const sx = tw / canvasFull.width;
    const sy = th / canvasFull.height;
    const c = document.createElement('canvas');
    c.width = tw;
    c.height = th;
    const ctx = c.getContext('2d');
    if (!ctx) {
      return 0;
    }
    ctx.drawImage(canvasFull, 0, 0, tw, th);
    let id;
    try {
      id = ctx.getImageData(0, 0, tw, th);
    } catch (e) {
      return 0;
    }
    const buf = id.data;
    const shortT = Math.min(tw, th);
    const edgeNear = shortT * 0.1;
    const cxc =
      (pts[0][0] * sx + pts[1][0] * sx + pts[2][0] * sx + pts[3][0] * sx) * 0.25;
    const cyc =
      (pts[0][1] * sy + pts[1][1] * sy + pts[2][1] * sy + pts[3][1] * sy) * 0.25;
    let hits = 0;
    for (let i = 0; i < 4; i++) {
      const px = pts[i][0] * sx;
      const py = pts[i][1] * sy;
      const nearFrame =
        px < edgeNear || py < edgeNear || tw - px < edgeNear || th - py < edgeNear;
      if (!nearFrame) {
        continue;
      }
      const vx = px - cxc;
      const vy = py - cyc;
      const len = Math.hypot(vx, vy) || 1;
      const ux = vx / len;
      const uy = vy / len;
      const qx = px + ux * 18;
      const qy = py + uy * 18;
      let sum = 0;
      let cnt = 0;
      for (let dy = -3; dy <= 3; dy++) {
        for (let dx = -3; dx <= 3; dx++) {
          const ix = (qx + dx) | 0;
          const iy = (qy + dy) | 0;
          if (ix < 0 || ix >= tw || iy < 0 || iy >= th) {
            continue;
          }
          const j = (iy * tw + ix) * 4;
          sum += 0.299 * buf[j] + 0.587 * buf[j + 1] + 0.114 * buf[j + 2];
          cnt++;
        }
      }
      if (cnt > 0 && sum / cnt < 76) {
        hits++;
      }
    }
    return hits;
  }

  /** Bewertet ein Quad: bevorzugt „Blatt im Bild“ statt Vollbild-Rahmen / Tischkante / kleine innere Kästen. */
  function scoreDocumentQuad(pts, w, h) {
    const imgArea = w * h;
    const qa = quadAreaOrdered(pts);
    if (qa < imgArea * 0.012) {
      return -1e9;
    }
    const areaRatio = qa / imgArea;
    if (areaRatio > 0.93) {
      return -1e9;
    }
    if (areaRatio < 0.14) {
      return -1e9;
    }
    if (!isConvexQuadOrdered(pts) || !isPlausiblePerspectiveQuad(pts) || hasExtremeEdgeLengthRatio(pts)) {
      return -1e9;
    }
    if (isLikelyHorizontalFoldArtifact(pts, w, h)) {
      return -1e9;
    }
    const shortSide = Math.min(w, h);
    let minMargin = Infinity;
    for (let i = 0; i < 4; i++) {
      const px = pts[i][0];
      const py = pts[i][1];
      const m = Math.min(px, py, w - px, h - py);
      if (m < minMargin) minMargin = m;
    }
    const xs = pts.map(function (p) {
      return p[0];
    });
    const ys = pts.map(function (p) {
      return p[1];
    });
    const bw = Math.max.apply(null, xs) - Math.min.apply(null, xs);
    const bh = Math.max.apply(null, ys) - Math.min.apply(null, ys);
    const ar = bw > 0 && bh > 0 ? Math.min(bw, bh) / Math.max(bw, bh) : 0;

    let score = Math.log(Math.max(qa, 1)) * 10;
    if (areaRatio > 0.9) score -= 380;
    else if (areaRatio > 0.85) score -= 220;
    else if (areaRatio > 0.8) score -= 100;
    /* Randstrafe abschwächen, wenn das Blatt den Rahmen sinnvoll ausfüllt (sonst gewinnen kleine innere Quads). */
    let marginFactor = 1;
    if (areaRatio > 0.42) {
      marginFactor = 0.22;
    } else if (areaRatio > 0.3) {
      marginFactor = 0.55;
    }
    if (minMargin < shortSide * 0.01) score -= 350 * marginFactor;
    else if (minMargin < shortSide * 0.022) score -= 160 * marginFactor;
    else if (minMargin < shortSide * 0.04) score -= 55 * marginFactor;
    if (ar >= 0.48 && ar <= 0.92) score += 85;
    else if (ar >= 0.35 && ar <= 0.98) score += 35;
    else score -= 70;
    if (areaRatio >= 0.28 && areaRatio <= 0.9) {
      score += 55;
    }
    /* Starke Streuung der Abstände der Ecken zum Bildrand: eine Ecke weit auf Tisch/Blendung gezogen */
    const margins = pts.map(function (p) {
      return Math.min(p[0], p[1], w - p[0], h - p[1]);
    });
    let sumM = 0;
    for (let im = 0; im < 4; im++) {
      sumM += margins[im];
    }
    const meanM = sumM * 0.25;
    let varSum = 0;
    for (let im = 0; im < 4; im++) {
      const d = margins[im] - meanM;
      varSum += d * d;
    }
    const varM = varSum * 0.25;
    if (varM > Math.pow(shortSide * 0.036, 2) && areaRatio > 0.38) {
      score -= 110;
    }
    return score;
  }

  function isQuadInImage(pts, w, h, margin) {
    const shortSide = Math.min(w, h);
    const m =
      margin !== undefined && margin !== null
        ? margin
        : Math.min(80, Math.max(6, shortSide * 0.06));
    for (let i = 0; i < 4; i++) {
      if (pts[i][0] < -m || pts[i][0] > w + m || pts[i][1] < -m || pts[i][1] > h + m) {
        return false;
      }
    }
    return quadAreaOrdered(pts) >= w * h * 0.014;
  }

  function quadFromContour(cnt, w, h, minArea) {
    const area = cv.contourArea(cnt, false);
    if (area < minArea) {
      return null;
    }
    const peri = cv.arcLength(cnt, true);
    const epsilons = [0.01, 0.015, 0.02, 0.025, 0.03, 0.04, 0.05, 0.06, 0.08, 0.1];
    for (let e = 0; e < epsilons.length; e++) {
      const approx = new cv.Mat();
      cv.approxPolyDP(cnt, approx, epsilons[e] * peri, true);
      if (approx.rows === 4) {
        const raw = approxToPoints(approx);
        approx.delete();
        if (raw && raw.length === 4) {
          const ordered = orderPoints(raw);
          if (isQuadInImage(ordered, w, h) && quadAreaOrdered(ordered) <= w * h * 0.905) {
            return ordered;
          }
        }
      } else {
        approx.delete();
      }
    }

    try {
      const rect = cv.minAreaRect(cnt);
      const box = new cv.Mat();
      cv.boxPoints(rect, box);
      const raw = [];
      for (let j = 0; j < 4; j++) {
        raw.push([box.data32F[j * 2], box.data32F[j * 2 + 1]]);
      }
      box.delete();
      const ordered = orderPoints(raw);
      if (isQuadInImage(ordered, w, h) && quadAreaOrdered(ordered) <= w * h * 0.905) {
        return ordered;
      }
    } catch (err) {
      /* optional */
    }
    return null;
  }

  function findBestQuadFromEdges(edges, w, h, minArea) {
    const modes = [cv.RETR_EXTERNAL, cv.RETR_LIST];
    let best = null;
    for (let mi = 0; mi < modes.length; mi++) {
      const contours = new cv.MatVector();
      const hierarchy = new cv.Mat();
      cv.findContours(edges, contours, hierarchy, modes[mi], cv.CHAIN_APPROX_SIMPLE);
      for (let i = 0; i < contours.size(); i++) {
        const cnt = contours.get(i);
        const a = cv.contourArea(cnt, false);
        if (a < minArea) {
          cnt.delete();
          continue;
        }
        const pts = quadFromContour(cnt, w, h, minArea);
        cnt.delete();
        if (pts) {
          const sc = scoreDocumentQuad(pts, w, h);
          if (sc > -1e8 && (!best || sc > best.score)) {
            best = { pts: pts, score: sc };
          }
        }
      }
      hierarchy.delete();
      contours.delete();
    }
    return best;
  }

  function getJscanifyScanner() {
    if (typeof window.jscanify !== 'function') {
      return null;
    }
    if (!state.jscanifyScanner) {
      state.jscanifyScanner = new window.jscanify();
    }
    return state.jscanifyScanner;
  }

  /**
   * jscanify: größte Papierkontur → Ecken; gleiche Downscale-Logik wie Legacy.
   * @param {HTMLCanvasElement} canvasFull
   * @returns {number[][]|null} vier Punkte [tl,tr,br,bl] in Pixeln des canvasFull
   */
  function findDocumentCornersJscanify(canvasFull) {
    if (!state.cvReady || typeof cv === 'undefined') {
      return null;
    }
    const scanner = getJscanifyScanner();
    if (!scanner) {
      return null;
    }

    const maxDim = 1200;
    let scale = 1;
    let src = cv.imread(canvasFull);
    let work = src;
    if (src.cols > maxDim) {
      scale = maxDim / src.cols;
      const dsize = new cv.Size(Math.round(src.cols * scale), Math.round(src.rows * scale));
      work = new cv.Mat();
      cv.resize(src, work, dsize, 0, 0, cv.INTER_AREA);
      src.delete();
    }

    const w = work.cols;
    const h = work.rows;
    let contour = null;
    try {
      contour = scanner.findPaperContour(work);
    } catch (err) {
      work.delete();
      return null;
    }
    if (!contour) {
      work.delete();
      return null;
    }

    let cornersObj;
    try {
      cornersObj = scanner.getCornerPoints(contour);
    } catch (err2) {
      contour.delete();
      work.delete();
      return null;
    }
    contour.delete();

    const tl = cornersObj.topLeftCorner;
    const tr = cornersObj.topRightCorner;
    const br = cornersObj.bottomRightCorner;
    const bl = cornersObj.bottomLeftCorner;
    if (!tl || !tr || !br || !bl) {
      work.delete();
      return null;
    }

    const pts = [
      [tl.x, tl.y],
      [tr.x, tr.y],
      [br.x, br.y],
      [bl.x, bl.y],
    ];

    if (!isQuadInImage(pts, w, h)) {
      work.delete();
      return null;
    }
    const sc = scoreDocumentQuad(pts, w, h);
    const areaRatio = quadAreaOrdered(pts) / (w * h);
    work.delete();
    if (sc <= -1e8 || areaRatio < DOC_QUAD_MIN_AREA_RATIO) {
      return null;
    }

    const inv = 1 / scale;
    return pts.map(function (pt) {
      return [pt[0] * inv, pt[1] * inv];
    });
  }

  /**
   * @param {HTMLCanvasElement} canvasFull
   * @returns {number[][]|null} vier Punkte [tl,tr,br,bl] in Pixeln des canvasFull
   */
  function findDocumentCornersLegacy(canvasFull) {
    if (!state.cvReady || typeof cv === 'undefined') {
      return null;
    }
    const maxDim = 1200;
    let scale = 1;
    let src = cv.imread(canvasFull);
    let work = src;
    if (src.cols > maxDim) {
      scale = maxDim / src.cols;
      const dsize = new cv.Size(Math.round(src.cols * scale), Math.round(src.rows * scale));
      work = new cv.Mat();
      cv.resize(src, work, dsize, 0, 0, cv.INTER_AREA);
      src.delete();
    }

    const w = work.cols;
    const h = work.rows;
    const minArea = w * h * 0.035;

    const gray = new cv.Mat();
    cv.cvtColor(work, gray, cv.COLOR_RGBA2GRAY);

    const pipelines = [];

    function addCannyDilate(low, high, ksize, dilateSize) {
      const blur = new cv.Mat();
      cv.GaussianBlur(gray, blur, new cv.Size(ksize, ksize), 0, 0, cv.BORDER_DEFAULT);
      const edge = new cv.Mat();
      cv.Canny(blur, edge, low, high);
      blur.delete();
      if (dilateSize > 0) {
        const k = cv.getStructuringElement(cv.MORPH_RECT, new cv.Size(dilateSize, dilateSize));
        const dil = new cv.Mat();
        cv.dilate(edge, dil, k);
        k.delete();
        edge.delete();
        pipelines.push(dil);
      } else {
        pipelines.push(edge);
      }
    }

    function addOtsuCloseCanny() {
      const blur = new cv.Mat();
      cv.GaussianBlur(gray, blur, new cv.Size(5, 5), 0);
      const bin = new cv.Mat();
      cv.threshold(blur, bin, 0, 255, cv.THRESH_BINARY + cv.THRESH_OTSU);
      blur.delete();
      const k = cv.getStructuringElement(cv.MORPH_RECT, new cv.Size(3, 3));
      const closed = new cv.Mat();
      cv.morphologyEx(bin, closed, cv.MORPH_CLOSE, k);
      k.delete();
      bin.delete();
      const edge = new cv.Mat();
      cv.Canny(closed, edge, 40, 120);
      closed.delete();
      pipelines.push(edge);
    }

    function addAdaptiveCanny() {
      const blur = new cv.Mat();
      cv.GaussianBlur(gray, blur, new cv.Size(5, 5), 0);
      const bin = new cv.Mat();
      cv.adaptiveThreshold(
        blur,
        bin,
        255,
        cv.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv.THRESH_BINARY,
        15,
        4
      );
      blur.delete();
      const edge = new cv.Mat();
      cv.Canny(bin, edge, 25, 85);
      bin.delete();
      pipelines.push(edge);
    }

    function addEqualizedCanny() {
      const eq = new cv.Mat();
      cv.equalizeHist(gray, eq);
      const blur = new cv.Mat();
      cv.GaussianBlur(eq, blur, new cv.Size(5, 5), 0);
      eq.delete();
      const edge = new cv.Mat();
      cv.Canny(blur, edge, 20, 70);
      blur.delete();
      pipelines.push(edge);
    }

    function addBilateralCanny() {
      const filt = new cv.Mat();
      cv.bilateralFilter(gray, filt, 7, 50, 50);
      const edge = new cv.Mat();
      cv.Canny(filt, edge, 18, 54);
      filt.delete();
      pipelines.push(edge);
    }

    function addClaheCanny() {
      const clOut = new cv.Mat();
      let applied = false;
      try {
        if (typeof cv.createCLAHE === 'function') {
          const clahe = cv.createCLAHE(2.0, new cv.Size(8, 8));
          clahe.apply(gray, clOut);
          applied = true;
        } else if (typeof cv.CLAHE === 'function') {
          const clahe = new cv.CLAHE(2.0, new cv.Size(8, 8));
          clahe.apply(gray, clOut);
          applied = true;
        }
      } catch (err) {
        /* Build ohne CLAHE oder andere API */
      }
      if (!applied) {
        clOut.delete();
        return;
      }
      const blur = new cv.Mat();
      cv.GaussianBlur(clOut, blur, new cv.Size(5, 5), 0);
      clOut.delete();
      const edge = new cv.Mat();
      cv.Canny(blur, edge, 22, 66);
      blur.delete();
      pipelines.push(edge);
    }

    addCannyDilate(20, 60, 5, 3);
    addCannyDilate(30, 90, 5, 3);
    addCannyDilate(50, 150, 5, 0);
    addCannyDilate(40, 120, 7, 5);
    addCannyDilate(15, 45, 5, 5);
    addCannyDilate(10, 40, 5, 5);
    /* Schwache Außenkanten (helles Papier / Untergrund): stärker weichzeichnen + Canny + Dilate */
    addCannyDilate(12, 38, 9, 7);
    addCannyDilate(6, 22, 11, 9);
    try {
      addOtsuCloseCanny();
    } catch (e) {}
    try {
      addAdaptiveCanny();
    } catch (e) {}
    try {
      addEqualizedCanny();
    } catch (e) {}
    try {
      addBilateralCanny();
    } catch (e) {}
    try {
      addClaheCanny();
    } catch (e) {}

    let bestPts = null;
    let bestScore = -Infinity;

    for (let p = 0; p < pipelines.length; p++) {
      const edges = pipelines[p];
      const found = findBestQuadFromEdges(edges, w, h, minArea);
      edges.delete();
      if (found && found.score > bestScore) {
        bestScore = found.score;
        bestPts = found.pts;
      }
    }

    gray.delete();
    work.delete();

    if (!bestPts) {
      return null;
    }

    const inv = 1 / scale;
    const out = bestPts.map(function (pt) {
      return [pt[0] * inv, pt[1] * inv];
    });
    const cw = canvasFull.width;
    const ch = canvasFull.height;
    if (quadAreaOrdered(out) < cw * ch * DOC_QUAD_MIN_AREA_RATIO) {
      return null;
    }
    return out;
  }

  /**
   * Große zusammenhängende Fläche (Otsu + Morphologie + Kanten): hilft bei hellem Papier auf hellem Untergrund.
   * @param {HTMLCanvasElement} canvasFull
   * @returns {number[][]|null}
   */
  function findDocumentCornersBinaryHull(canvasFull) {
    if (!state.cvReady || typeof cv === 'undefined') {
      return null;
    }
    const maxDim = 1200;
    let scale = 1;
    let src = cv.imread(canvasFull);
    let work = src;
    if (src.cols > maxDim) {
      scale = maxDim / src.cols;
      const dsize = new cv.Size(Math.round(src.cols * scale), Math.round(src.rows * scale));
      work = new cv.Mat();
      cv.resize(src, work, dsize, 0, 0, cv.INTER_AREA);
      src.delete();
    }
    const w = work.cols;
    const h = work.rows;
    const minAreaHull = w * h * 0.022;

    const gray = new cv.Mat();
    cv.cvtColor(work, gray, cv.COLOR_RGBA2GRAY);
    const blur = new cv.Mat();
    cv.GaussianBlur(gray, blur, new cv.Size(11, 11), 0);
    const bin = new cv.Mat();
    cv.threshold(blur, bin, 0, 255, cv.THRESH_BINARY + cv.THRESH_OTSU);
    blur.delete();
    gray.delete();
    work.delete();

    let ksz = Math.round(Math.min(w, h) * 0.028);
    if (ksz % 2 === 0) {
      ksz += 1;
    }
    ksz = Math.min(21, Math.max(7, ksz));

    const morphKs = [];
    (function () {
      const seen = {};
      function addK(k0) {
        let kk = k0 | 0;
        if (kk % 2 === 0) {
          kk += 1;
        }
        kk = Math.min(21, Math.max(7, kk));
        if (!seen[kk]) {
          seen[kk] = true;
          morphKs.push(kk);
        }
      }
      addK(ksz);
      addK(ksz - 8);
      addK(ksz + 4);
    })();

    let bestPts = null;
    let bestScore = -Infinity;

    function tryPolarityMorph(inv, kMorph) {
      const prep = new cv.Mat();
      if (inv) {
        cv.bitwise_not(bin, prep);
      } else {
        bin.copyTo(prep);
      }
      const mk = cv.getStructuringElement(cv.MORPH_RECT, new cv.Size(kMorph, kMorph));
      const closed = new cv.Mat();
      cv.morphologyEx(prep, closed, cv.MORPH_CLOSE, mk);
      mk.delete();
      prep.delete();
      const edges = new cv.Mat();
      cv.Canny(closed, edges, 18, 55);
      closed.delete();
      const found = findBestQuadFromEdges(edges, w, h, minAreaHull);
      edges.delete();
      if (found && found.score > bestScore) {
        bestScore = found.score;
        bestPts = found.pts;
      }
    }

    for (let mi = 0; mi < morphKs.length; mi++) {
      tryPolarityMorph(false, morphKs[mi]);
      tryPolarityMorph(true, morphKs[mi]);
    }
    bin.delete();

    if (!bestPts) {
      return null;
    }

    const inv = 1 / scale;
    const out = bestPts.map(function (pt) {
      return [pt[0] * inv, pt[1] * inv];
    });
    const cw = canvasFull.width;
    const ch = canvasFull.height;
    if (quadAreaOrdered(out) < cw * ch * DOC_QUAD_MIN_AREA_RATIO) {
      return null;
    }
    return out;
  }

  /**
   * Kombiniert jscanify, Multi-Canny-Legacy und Binär-/Hull-Pfad; wählt Score plus Kanten-Kontrast
   * (gegen Übergröße auf einheitlichem Untergrund).
   * @param {HTMLCanvasElement} canvasFull
   * @returns {number[][]|null}
   */
  function findDocumentCorners(canvasFull) {
    const cw = canvasFull.width;
    const ch = canvasFull.height;
    const candidates = [];
    const j = findDocumentCornersJscanify(canvasFull);
    if (j) {
      candidates.push(j);
    }
    const leg = findDocumentCornersLegacy(canvasFull);
    if (leg) {
      candidates.push(leg);
    }
    const hull = findDocumentCornersBinaryHull(canvasFull);
    if (hull) {
      candidates.push(hull);
    }

    let best = null;
    let bestCombined = -Infinity;
    for (let i = 0; i < candidates.length; i++) {
      const pts = candidates[i];
      const sc = scoreDocumentQuad(pts, cw, ch);
      const ar = quadAreaOrdered(pts) / (cw * ch);
      if (sc <= -1e8 || ar < DOC_QUAD_MIN_AREA_RATIO * 0.97) {
        continue;
      }
      let bc = 12;
      try {
        bc = borderContrastScore(canvasFull, pts);
      } catch (e2) {
        bc = 12;
      }
      let combined = sc + Math.min(105, bc * 0.55);
      if (ar > 0.5 && bc < 6.8) {
        combined -= 240;
      }
      if (ar > 0.58 && bc < 7.4) {
        combined -= 160;
      }
      if (ar > 0.65 && bc < 8.5) {
        combined -= 145;
      }
      let darkOut = 0;
      try {
        darkOut = countDarkOutwardHitsNearFrame(canvasFull, pts);
      } catch (e3) {
        darkOut = 0;
      }
      if (darkOut >= 2) {
        combined -= 280;
      } else if (darkOut >= 1 && ar > 0.48) {
        combined -= 140;
      }
      if (combined > bestCombined) {
        bestCombined = combined;
        best = pts;
      }
    }
    if (best) {
      return best;
    }
    const order = [leg, hull, j];
    for (let u = 0; u < order.length; u++) {
      const pts = order[u];
      if (!pts) {
        continue;
      }
      if (isLikelyHorizontalFoldArtifact(pts, cw, ch)) {
        continue;
      }
      if (quadAreaOrdered(pts) < cw * ch * 0.12) {
        continue;
      }
      return pts;
    }
    return null;
  }

  function warpPerspectiveFromCorners(srcCanvas, corners) {
    const [tl, tr, br, bl] = corners;
    const widthA = Math.hypot(br[0] - bl[0], br[1] - bl[1]);
    const widthB = Math.hypot(tr[0] - tl[0], tr[1] - tl[1]);
    const maxWidth = Math.max(widthA, widthB);
    const heightA = Math.hypot(tr[0] - br[0], tr[1] - br[1]);
    const heightB = Math.hypot(tl[0] - bl[0], tl[1] - bl[1]);
    const maxHeight = Math.max(heightA, heightB);
    const W = Math.max(32, Math.round(maxWidth));
    const H = Math.max(32, Math.round(maxHeight));

    const src = cv.imread(srcCanvas);
    const dst = new cv.Mat();
    const dsize = new cv.Size(W, H);
    const srcTri = cv.matFromArray(4, 1, cv.CV_32FC2, [
      tl[0], tl[1], tr[0], tr[1], br[0], br[1], bl[0], bl[1],
    ]);
    const dstTri = cv.matFromArray(4, 1, cv.CV_32FC2, [0, 0, W - 1, 0, W - 1, H - 1, 0, H - 1]);
    const M = cv.getPerspectiveTransform(srcTri, dstTri);
    cv.warpPerspective(src, dst, M, dsize, cv.INTER_LINEAR, cv.BORDER_CONSTANT, new cv.Scalar());
    const out = document.createElement('canvas');
    out.width = W;
    out.height = H;
    cv.imshow(out, dst);
    src.delete();
    dst.delete();
    srcTri.delete();
    dstTri.delete();
    M.delete();
    return out;
  }

  function ensureSourceCanvas(w, h) {
    if (!state.sourceCanvas) {
      state.sourceCanvas = document.createElement('canvas');
    }
    state.sourceCanvas.width = w;
    state.sourceCanvas.height = h;
    return state.sourceCanvas;
  }

  function setSourceFromCanvas(c) {
    state.sourceCanvas = c;
    state.corners = defaultCorners(c.width, c.height);
    drawAdjustCanvas();
    el.btnDetect.disabled = false;
    el.btnWarp.disabled = false;
    el.btnResetCorners.disabled = false;
    el.btnSaveImport.disabled = true;
    el.btnDownloadLocal.disabled = true;
    state.warpedCanvas = null;
    el.canvasResult.getContext('2d').clearRect(0, 0, el.canvasResult.width, el.canvasResult.height);
    if (el.saveFilename) {
      el.saveFilename.value = '';
      state.saveFilenameMirror = '';
    }
  }

  function imageToCanvas(img) {
    const c = ensureSourceCanvas(img.naturalWidth || img.width, img.naturalHeight || img.height);
    const ctx = c.getContext('2d');
    ctx.drawImage(img, 0, 0);
    return c;
  }

  function drawAdjustCanvas() {
    const c = state.sourceCanvas;
    const adj = el.canvasAdjust;
    if (!c || !state.corners) {
      return;
    }
    const wrap = el.adjustWrap;
    const maxW = wrap.clientWidth || 800;
    const maxH = 420;
    const pad = ADJUST_VIEW_PADDING;
    const innerW = Math.max(64, maxW - 2 * pad);
    const innerH = Math.max(64, maxH - 2 * pad);
    const scale = Math.min(innerW / c.width, innerH / c.height, 1);
    state.adjustScale = scale;
    state.adjustOffsetX = (maxW - c.width * scale) / 2;
    state.adjustOffsetY = (maxH - c.height * scale) / 2;
    adj.width = maxW;
    adj.height = maxH;
    const ctx = adj.getContext('2d');
    ctx.fillStyle = '#e9ecef';
    ctx.fillRect(0, 0, adj.width, adj.height);
    ctx.save();
    ctx.translate(state.adjustOffsetX, state.adjustOffsetY);
    ctx.scale(scale, scale);
    ctx.drawImage(c, 0, 0);
    ctx.strokeStyle = '#0d6efd';
    ctx.lineWidth = 2 / scale;
    ctx.beginPath();
    const p = state.corners;
    ctx.moveTo(p[0][0], p[0][1]);
    ctx.lineTo(p[1][0], p[1][1]);
    ctx.lineTo(p[2][0], p[2][1]);
    ctx.lineTo(p[3][0], p[3][1]);
    ctx.closePath();
    ctx.stroke();
    const r = 12 / scale;
    ctx.fillStyle = '#0d6efd';
    for (let i = 0; i < 4; i++) {
      ctx.beginPath();
      ctx.arc(p[i][0], p[i][1], r, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = '#fff';
      ctx.lineWidth = 1 / scale;
      ctx.stroke();
    }
    ctx.restore();
  }

  function canvasToImageCoords(clientX, clientY) {
    const rect = el.canvasAdjust.getBoundingClientRect();
    const x = clientX - rect.left;
    const y = clientY - rect.top;
    const ix = (x - state.adjustOffsetX) / state.adjustScale;
    const iy = (y - state.adjustOffsetY) / state.adjustScale;
    return [ix, iy];
  }

  function nearestCornerIndex(ix, iy) {
    let best = -1;
    let bestD = 24 / state.adjustScale;
    bestD *= bestD;
    state.corners.forEach(function (p, i) {
      const dx = p[0] - ix;
      const dy = p[1] - iy;
      const d = dx * dx + dy * dy;
      if (d < bestD) {
        bestD = d;
        best = i;
      }
    });
    return best;
  }

  function applyResultFilters() {
    if (!state.warpedCanvas) return;
    const w = state.warpedCanvas.width;
    const h = state.warpedCanvas.height;
    const out = el.canvasResult;
    out.width = w;
    out.height = h;
    const ctx = out.getContext('2d');
    const br = parseInt(el.rangeBrightness.value, 10) / 100;
    const co = parseInt(el.rangeContrast.value, 10) / 100;
    const rot = parseInt(el.rangeRotate.value, 10);
    const wantGray = el.chkGrayscale.checked;

    ctx.save();
    ctx.translate(w / 2, h / 2);
    ctx.rotate((rot * Math.PI) / 180);
    ctx.translate(-w / 2, -h / 2);
    ctx.drawImage(state.warpedCanvas, 0, 0);
    ctx.restore();

    const imgData = ctx.getImageData(0, 0, w, h);
    const d = imgData.data;
    for (let i = 0; i < d.length; i += 4) {
      let r = d[i];
      let g = d[i + 1];
      let b = d[i + 2];
      r = (r - 128) * co + 128;
      g = (g - 128) * co + 128;
      b = (b - 128) * co + 128;
      r *= br;
      g *= br;
      b *= br;
      r = Math.max(0, Math.min(255, r));
      g = Math.max(0, Math.min(255, g));
      b = Math.max(0, Math.min(255, b));
      if (wantGray) {
        const y = 0.299 * r + 0.587 * g + 0.114 * b;
        d[i] = d[i + 1] = d[i + 2] = y;
      } else {
        d[i] = r;
        d[i + 1] = g;
        d[i + 2] = b;
      }
    }
    ctx.putImageData(imgData, 0, 0);
    el.btnSaveImport.disabled = false;
    el.btnDownloadLocal.disabled = false;
    if (el.saveFilename) {
      if (!el.saveFilename.value.trim()) {
        el.saveFilename.value = 'scan_' + localTimestampForFilename() + '.jpg';
      }
      state.saveFilenameMirror = el.saveFilename.value;
    }
  }

  function suggestedFilename() {
    return 'scan_' + localTimestampForFilename() + '.jpg';
  }

  /** Vom System gesetzter Name „scan_YYYY-MM-DDTHH-MM-SS.jpg“ (bzw. .jpeg). */
  function isGeneratedScanFilenameValue(s) {
    return /^scan_\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}\.(jpe?g)$/i.test(String(s || '').trim());
  }

  /** Aktuellen Wert aus dem Eingabefeld übernehmen (wichtig für Mobilbrowser). */
  function syncFilenameFromDom() {
    if (el.saveFilename) {
      state.saveFilenameMirror = el.saveFilename.value;
    }
  }

  /** @returns {string} Dateiname mit .jpg für Upload/Download */
  function getExportFileName() {
    syncFilenameFromDom();
    const fromInput = el.saveFilename ? String(el.saveFilename.value || '').trim() : '';
    const raw = fromInput || String(state.saveFilenameMirror || '').trim();
    const n = normalizeImportFilename(raw);
    return n || suggestedFilename();
  }

  function normalizeImportFilename(raw) {
    let s = (raw || '').trim();
    if (!s) return null;
    s = s.replace(/[/\\:*?"<>|]/g, '_');
    s = s.replace(/\s+/g, '_');
    if (!/\.(jpe?g)$/i.test(s)) {
      const dot = s.lastIndexOf('.');
      if (dot > 0) {
        s = s.substring(0, dot);
      }
      s = s + '.jpg';
    } else {
      s = s.replace(/\.(jpeg|jpe?g)$/i, '.jpg');
    }
    if (s.length > 200) {
      s = s.substring(0, 196) + '.jpg';
    }
    return s;
  }

  function applyWarpFromCorners() {
    state.warpedCanvas = warpPerspectiveFromCorners(state.sourceCanvas, state.corners);
    applyResultFilters();
  }

  /** Nach Erkennen / Eckpunkt loslassen: Zuschnitt ohne extra Klick (nur wenn OpenCV bereit). */
  function tryAutoWarp() {
    if (!state.sourceCanvas || !state.corners || !state.cvReady || typeof cv === 'undefined') {
      return;
    }
    try {
      applyWarpFromCorners();
    } catch (e) {
      setOpencvStatus('Zuschneiden fehlgeschlagen: ' + (e.message || e), true);
    }
  }

  function onWarp() {
    if (!state.sourceCanvas || !state.corners) return;
    if (!state.cvReady || typeof cv === 'undefined') {
      setOpencvStatus('Bildverarbeitung noch nicht bereit.', true);
      return;
    }
    try {
      applyWarpFromCorners();
    } catch (e) {
      setOpencvStatus('Zuschneiden fehlgeschlagen: ' + (e.message || e), true);
    }
  }

  async function startCamera() {
    hideCameraTapHint();
    try {
      state.stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: 'environment' }, width: { ideal: 1920 } },
        audio: false,
      });
      el.video.srcObject = state.stream;
      el.video.style.display = '';
      el.canvasCapture.style.display = 'none';
      el.videoPlaceholder.style.display = 'none';
      el.btnStopCamera.disabled = false;
      setCaptureButtonsDisabled(false);
      await el.video.play();
    } catch (e) {
      showCameraTapHint();
      setOpencvStatus('Kamera nicht verfügbar: ' + (e.message || e), true);
    }
  }

  function stopCamera() {
    if (state.stream) {
      state.stream.getTracks().forEach(function (t) {
        t.stop();
      });
      state.stream = null;
    }
    el.video.srcObject = null;
    el.video.style.display = 'none';
    el.btnStopCamera.disabled = true;
    setCaptureButtonsDisabled(true);
  }

  function captureFrame() {
    const v = el.video;
    if (!v.videoWidth) return;
    const c = ensureSourceCanvas(v.videoWidth, v.videoHeight);
    const ctx = c.getContext('2d');
    ctx.drawImage(v, 0, 0);
    el.canvasCapture.width = v.videoWidth;
    el.canvasCapture.height = v.videoHeight;
    el.canvasCapture.getContext('2d').drawImage(v, 0, 0);
    el.canvasCapture.style.display = '';
    el.video.style.display = 'none';
    stopCamera();
    setSourceFromCanvas(c);
    onDetect();
  }

  function onFile(e) {
    const f = e.target.files && e.target.files[0];
    if (!f) return;
    const r = new FileReader();
    r.onload = function () {
      const img = new Image();
      img.onload = function () {
        const c = imageToCanvas(img);
        el.canvasCapture.width = c.width;
        el.canvasCapture.height = c.height;
        el.canvasCapture.getContext('2d').drawImage(img, 0, 0);
        el.canvasCapture.style.display = '';
        el.video.style.display = 'none';
        el.videoPlaceholder.style.display = 'none';
        setSourceFromCanvas(c);
        onDetect();
      };
      img.src = r.result;
    };
    r.readAsDataURL(f);
    e.target.value = '';
  }

  function onDetect() {
    if (!state.sourceCanvas) return;
    loadOpenCv()
      .then(function () {
        const found = findDocumentCorners(state.sourceCanvas);
        if (found) {
          state.corners = found;
          setOpencvStatus('Dokument erkannt. Punkte bei Bedarf verschieben.');
        } else {
          state.corners = defaultCorners(state.sourceCanvas.width, state.sourceCanvas.height);
          setOpencvStatus(
            'Kein klarer Dokumentrand erkannt – eingerückter Standardrahmen (an den Rand ziehen oder erneut erkennen).',
            true
          );
        }
        drawAdjustCanvas();
        tryAutoWarp();
      })
      .catch(function () {
        state.corners = defaultCorners(state.sourceCanvas.width, state.sourceCanvas.height);
        drawAdjustCanvas();
        tryAutoWarp();
      });
  }

  function setImportAdjustScrollLock(lock) {
    if (lock) {
      document.documentElement.style.overflow = 'hidden';
      document.body.style.overflow = 'hidden';
      document.body.style.touchAction = 'none';
    } else {
      document.documentElement.style.overflow = '';
      document.body.style.overflow = '';
      document.body.style.touchAction = '';
    }
  }

  function bindAdjustPointer() {
    const adj = el.canvasAdjust;
    const opts = { passive: false };
    function down(ev) {
      const [ix, iy] = canvasToImageCoords(ev.clientX, ev.clientY);
      state.dragIndex = nearestCornerIndex(ix, iy);
      if (state.dragIndex >= 0) {
        ev.preventDefault();
        if (ev.pointerType === 'touch' || ev.pointerType === 'pen') {
          setImportAdjustScrollLock(true);
          state.adjustScrollLockActive = true;
        }
        if (adj.setPointerCapture) {
          try {
            adj.setPointerCapture(ev.pointerId);
          } catch (e) {}
        }
      }
    }
    function move(ev) {
      if (state.dragIndex < 0 || !state.corners || !state.sourceCanvas) return;
      ev.preventDefault();
      let [ix, iy] = canvasToImageCoords(ev.clientX, ev.clientY);
      ix = Math.max(0, Math.min(state.sourceCanvas.width, ix));
      iy = Math.max(0, Math.min(state.sourceCanvas.height, iy));
      state.corners[state.dragIndex] = [ix, iy];
      drawAdjustCanvas();
    }
    function up(ev) {
      const hadCornerDrag = state.dragIndex >= 0;
      if (state.dragIndex >= 0 && state.adjustScrollLockActive) {
        setImportAdjustScrollLock(false);
        state.adjustScrollLockActive = false;
      }
      if (state.dragIndex >= 0 && adj.releasePointerCapture) {
        try {
          adj.releasePointerCapture(ev.pointerId);
        } catch (e) {}
      }
      state.dragIndex = -1;
      if (hadCornerDrag) {
        tryAutoWarp();
      }
    }
    adj.addEventListener('pointerdown', down, opts);
    adj.addEventListener('pointermove', move, opts);
    adj.addEventListener('pointerup', up, opts);
    adj.addEventListener('pointercancel', up, opts);
    adj.addEventListener('pointerleave', function (ev) {
      if (ev.pointerType === 'mouse') up(ev);
    });
  }

  function saveToImport() {
    el.saveMessage.textContent = '';
    if (el.saveFilename) {
      el.saveFilename.blur();
      state.saveFilenameMirror = el.saveFilename.value;
    }
    if (el.filenameFocusSink) {
      try {
        el.filenameFocusSink.focus({ preventScroll: true });
      } catch (e) {
        el.filenameFocusSink.focus();
      }
    }
    function runUpload() {
      syncFilenameFromDom();
      el.canvasResult.toBlob(
        function (blob) {
          if (!blob) {
            el.saveMessage.textContent = 'Kein Bild erzeugbar.';
            el.saveMessage.classList.add('text-danger');
            return;
          }
          syncFilenameFromDom();
          const raw =
            el.saveFilename && el.saveFilename.value != null
              ? String(el.saveFilename.value)
              : String(state.saveFilenameMirror || '');
          state.saveFilenameMirror = raw;
          const name = normalizeImportFilename(raw.trim()) || suggestedFilename();
          const fd = new FormData();
          fd.append('filename', name);
          fd.append('file', blob, 'upload.jpg');
          const url = buildImportUploadUrl(name);
          fetch(url, {
            method: 'POST',
            body: fd,
            credentials: 'same-origin',
            headers: { 'X-Requested-With': 'XMLHttpRequest' },
          })
            .then(function (r) {
              return r.json().then(function (j) {
                return { ok: r.ok, body: j };
              });
            })
            .then(function (_ref) {
              const ok = _ref.ok;
              const body = _ref.body;
              if (ok && body.success) {
                el.saveMessage.textContent = body.message || 'Gespeichert.';
                el.saveMessage.classList.remove('text-danger');
                el.saveMessage.classList.add('text-success');
                refreshDokumentePersonalImportListe();
              } else {
                el.saveMessage.textContent = (body && body.message) || 'Fehler beim Speichern.';
                el.saveMessage.classList.add('text-danger');
              }
            })
            .catch(function () {
              el.saveMessage.textContent = 'Netzwerkfehler beim Speichern.';
              el.saveMessage.classList.add('text-danger');
            });
        },
        'image/jpeg',
        0.92
      );
    }
    scheduleAfterKeyboardFriendly(runUpload);
  }

  function downloadLocal() {
    if (el.saveFilename) {
      el.saveFilename.blur();
      state.saveFilenameMirror = el.saveFilename.value;
    }
    if (el.filenameFocusSink) {
      try {
        el.filenameFocusSink.focus({ preventScroll: true });
      } catch (e) {
        el.filenameFocusSink.focus();
      }
    }
    scheduleAfterKeyboardFriendly(function () {
      syncFilenameFromDom();
      el.canvasResult.toBlob(function (blob) {
        if (!blob) return;
        syncFilenameFromDom();
        const raw =
          el.saveFilename && el.saveFilename.value != null
            ? String(el.saveFilename.value)
            : String(state.saveFilenameMirror || '');
        state.saveFilenameMirror = raw;
        const fname = normalizeImportFilename(raw.trim()) || suggestedFilename();
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = fname;
        a.click();
        URL.revokeObjectURL(a.href);
      }, 'image/jpeg', 0.92);
    });
  }

  el.btnStartCamera.addEventListener('click', startCamera);
  el.btnStopCamera.addEventListener('click', stopCamera);
  el.btnCapture.addEventListener('click', captureFrame);
  if (el.btnCaptureMobile) {
    el.btnCaptureMobile.addEventListener('click', captureFrame);
  }
  el.fileInput.addEventListener('change', onFile);
  el.btnDetect.addEventListener('click', onDetect);
  el.btnWarp.addEventListener('click', onWarp);
  el.btnResetCorners.addEventListener('click', function () {
    if (!state.sourceCanvas) return;
    state.corners = defaultCorners(state.sourceCanvas.width, state.sourceCanvas.height);
    drawAdjustCanvas();
    tryAutoWarp();
  });
  if (el.saveFilename) {
    el.saveFilename.addEventListener('focus', function () {
      if (isGeneratedScanFilenameValue(el.saveFilename.value)) {
        el.saveFilename.value = '';
        state.saveFilenameMirror = '';
      }
    });
    el.saveFilename.addEventListener('input', function () {
      state.saveFilenameMirror = el.saveFilename.value;
    });
    el.saveFilename.addEventListener('change', function () {
      state.saveFilenameMirror = el.saveFilename.value;
    });
    el.saveFilename.addEventListener('blur', function () {
      state.saveFilenameMirror = el.saveFilename.value;
    });
    el.saveFilename.addEventListener('compositionend', function () {
      state.saveFilenameMirror = el.saveFilename.value;
    });
  }

  function bindFilenameSyncPointer(btn) {
    if (!btn) return;
    btn.addEventListener(
      'pointerdown',
      function () {
        syncFilenameFromDom();
      },
      true
    );
  }
  bindFilenameSyncPointer(el.btnSaveImport);
  bindFilenameSyncPointer(el.btnDownloadLocal);

  el.btnSaveImport.addEventListener('click', saveToImport);
  el.btnDownloadLocal.addEventListener('click', downloadLocal);

  ['input', 'change'].forEach(function (ev) {
    el.rangeBrightness.addEventListener(ev, function () {
      el.valBrightness.textContent = el.rangeBrightness.value;
      if (state.warpedCanvas) applyResultFilters();
    });
    el.rangeContrast.addEventListener(ev, function () {
      el.valContrast.textContent = el.rangeContrast.value;
      if (state.warpedCanvas) applyResultFilters();
    });
    el.rangeRotate.addEventListener(ev, function () {
      el.valRotate.textContent = el.rangeRotate.value;
      if (state.warpedCanvas) applyResultFilters();
    });
    el.chkGrayscale.addEventListener(ev, function () {
      if (state.warpedCanvas) applyResultFilters();
    });
  });

  window.addEventListener('resize', function () {
    if (state.sourceCanvas && state.corners) drawAdjustCanvas();
  });

  bindAdjustPointer();

  if (el.collapseBearbeitung && typeof window.bootstrap !== 'undefined' && window.bootstrap.Collapse) {
    el.collapseBearbeitung.addEventListener('shown.bs.collapse', function () {
      if (state.warpedCanvas) {
        applyResultFilters();
      }
    });
  }

  (function bindTapToStartCamera() {
    const wrap = document.querySelector('.doc-capture-frame');
    if (!wrap) return;
    wrap.addEventListener(
      'click',
      function () {
        if (state.stream) return;
        if (el.canvasCapture && el.canvasCapture.style.display !== 'none') return;
        hideCameraTapHint();
        startCamera();
      },
      false
    );
  })();

  /* OpenCV (~10 MB) erst bei erster Erkennung/Zuschneiden laden – vermeidet Timeout beim Seitenstart. */

  function escapeHtml(s) {
    var d = document.createElement('div');
    d.textContent = s == null ? '' : String(s);
    return d.innerHTML;
  }

  function escapeAttr(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/"/g, '&quot;')
      .replace(/</g, '&lt;');
  }

  function refreshDokumentePersonalImportListe() {
    var wrap = el.personalImportListe;
    if (!wrap) return;
    wrap.innerHTML =
      '<div class="text-center py-2"><div class="spinner-border spinner-border-sm text-secondary" role="status"></div></div>';
    fetch('/api/import/dateien', { credentials: 'same-origin' })
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        if (!data.success) {
          wrap.innerHTML =
            '<div class="alert alert-danger mb-0">' + escapeHtml(data.message || 'Fehler beim Laden') + '</div>';
          return;
        }
        var files = data.dateien_personal || [];
        if (files.length === 0) {
          wrap.innerHTML =
            '<p class="text-muted small mb-0">Noch keine Dateien in Ihrem persönlichen Import-Ordner.</p>';
          return;
        }
        var rows = files
          .map(function (f) {
            var name = f.name;
            var left =
              typeof importOrdnerRowLeftHtml === 'function'
                ? importOrdnerRowLeftHtml(name, f.size, 'personal')
                : '<div><strong>' + escapeHtml(name) + '</strong></div>';
            return (
              '<div class="list-group-item py-2">' +
              '<div class="d-flex flex-wrap align-items-center gap-2 justify-content-between">' +
              '<div class="flex-grow-1 min-w-0">' +
              left +
              '</div>' +
              '<div class="d-flex flex-wrap gap-1 align-items-center">' +
              '<button type="button" class="btn btn-sm btn-outline-secondary btn-dokumente-pers-rename" data-filename="' +
              escapeAttr(name) +
              '">Umbenennen</button>' +
              '<button type="button" class="btn btn-sm btn-outline-danger btn-dokumente-pers-delete" data-filename="' +
              escapeAttr(name) +
              '">Löschen</button>' +
              '</div></div>' +
              '<div class="dokumente-pers-rename-row mt-2 d-none">' +
              '<div class="input-group input-group-sm">' +
              '<input type="text" class="form-control dokumente-pers-rename-input" data-original-filename="' +
              escapeAttr(name) +
              '" value="' +
              escapeAttr(name) +
              '" aria-label="Neuer Dateiname">' +
              '<button type="button" class="btn btn-success dokumente-pers-rename-save">Speichern</button>' +
              '<button type="button" class="btn btn-outline-secondary dokumente-pers-rename-cancel">Abbrechen</button>' +
              '</div></div></div>'
            );
          })
          .join('');
        wrap.innerHTML = '<div class="list-group list-group-flush border rounded">' + rows + '</div>';
      })
      .catch(function () {
        wrap.innerHTML = '<div class="alert alert-danger mb-0">Netzwerkfehler beim Laden.</div>';
      });
  }

  if (el.personalImportListe) {
    if (el.btnPersonalImportRefresh) {
      el.btnPersonalImportRefresh.addEventListener('click', refreshDokumentePersonalImportListe);
    }
    el.personalImportListe.addEventListener('click', function (ev) {
      var t = ev.target;
      if (!t || !t.closest) return;
      var delBtn = t.closest('.btn-dokumente-pers-delete');
      if (delBtn) {
        var fn = delBtn.getAttribute('data-filename');
        if (!fn || !confirm('Datei „' + fn + '“ unwiderruflich löschen?')) return;
        fetch('/api/import/personal/loeschen', {
          method: 'POST',
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
          body: JSON.stringify({ filename: fn }),
        })
          .then(function (r) {
            return r.json().then(function (j) {
              return { ok: r.ok, body: j };
            });
          })
          .then(function (x) {
            if (x.ok && x.body.success) refreshDokumentePersonalImportListe();
            else alert((x.body && x.body.message) || 'Löschen fehlgeschlagen');
          })
          .catch(function () {
            alert('Netzwerkfehler');
          });
        return;
      }
      var renBtn = t.closest('.btn-dokumente-pers-rename');
      if (renBtn) {
        var item = renBtn.closest('.list-group-item');
        if (!item) return;
        var row = item.querySelector('.dokumente-pers-rename-row');
        if (row) {
          row.classList.toggle('d-none');
          var inp = row.querySelector('.dokumente-pers-rename-input');
          if (inp && !row.classList.contains('d-none')) inp.focus();
        }
        return;
      }
      var cancelBtn = t.closest('.dokumente-pers-rename-cancel');
      if (cancelBtn) {
        var grp = cancelBtn.closest('.dokumente-pers-rename-row');
        if (grp) grp.classList.add('d-none');
        return;
      }
      var saveBtn = t.closest('.dokumente-pers-rename-save');
      if (saveBtn) {
        var grp2 = saveBtn.closest('.dokumente-pers-rename-row');
        if (!grp2) return;
        var inp2 = grp2.querySelector('.dokumente-pers-rename-input');
        var alt = inp2 ? inp2.getAttribute('data-original-filename') : '';
        var neu = inp2 ? inp2.value.trim() : '';
        if (!alt || !neu) return;
        fetch('/api/import/personal/umbenennen', {
          method: 'POST',
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
          body: JSON.stringify({ alt: alt, neu: neu }),
        })
          .then(function (r) {
            return r.json().then(function (j) {
              return { ok: r.ok, body: j };
            });
          })
          .then(function (x) {
            if (x.ok && x.body.success) refreshDokumentePersonalImportListe();
            else alert((x.body && x.body.message) || 'Umbenennen fehlgeschlagen');
          })
          .catch(function () {
            alert('Netzwerkfehler');
          });
      }
    });
    refreshDokumentePersonalImportListe();
  }

  startCamera();
})();

