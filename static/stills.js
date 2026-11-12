/* Picture video: still pictures, a short caption on each, then one portrait MP4. */
(function () {
  "use strict";

  const MAX_PICTURES = 12;
  const MAX_FILE_BYTES = 12 * 1024 * 1024;
  const MAX_JPEG_BYTES = 2400000;
  const SHOT_SECONDS = 3.6;
  const TYPES = new Set(["jpg", "jpeg", "png", "webp", "gif", "svg"]);
  const W = 1080;
  const H = 1350;
  const FONT = '"Avenir Next", "Segoe UI", "Helvetica Neue", sans-serif';

  const fileInput = document.querySelector("#stills-files");
  const list = document.querySelector("#stills-list");
  const status = document.querySelector("#stills-status");
  const card = document.querySelector("#stills-card");
  const playButton = document.querySelector("#stills-play");
  const downloadButton = document.querySelector("#stills-download");
  const progress = document.querySelector("#stills-progress");
  const empty = document.querySelector("#stills-empty");
  const canvas = document.querySelector("#stills-canvas");
  const caption = document.querySelector("#stills-caption");
  const videoNote = document.querySelector("#stills-video-note");

  let shots = [];
  let ffmpeg = false;
  let ffmpegKnown = false;
  let busy = false;
  let playToken = 0;

  function isStillsMode() {
    const picked = document.querySelector('input[name="mode"]:checked');
    return Boolean(picked && picked.value === "stills");
  }

  function extension(name) {
    const base = String(name || "").split(/[/\\]/).pop() || "";
    const dot = base.lastIndexOf(".");
    return dot === -1 ? "" : base.slice(dot + 1).toLowerCase();
  }

  function note(message) {
    status.textContent = message;
  }

  function pad(index) {
    return String(index).padStart(2, "0");
  }

  function refreshButtons() {
    const ready = shots.length > 0 && !busy;
    fileInput.disabled = busy;
    playButton.disabled = !ready;
    downloadButton.hidden = !ffmpeg;
    downloadButton.disabled = !ready;
    videoNote.hidden = !ffmpegKnown || ffmpeg;
    shots.forEach((shot) => {
      shot.input.disabled = busy;
      shot.remove.disabled = busy;
    });
  }

  function showCard(on) {
    card.dataset.ready = on ? "1" : "0";
    card.hidden = !on || !isStillsMode();
  }

  function renderList() {
    list.replaceChildren();
    shots.forEach((shot, index) => {
      const item = document.createElement("li");
      const preview = document.createElement("img");
      preview.src = shot.url;
      preview.alt = "";
      shot.input.setAttribute("aria-label", `Caption for picture ${index + 1}`);
      shot.input.placeholder = "Short caption";
      item.append(preview, shot.input, shot.remove);
      list.append(item);
    });
    showCard(shots.length > 0);
    if (shots.length) showStill();
  }

  function loadImage(file) {
    return new Promise((resolve, reject) => {
      const url = URL.createObjectURL(file);
      const image = new Image();
      image.onload = () => resolve({ image, url });
      image.onerror = () => {
        URL.revokeObjectURL(url);
        reject(new Error(`${file.name} could not be read. Use a JPEG, PNG, WEBP, GIF, or SVG.`));
      };
      image.src = url;
    });
  }

  async function addFiles(selected) {
    const incoming = Array.from(selected || []);
    if (!incoming.length) return;
    for (const file of incoming) {
      if (shots.length >= MAX_PICTURES) {
        note(`Use ${MAX_PICTURES} pictures or fewer.`);
        break;
      }
      if (!TYPES.has(extension(file.name))) {
        note(`${file.name} is not a JPEG, PNG, WEBP, GIF, or SVG.`);
        continue;
      }
      if (file.size <= 0 || file.size > MAX_FILE_BYTES) {
        note(`${file.name} is over 12 MB.`);
        continue;
      }
      try {
        const loaded = await loadImage(file);
        const input = document.createElement("input");
        input.type = "text";
        input.maxLength = 90;
        input.autocomplete = "off";
        input.addEventListener("input", () => {
          if (!busy) showStill();
        });
        const remove = document.createElement("button");
        remove.type = "button";
        remove.textContent = "Remove";
        const shot = { image: loaded.image, url: loaded.url, input, remove };
        remove.addEventListener("click", () => {
          URL.revokeObjectURL(shot.url);
          shots = shots.filter((item) => item !== shot);
          renderList();
          refreshButtons();
          note(shots.length ? `${shots.length} pictures ready.` : "Add pictures, then write a caption for each.");
        });
        shots.push(shot);
      } catch (error) {
        note(error.message);
      }
    }
    fileInput.value = "";
    renderList();
    refreshButtons();
    if (shots.length) note(`${shots.length} ${shots.length === 1 ? "picture" : "pictures"} ready.`);
  }

  function wrap(ctx, text, maxWidth, maxLines, size) {
    ctx.font = `600 ${size}px ${FONT}`;
    const words = String(text || "").split(/\s+/).filter(Boolean);
    const lines = [];
    let current = "";
    for (const word of words) {
      const trial = current ? `${current} ${word}` : word;
      if (current && ctx.measureText(trial).width > maxWidth) {
        lines.push(current);
        current = word;
        if (lines.length === maxLines) return lines;
      } else {
        current = trial;
      }
    }
    if (current && lines.length < maxLines) lines.push(current);
    return lines;
  }

  function drawPhoto(ctx, image, time) {
    const zoom = 1 + 0.08 * Math.max(0, Math.min(1, time / SHOT_SECONDS));
    const width = image.naturalWidth || image.width;
    const height = image.naturalHeight || image.height;
    const base = Math.max(W / width, H / height) * zoom;
    const dw = width * base;
    const dh = height * base;
    const drift = (time / SHOT_SECONDS - 0.5) * 28;
    ctx.fillStyle = "#050d16";
    ctx.fillRect(0, 0, W, H);
    ctx.drawImage(image, (W - dw) / 2 + drift, (H - dh) / 2, dw, dh);
  }

  function drawCaption(ctx, text) {
    const words = String(text || "").trim();
    if (!words) return;
    const shade = ctx.createLinearGradient(0, H - 460, 0, H);
    shade.addColorStop(0, "rgba(5, 13, 22, 0)");
    shade.addColorStop(1, "rgba(5, 13, 22, 0.82)");
    ctx.fillStyle = shade;
    ctx.fillRect(0, H - 460, W, 460);
    const lines = wrap(ctx, words, W - 168, 3, 48);
    ctx.font = `600 48px ${FONT}`;
    ctx.fillStyle = "#f7fbfe";
    ctx.textBaseline = "top";
    let y = H - 156 - lines.length * 58;
    for (const line of lines) {
      ctx.fillText(line, 84, y);
      y += 58;
    }
  }

  function drawShot(ctx, image, text, time) {
    drawPhoto(ctx, image, time);
    drawCaption(ctx, text);
    const fadeIn = 1 - Math.min(1, time / 0.28);
    const fadeOut = Math.max(0, (time - (SHOT_SECONDS - 0.28)) / 0.28);
    const fade = Math.max(fadeIn, fadeOut);
    if (fade > 0.01) {
      ctx.globalAlpha = fade;
      ctx.fillStyle = "#050d16";
      ctx.fillRect(0, 0, W, H);
      ctx.globalAlpha = 1;
    }
  }

  function context() {
    canvas.width = W;
    canvas.height = H;
    return canvas.getContext("2d", { alpha: false });
  }

  function showStill() {
    if (!shots.length || !canvas) return;
    const ctx = context();
    if (!ctx) return;
    drawShot(ctx, shots[0].image, shots[0].input.value, 1.2);
    canvas.hidden = false;
    empty.hidden = true;
    caption.textContent = shots[0].input.value.trim();
  }

  function stopPlayback() {
    playToken += 1;
  }

  function play() {
    if (busy || !shots.length) return;
    stopPlayback();
    const run = playToken;
    const ctx = context();
    if (!ctx) return;
    let step = 0;
    let started = performance.now();
    const frame = (now) => {
      if (run !== playToken) return;
      let time = (now - started) / 1000;
      if (time >= SHOT_SECONDS && step < shots.length - 1) {
        step += 1;
        started = now;
        time = 0;
      }
      time = Math.min(time, SHOT_SECONDS);
      drawShot(ctx, shots[step].image, shots[step].input.value, time);
      caption.textContent = shots[step].input.value.trim();
      if (step < shots.length - 1 || time < SHOT_SECONDS) requestAnimationFrame(frame);
    };
    canvas.hidden = false;
    empty.hidden = true;
    requestAnimationFrame(frame);
  }

  function blobOf(target, type, quality) {
    return new Promise((resolve, reject) => {
      target.toBlob((blob) => {
        if (!blob) reject(new Error("A picture could not be prepared."));
        else resolve(blob);
      }, type, quality);
    });
  }

  async function photoJpeg(image) {
    const width = image.naturalWidth || image.width;
    const height = image.naturalHeight || image.height;
    const edge = Math.max(width, height);
    const scale = Math.min(1, 2000 / edge);
    const target = document.createElement("canvas");
    target.width = Math.max(2, Math.round(width * scale));
    target.height = Math.max(2, Math.round(height * scale));
    const ctx = target.getContext("2d", { alpha: false });
    ctx.fillStyle = "#050d16";
    ctx.fillRect(0, 0, target.width, target.height);
    ctx.drawImage(image, 0, 0, target.width, target.height);
    let quality = 0.86;
    let blob = await blobOf(target, "image/jpeg", quality);
    while (blob.size > MAX_JPEG_BYTES && quality > 0.5) {
      quality -= 0.12;
      blob = await blobOf(target, "image/jpeg", quality);
    }
    if (blob.size > 2500000) throw new Error("One picture is too large. Try a smaller one.");
    return blob;
  }

  async function captionPng(text) {
    const target = document.createElement("canvas");
    target.width = W;
    target.height = H;
    const ctx = target.getContext("2d", { alpha: true });
    drawCaption(ctx, text);
    return blobOf(target, "image/png");
  }

  function saveBlob(blob, name) {
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = name;
    link.click();
    setTimeout(() => URL.revokeObjectURL(link.href), 1500);
  }

  async function download() {
    if (busy || !shots.length) return;
    stopPlayback();
    busy = true;
    refreshButtons();
    progress.textContent = "Preparing the pictures";
    try {
      const body = new FormData();
      for (let index = 0; index < shots.length; index += 1) {
        const number = pad(index + 1);
        progress.textContent = `Preparing picture ${index + 1} of ${shots.length}`;
        body.append("stills", await photoJpeg(shots[index].image), `still-${number}.jpg`);
        const text = shots[index].input.value.trim();
        if (text) body.append("captions", await captionPng(text), `caption-${number}.png`);
        await new Promise((resolve) => setTimeout(resolve, 0));
      }
      progress.textContent = "Making the video";
      const response = await fetch("/api/stills", { method: "POST", body });
      if (!response.ok) {
        const failure = await response.json().catch(() => ({}));
        throw new Error(failure.error || "The video could not be made.");
      }
      saveBlob(await response.blob(), "picture-video.mp4");
      showStill();
      progress.textContent = "Saved the video.";
    } catch (error) {
      progress.textContent = error.message || "The video could not be made.";
    } finally {
      busy = false;
      refreshButtons();
    }
  }

  fileInput.addEventListener("change", () => addFiles(fileInput.files));
  playButton.addEventListener("click", play);
  downloadButton.addEventListener("click", download);
  document.querySelectorAll('input[name="mode"]').forEach((input) => {
    input.addEventListener("change", () => {
      if (!isStillsMode()) stopPlayback();
      if (isStillsMode() && card.dataset.ready === "1") card.hidden = false;
    });
  });

  function setFfmpeg(available) {
    ffmpeg = Boolean(available);
    ffmpegKnown = true;
    refreshButtons();
  }

  refreshButtons();
  window.LinkedInStills = { setFfmpeg, isStillsMode, download };
})();
