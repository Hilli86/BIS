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

  /** POST-URL mit Dateiname in der Query (zuverlässiger als nur multipart auf iOS/Android). */
  function buildImportUploadUrl(filenameEncoded) {
    const sep = UPLOAD_URL.indexOf('?') >= 0 ? '&' : '?';
    return UPLOAD_URL + sep + 'filename=' + encodeURIComponent(filenameEncoded);
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

  function defaultCorners(w, h) {
    const xmax = Math.max(0, w - 1);
    const ymax = Math.max(0, h - 1);
    return [
      [0, 0],
      [xmax, 0],
      [xmax, ymax],
      [0, ymax],
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

  /** Bewertet ein Quad: bevorzugt „Blatt im Bild“ statt Vollbild-Rahmen / Tischkante. */
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
    if (minMargin < shortSide * 0.01) score -= 350;
    else if (minMargin < shortSide * 0.022) score -= 160;
    else if (minMargin < shortSide * 0.04) score -= 55;
    if (ar >= 0.48 && ar <= 0.92) score += 85;
    else if (ar >= 0.35 && ar <= 0.98) score += 35;
    else score -= 70;
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
    return quadAreaOrdered(pts) >= w * h * 0.008;
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

  /**
   * @param {HTMLCanvasElement} canvasFull
   * @returns {number[][]|null} vier Punkte [tl,tr,br,bl] in Pixeln des canvasFull
   */
  function findDocumentCorners(canvasFull) {
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
    const minArea = w * h * 0.015;

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
    return bestPts.map(function (pt) {
      return [pt[0] * inv, pt[1] * inv];
    });
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
          setOpencvStatus('Kein klarer Dokumentrand erkannt – Standardrahmen gesetzt (anpassbar).', true);
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

  startCamera();
})();

