/* Post via Pics: the local model reads the pictures, you edit the post, then the video plays those pictures. */
(function () {
  "use strict";

  const MAX_PICTURES = 10;
  const MAX_FILE_BYTES = 12 * 1024 * 1024;
  const SHOT_SECONDS = 8;
  const TRANSITION_SECONDS = 0.7;
  const TRANSITIONS = new Set(["crossfade", "slide", "wipe", "push", "zoom"]);
  const TYPES = new Set(["jpg", "jpeg", "png", "webp", "gif", "svg"]);
  const FONT = '"Avenir Next", "Segoe UI", "Helvetica Neue", sans-serif';

  const fileInput = document.querySelector("#pics-files");
  const list = document.querySelector("#pics-list");
  const readButton = document.querySelector("#read-pictures");
  const status = document.querySelector("#pics-status");
  const card = document.querySelector("#pics-card");
  const postInput = document.querySelector("#pics-post");
  const count = document.querySelector("#pics-count");
  const copyButton = document.querySelector("#pics-copy");
  const playButton = document.querySelector("#pics-play");
  const downloadButton = document.querySelector("#pics-download");
  const progress = document.querySelector("#pics-progress");
  const empty = document.querySelector("#pics-empty");
  const canvas = document.querySelector("#pics-canvas");
  const caption = document.querySelector("#pics-caption");
  const videoNote = document.querySelector("#pics-video-note");
  const modelSelect = document.querySelector("#pics-model");
  const instructions = document.querySelector("#pics-instructions");
  const transitionSelect = document.querySelector("#pics-transition");
  const musicInput = document.querySelector("#pics-music");

  let stage = { w: 1080, h: 1350, wide: false };

  let shots = [];
  let snapshot = "";
  let ffmpeg = false;
  let ffmpegKnown = false;
  let busy = false;
  let playToken = 0;

  function isPicsMode() {
    const picked = document.querySelector('input[name="mode"]:checked');
    return Boolean(picked && picked.value === "pics");
  }

  function extension(name) {
    const base = String(name || "").split(/[/\\]/).pop() || "";
    const dot = base.lastIndexOf(".");
    return dot === -1 ? "" : base.slice(dot + 1).toLowerCase();
  }

  function note(message) {
    status.textContent = message;
  }

  function words(text) {
    const trimmed = String(text || "").trim();
    if (!trimmed) return "";
    return `${trimmed.split(/\s+/).length} words`;
  }

  function signature() {
    return shots
      .map((shot) => `${shot.file.name}:${shot.file.size}:${shot.file.lastModified}`)
      .sort()
      .join("|");
  }

  function stale() {
    return Boolean(snapshot) && signature() !== snapshot;
  }

  function captionsFor(post, total) {
    const sentences = String(post || "")
      .split(/(?<=[.!?])\s+/)
      .map((sentence) => sentence.trim())
      .filter(Boolean);
    const groups = Array.from({ length: total }, () => []);
    if (!sentences.length || !total) return groups.map(() => "");
    sentences.forEach((sentence, index) => {
      const at = Math.min(total - 1, Math.floor((index * total) / sentences.length));
      groups[at].push(sentence);
    });
    return groups.map((group) => group.join(" "));
  }

  function refreshButtons() {
    const ready = shots.length > 0 && postInput.value.trim() && !busy && !stale();
    readButton.disabled = busy || shots.length === 0;
    fileInput.disabled = busy;
    postInput.disabled = busy;
    copyButton.disabled = busy || !postInput.value.trim();
    playButton.disabled = !ready;
    downloadButton.hidden = !ffmpeg;
    downloadButton.disabled = !ready;
    videoNote.hidden = !ffmpegKnown || ffmpeg;
    count.textContent = words(postInput.value);
    if (transitionSelect) transitionSelect.disabled = busy;
    if (musicInput) musicInput.disabled = busy;
  }

  function showCard(on) {
    card.dataset.ready = on ? "1" : "0";
    card.hidden = !on || !isPicsMode();
  }

  let dragFrom = null;

  function shotIndex(value) {
    const text = String(value == null ? "" : value);
    if (!/^\d+$/.test(text)) return -1;
    const index = Number(text);
    return index < shots.length ? index : -1;
  }

  function afterSequenceChange() {
    stopPlayback();
    renderList();
    refreshButtons();
    if (stale()) {
      note("Read the pictures again so the post matches this set.");
      return;
    }
    if (!postInput.value.trim()) return;
    showStill();
    if (snapshot) note("The video now follows this order. Read the pictures again if the post should be rewritten for it.");
  }

  function moveShot(from, to) {
    if (busy || from === to) return;
    if (shotIndex(from) !== from || shotIndex(to) !== to) return;
    const [shot] = shots.splice(from, 1);
    shots.splice(to, 0, shot);
    afterSequenceChange();
  }

  function renderList() {
    list.replaceChildren();
    dragFrom = null;
    shots.forEach((shot, index) => {
      const item = document.createElement("li");
      const grip = document.createElement("span");
      grip.className = "pics-grip";
      grip.textContent = "⋮⋮";
      grip.title = "Drag to reorder";
      grip.setAttribute("aria-hidden", "true");
      grip.draggable = !busy;
      const preview = document.createElement("img");
      preview.src = shot.url;
      preview.alt = "";
      preview.draggable = false;
      const label = document.createElement("span");
      label.className = "pics-name";
      label.textContent = `Picture ${index + 1}`;
      const controls = document.createElement("span");
      controls.className = "pics-controls";
      const up = document.createElement("button");
      up.type = "button";
      up.textContent = "Up";
      up.setAttribute("aria-label", `Move picture ${index + 1} earlier`);
      up.disabled = busy || index === 0;
      up.addEventListener("click", () => moveShot(index, index - 1));
      const down = document.createElement("button");
      down.type = "button";
      down.textContent = "Down";
      down.setAttribute("aria-label", `Move picture ${index + 1} later`);
      down.disabled = busy || index === shots.length - 1;
      down.addEventListener("click", () => moveShot(index, index + 1));
      const remove = document.createElement("button");
      remove.type = "button";
      remove.textContent = "Remove";
      remove.disabled = busy;
      remove.addEventListener("click", () => {
        if (busy) return;
        URL.revokeObjectURL(shot.url);
        shots.splice(index, 1);
        afterSequenceChange();
      });
      grip.addEventListener("dragstart", (event) => {
        if (busy || !event.dataTransfer) return;
        dragFrom = index;
        event.dataTransfer.effectAllowed = "move";
        event.dataTransfer.setData("text/plain", String(index));
        item.classList.add("is-dragging");
      });
      item.addEventListener("dragover", (event) => {
        if (dragFrom === null || dragFrom === index) return;
        event.preventDefault();
        if (event.dataTransfer) event.dataTransfer.dropEffect = "move";
        item.classList.add("is-drop");
      });
      item.addEventListener("dragleave", () => item.classList.remove("is-drop"));
      item.addEventListener("drop", (event) => {
        event.preventDefault();
        item.classList.remove("is-drop");
        const from = dragFrom;
        dragFrom = null;
        if (from === null) return;
        moveShot(from, index);
      });
      grip.addEventListener("dragend", () => {
        dragFrom = null;
        item.classList.remove("is-dragging");
        list.querySelectorAll(".is-drop").forEach((row) => row.classList.remove("is-drop"));
      });
      controls.append(up, down, remove);
      item.append(grip, preview, label, controls);
      list.append(item);
    });
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

  let adding = Promise.resolve();

  function addFiles(selected) {
    const incoming = Array.from(selected || []);
    if (!incoming.length) return adding;
    const run = adding.then(() => ingest(incoming));
    adding = run.catch(() => {});
    return run;
  }

  async function ingest(incoming) {
    let capped = false;
    for (const file of incoming) {
      if (shots.length >= MAX_PICTURES) {
        capped = true;
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
        if (shots.length >= MAX_PICTURES) {
          URL.revokeObjectURL(loaded.url);
          capped = true;
          break;
        }
        shots.push({ file, image: loaded.image, url: loaded.url });
      } catch (error) {
        note(error.message);
      }
    }
    fileInput.value = "";
    renderList();
    refreshButtons();
    if (stale()) note("Read the pictures again so the post matches this set.");
    else if (capped) note(`Use ${MAX_PICTURES} pictures or fewer. The first ${MAX_PICTURES} are ready.`);
    else if (shots.length) note(`${shots.length} ${shots.length === 1 ? "picture" : "pictures"} ready.`);
  }

  function modelJpeg(image) {
    const edge = Math.max(image.naturalWidth || image.width, image.naturalHeight || image.height);
    const scale = Math.min(1, 1024 / edge);
    const target = document.createElement("canvas");
    target.width = Math.max(1, Math.round((image.naturalWidth || image.width) * scale));
    target.height = Math.max(1, Math.round((image.naturalHeight || image.height) * scale));
    const ctx = target.getContext("2d", { alpha: false });
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, target.width, target.height);
    ctx.drawImage(image, 0, 0, target.width, target.height);
    return new Promise((resolve, reject) => {
      target.toBlob((blob) => {
        if (!blob) reject(new Error("A picture could not be prepared."));
        else resolve(blob);
      }, "image/jpeg", 0.82);
    });
  }

  async function readPictures() {
    if (busy || !shots.length) {
      if (!shots.length) note("Add at least one picture.");
      return;
    }
    busy = true;
    stopPlayback();
    refreshButtons();
    note("Reading the pictures on this laptop");
    try {
      const body = new FormData();
      body.set("model", modelSelect.value);
      body.set("instructions", instructions.value);
      for (let index = 0; index < shots.length; index += 1) {
        const blob = await modelJpeg(shots[index].image);
        body.append("pictures", blob, `picture-${String(index + 1).padStart(2, "0")}.jpg`);
      }
      const response = await fetch("/api/pictures", { method: "POST", body });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || "The pictures could not be read.");
      if (!data.post) throw new Error("The pictures could not be read.");
      postInput.value = data.post;
      snapshot = signature();
      showCard(true);
      showStill();
      note("Edit the post, then play it over the pictures or download the video.");
      progress.textContent = "";
    } catch (error) {
      note(error.message || "The pictures could not be read.");
    } finally {
      busy = false;
      refreshButtons();
    }
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

  function imageSize(image) {
    return {
      w: image.naturalWidth || image.width,
      h: image.naturalHeight || image.height,
    };
  }

  function chooseStage() {
    const wideCount = shots.filter((shot) => {
      const size = imageSize(shot.image);
      return size.w > size.h;
    }).length;
    const wide = shots.length > 0 && wideCount * 2 >= shots.length;
    stage = wide ? { w: 1920, h: 1080, wide: true } : { w: 1080, h: 1350, wide: false };
    canvas.classList.toggle("wide", stage.wide);
  }

  function transitionName() {
    const value = transitionSelect ? transitionSelect.value : "crossfade";
    return TRANSITIONS.has(value) ? value : "crossfade";
  }

  function musicOn() {
    return Boolean(musicInput && musicInput.checked);
  }

  function smooth(value) {
    const u = Math.max(0, Math.min(1, value));
    return u * u * (3 - 2 * u);
  }

  function fitBox(image, zoom) {
    const size = imageSize(image);
    const scale = Math.min(stage.w / size.w, stage.h / size.h) * zoom;
    const dw = size.w * scale;
    const dh = size.h * scale;
    return { x: (stage.w - dw) / 2, y: (stage.h - dh) / 2, dw, dh };
  }

  function plate(ctx, image, zoom) {
    const size = imageSize(image);
    const cover = Math.max(stage.w / size.w, stage.h / size.h) * 1.12;
    ctx.fillStyle = "#050d16";
    ctx.fillRect(0, 0, stage.w, stage.h);
    ctx.save();
    ctx.filter = "blur(22px)";
    ctx.drawImage(
      image,
      (stage.w - size.w * cover) / 2,
      (stage.h - size.h * cover) / 2,
      size.w * cover,
      size.h * cover,
    );
    ctx.restore();
    ctx.fillStyle = "rgba(5, 13, 22, 0.42)";
    ctx.fillRect(0, 0, stage.w, stage.h);
    const box = fitBox(image, zoom);
    ctx.drawImage(image, box.x, box.y, box.dw, box.dh);
  }

  function drawShot(ctx, image, text, time, index, total, previous) {
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.globalAlpha = 1;
    ctx.filter = "none";
    const zoom = 0.97 + 0.03 * Math.max(0, Math.min(1, time / SHOT_SECONDS));
    const opening = previous && index > 0 && time < TRANSITION_SECONDS;
    const u = smooth(time / TRANSITION_SECONDS);
    const name = transitionName();
    if (!opening) {
      plate(ctx, image, zoom);
    } else if (name === "slide") {
      plate(ctx, previous, 1);
      ctx.save();
      ctx.translate(stage.w * (1 - u), 0);
      plate(ctx, image, zoom);
      ctx.restore();
    } else if (name === "wipe") {
      plate(ctx, previous, 1);
      ctx.save();
      ctx.beginPath();
      ctx.rect(0, 0, stage.w * u, stage.h);
      ctx.clip();
      plate(ctx, image, zoom);
      ctx.restore();
    } else if (name === "push") {
      ctx.save();
      ctx.translate(-stage.w * u, 0);
      plate(ctx, previous, 1);
      ctx.restore();
      ctx.save();
      ctx.translate(stage.w * (1 - u), 0);
      plate(ctx, image, zoom);
      ctx.restore();
    } else if (name === "zoom") {
      ctx.save();
      ctx.translate(stage.w / 2, stage.h / 2);
      ctx.scale(1 + 0.08 * u, 1 + 0.08 * u);
      ctx.translate(-stage.w / 2, -stage.h / 2);
      ctx.globalAlpha = 1 - u;
      plate(ctx, previous, 1);
      ctx.restore();
      ctx.save();
      ctx.globalAlpha = u;
      plate(ctx, image, zoom);
      ctx.restore();
    } else {
      plate(ctx, previous, 1);
      ctx.save();
      ctx.globalAlpha = u;
      plate(ctx, image, zoom);
      ctx.restore();
    }
    const typeSize = stage.wide ? 40 : 36;
    const lines = wrap(ctx, text, stage.w - 144, 4, typeSize);
    const lineH = typeSize + 10;
    const textTop = stage.h - 78 - lines.length * lineH;
    const shadeTop = Math.max(0, textTop - 28);
    const shade = ctx.createLinearGradient(0, shadeTop, 0, stage.h);
    shade.addColorStop(0, "rgba(5, 13, 22, 0)");
    shade.addColorStop(1, "rgba(5, 13, 22, 0.88)");
    ctx.fillStyle = shade;
    ctx.fillRect(0, shadeTop, stage.w, stage.h - shadeTop);
    ctx.fillStyle = "#f7fbfe";
    ctx.textBaseline = "top";
    let y = textTop;
    for (const line of lines) {
      ctx.fillText(line, 72, y);
      y += lineH;
    }
    if (total > 1) {
      const gap = 14;
      const dot = 10;
      const wide = 34;
      const span = (total - 1) * (dot + gap) + wide;
      let x = stage.w / 2 - span / 2;
      for (let step = 1; step <= total; step += 1) {
        const current = step === index + 1;
        ctx.fillStyle = current ? "#5ec4ef" : "rgba(150, 190, 214, 0.45)";
        const mark = current ? wide : dot;
        ctx.fillRect(x, stage.h - 42, mark, dot);
        x += mark + gap;
      }
    }
    const fadeIn = index === 0 ? 1 - Math.min(1, time / 0.4) : 0;
    const fadeOut = index === total - 1 ? Math.max(0, (time - (SHOT_SECONDS - 0.45)) / 0.45) : 0;
    const fade = Math.max(fadeIn, fadeOut);
    if (fade > 0.01) {
      ctx.globalAlpha = fade;
      ctx.fillStyle = "#050d16";
      ctx.fillRect(0, 0, stage.w, stage.h);
      ctx.globalAlpha = 1;
    }
  }

  function context(target) {
    const surface = target || canvas;
    surface.width = stage.w;
    surface.height = stage.h;
    return surface.getContext("2d", { alpha: false });
  }

  function showStill() {
    if (!shots.length || !canvas) return;
    chooseStage();
    const ctx = context();
    if (!ctx) return;
    const lines = captionsFor(postInput.value, shots.length);
    drawShot(ctx, shots[0].image, lines[0], SHOT_SECONDS - 0.5, 0, shots.length, null);
    canvas.hidden = false;
    empty.hidden = true;
    caption.textContent = lines[0] || "";
  }

  function stopPlayback() {
    playToken += 1;
  }

  function play() {
    if (busy || stale() || !shots.length || !postInput.value.trim()) return;
    stopPlayback();
    chooseStage();
    const run = playToken;
    const lines = captionsFor(postInput.value, shots.length);
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
      const previous = step > 0 ? shots[step - 1].image : null;
      drawShot(ctx, shots[step].image, lines[step], time, step, shots.length, previous);
      caption.textContent = lines[step] || "";
      if (step < shots.length - 1 || time < SHOT_SECONDS) requestAnimationFrame(frame);
    };
    canvas.hidden = false;
    empty.hidden = true;
    requestAnimationFrame(frame);
  }

  function blobOf(target) {
    return new Promise((resolve, reject) => {
      target.toBlob((blob) => {
        if (!blob) reject(new Error("A frame could not be drawn."));
        else resolve(blob);
      }, "image/jpeg", 0.62);
    });
  }

  function saveBlob(blob, name) {
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = name;
    link.click();
    setTimeout(() => URL.revokeObjectURL(link.href), 1500);
  }

  async function renderShot(ctx, target, image, text, index, total, previous, label) {
    const fps = 8;
    const frames = SHOT_SECONDS * fps;
    const body = new FormData();
    body.append("fps", String(fps));
    for (let frame = 0; frame < frames; frame += 1) {
      drawShot(ctx, image, text, frame / fps, index, total, previous);
      body.append("frames", await blobOf(target), `frame-${String(frame + 1).padStart(3, "0")}.jpg`);
      if (frame % 8 === 0) progress.textContent = `${label}, frame ${frame + 1} of ${frames}`;
      await new Promise((resolve) => setTimeout(resolve, 0));
    }
    progress.textContent = `${label}, encoding`;
    const response = await fetch("/api/motion", { method: "POST", body });
    if (!response.ok) {
      const failure = await response.json().catch(() => ({}));
      throw new Error(failure.error || "A picture could not be made into video.");
    }
    return response.blob();
  }

  async function download() {
    if (busy || stale() || !shots.length || !postInput.value.trim()) return;
    stopPlayback();
    busy = true;
    refreshButtons();
    try {
      chooseStage();
      const lines = captionsFor(postInput.value, shots.length);
      const target = document.createElement("canvas");
      target.width = stage.w;
      target.height = stage.h;
      const ctx = target.getContext("2d", { alpha: false });
      if (!ctx) throw new Error("This browser could not draw the video.");
      const videos = [];
      for (let index = 0; index < shots.length; index += 1) {
        videos.push(await renderShot(
          ctx,
          target,
          shots[index].image,
          lines[index],
          index,
          shots.length,
          index > 0 ? shots[index - 1].image : null,
          `Picture ${index + 1} of ${shots.length}`,
        ));
      }
      let video = videos[0];
      if (videos.length > 1 || musicOn()) {
        progress.textContent = videos.length > 1 ? "Joining the pictures into one video" : "Adding the quiet music";
        const body = new FormData();
        videos.forEach((blob, index) => {
          body.append("videos", blob, `scene-${String(index + 1).padStart(2, "0")}.mp4`);
        });
        if (musicOn()) body.append("music", "quiet");
        const response = await fetch("/api/stitch", { method: "POST", body });
        if (!response.ok) {
          const failure = await response.json().catch(() => ({}));
          throw new Error(failure.error || "The pictures could not be joined.");
        }
        video = await response.blob();
      }
      saveBlob(video, "post-from-pictures.mp4");
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
  readButton.addEventListener("click", readPictures);
  playButton.addEventListener("click", play);
  downloadButton.addEventListener("click", download);
  copyButton.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(postInput.value);
      progress.textContent = "Copied the post.";
    } catch {
      postInput.focus();
      postInput.select();
      progress.textContent = "Select the post and copy it.";
    }
  });
  postInput.addEventListener("input", () => {
    refreshButtons();
    if (!busy && postInput.value.trim() && shots.length) showStill();
  });
  if (transitionSelect) {
    transitionSelect.addEventListener("change", () => {
      if (!busy && postInput.value.trim() && shots.length) showStill();
    });
  }
  document.querySelectorAll('input[name="mode"]').forEach((input) => {
    input.addEventListener("change", () => {
      if (isPicsMode() && card.dataset.ready === "1") card.hidden = false;
    });
  });

  function setFfmpeg(available) {
    ffmpeg = Boolean(available);
    ffmpegKnown = true;
    refreshButtons();
  }

  refreshButtons();
  window.LinkedInPics = { readPictures, setFfmpeg, isPicsMode, captionsFor, drawShot };
})();
