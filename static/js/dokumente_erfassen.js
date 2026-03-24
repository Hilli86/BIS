/**
 * Dokumente erfassen: Kamera/Bild, OpenCV.js Kantenerkennung, Zuschnitt, Bearbeitung, Upload nach Import-Ordner.
 */
(function () {
  'use strict';

  const OPENCV_CDN =
    'https://cdn.jsdelivr.net/npm/@techstark/opencv-js@4.12.0-release.1/dist/opencv.js';

  const boot = document.getElementById('dokumente-erfassen-boot');
  const UPLOAD_URL = boot && boot.dataset.uploadUrl ? boot.dataset.uploadUrl : '/api/import/hochladen';

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
    /** Gespiegelter Dateiname (Mobile: input.value erst nach blur zuverlässig; input-Event aktualisiert sofort) */
    saveFilenameMirror: '',
  };

  function setOpencvStatus(text, isError) {
    if (!el.opencvStatus) return;
    el.opencvStatus.textContent = text || '';
    el.opencvStatus.classList.toggle('text-danger', !!isError);
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
    return new Promise(function (resolve, reject) {
      const script = document.createElement('script');
      script.src = OPENCV_CDN;
      script.async = true;
      script.onload = function () {
        cv['onRuntimeInitialized'] = function () {
          state.cvReady = true;
          setOpencvStatus('Bildverarbeitung bereit.');
          resolve();
        };
      };
      script.onerror = function () {
        setOpencvStatus('OpenCV.js konnte nicht geladen werden. Zuschnitt mit Standardrahmen möglich.', true);
        reject(new Error('opencv load'));
      };
      document.head.appendChild(script);
    });
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
    const m = 0.03;
    return [
      [w * m, h * m],
      [w * (1 - m), h * m],
      [w * (1 - m), h * (1 - m)],
      [w * m, h * (1 - m)],
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

  function isQuadInImage(pts, w, h, margin) {
    const m = margin || 0;
    for (let i = 0; i < 4; i++) {
      if (pts[i][0] < -m || pts[i][0] > w + m || pts[i][1] < -m || pts[i][1] > h + m) {
        return false;
      }
    }
    return quadAreaOrdered(pts) >= w * h * 0.03;
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
          if (isQuadInImage(ordered, w, h, 8)) {
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
      if (isQuadInImage(ordered, w, h, 8)) {
        return ordered;
      }
    } catch (err) {
      /* optional */
    }
    return null;
  }

  function findBestQuadFromEdges(edges, w, h, minArea) {
    const contours = new cv.MatVector();
    const hierarchy = new cv.Mat();
    cv.findContours(edges, contours, hierarchy, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE);

    let best = null;
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
        const qa = quadAreaOrdered(pts);
        if (!best || qa > best.area) {
          best = { pts: pts, area: qa };
        }
      }
    }
    hierarchy.delete();
    contours.delete();
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

    addCannyDilate(20, 60, 5, 3);
    addCannyDilate(30, 90, 5, 3);
    addCannyDilate(50, 150, 5, 0);
    addCannyDilate(40, 120, 7, 5);
    addCannyDilate(15, 45, 5, 5);

    let bestPts = null;
    let bestArea = 0;

    for (let p = 0; p < pipelines.length; p++) {
      const edges = pipelines[p];
      const found = findBestQuadFromEdges(edges, w, h, minArea);
      edges.delete();
      if (found && found.area > bestArea) {
        bestArea = found.area;
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
    const scale = Math.min(maxW / c.width, maxH / c.height, 1);
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

  /** @returns {string} Dateiname mit .jpg für Upload/Download */
  function getExportFileName() {
    const n = normalizeImportFilename(state.saveFilenameMirror || '');
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

  function onWarp() {
    if (!state.sourceCanvas || !state.corners) return;
    try {
      state.warpedCanvas = warpPerspectiveFromCorners(state.sourceCanvas, state.corners);
      applyResultFilters();
    } catch (e) {
      setOpencvStatus('Zuschneiden fehlgeschlagen: ' + (e.message || e), true);
    }
  }

  async function startCamera() {
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
      el.btnCapture.disabled = false;
      await el.video.play();
    } catch (e) {
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
    el.btnCapture.disabled = true;
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
      })
      .catch(function () {
        state.corners = defaultCorners(state.sourceCanvas.width, state.sourceCanvas.height);
        drawAdjustCanvas();
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
        setImportAdjustScrollLock(true);
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
      if (state.dragIndex >= 0) {
        setImportAdjustScrollLock(false);
      }
      if (state.dragIndex >= 0 && adj.releasePointerCapture) {
        try {
          adj.releasePointerCapture(ev.pointerId);
        } catch (e) {}
      }
      state.dragIndex = -1;
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
    window.setTimeout(function () {
      if (el.saveFilename) {
        state.saveFilenameMirror = el.saveFilename.value;
      }
      el.canvasResult.toBlob(
        function (blob) {
          if (!blob) {
            el.saveMessage.textContent = 'Kein Bild erzeugbar.';
            el.saveMessage.classList.add('text-danger');
            return;
          }
          const name = getExportFileName();
          const fd = new FormData();
          fd.append('file', blob, name);
          fetch(UPLOAD_URL, {
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
    }, 0);
  }

  function downloadLocal() {
    if (el.saveFilename) {
      el.saveFilename.blur();
      state.saveFilenameMirror = el.saveFilename.value;
    }
    window.setTimeout(function () {
      if (el.saveFilename) {
        state.saveFilenameMirror = el.saveFilename.value;
      }
      el.canvasResult.toBlob(function (blob) {
        if (!blob) return;
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = getExportFileName();
        a.click();
        URL.revokeObjectURL(a.href);
      }, 'image/jpeg', 0.92);
    }, 0);
  }

  el.btnStartCamera.addEventListener('click', startCamera);
  el.btnStopCamera.addEventListener('click', stopCamera);
  el.btnCapture.addEventListener('click', captureFrame);
  el.fileInput.addEventListener('change', onFile);
  el.btnDetect.addEventListener('click', onDetect);
  el.btnWarp.addEventListener('click', onWarp);
  el.btnResetCorners.addEventListener('click', function () {
    if (!state.sourceCanvas) return;
    state.corners = defaultCorners(state.sourceCanvas.width, state.sourceCanvas.height);
    drawAdjustCanvas();
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
  }

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

  loadOpenCv().catch(function () {});
})();

