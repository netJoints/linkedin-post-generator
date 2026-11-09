/* Animated video from a script: plan the words, edit them, then render. */
(function () {
  "use strict";

  const draftFields = document.querySelector("#draft-fields");
  const scriptFields = document.querySelector("#script-fields");
  const scriptCard = document.querySelector("#script-card");
  const topics = document.querySelector("#topics");
  const scriptInput = document.querySelector("#script");
  const planButton = document.querySelector("#plan-video");
  const headlineInput = document.querySelector("#plan-headline");
  const eyebrowInput = document.querySelector("#plan-eyebrow");
  const nodesInput = document.querySelector("#plan-nodes");
  const captionsInput = document.querySelector("#plan-captions");
  const applyButton = document.querySelector("#plan-apply");
  const playButton = document.querySelector("#script-play");
  const downloadButton = document.querySelector("#script-download");
  const progress = document.querySelector("#script-progress");
  const empty = document.querySelector("#script-empty");
  const canvas = document.querySelector("#script-canvas");
  const caption = document.querySelector("#script-caption");
  const videoNote = document.querySelector("#script-video-note");

  let board = null;
  let snapshot = "";
  let ffmpeg = false;
  let ffmpegKnown = false;
  let busy = false;
  let playToken = 0;

  function isVideoMode() {
    const picked = document.querySelector('input[name="mode"]:checked');
    return Boolean(picked && picked.value === "video");
  }

  function lines(value) {
    return String(value || "").split(/\n+/).map((line) => line.trim()).filter(Boolean);
  }

  function signature() {
    return JSON.stringify({
      headline: headlineInput.value,
      eyebrow: eyebrowInput.value,
      nodes: lines(nodesInput.value),
      captions: lines(captionsInput.value),
    });
  }

  function dirty() {
    return Boolean(snapshot) && signature() !== snapshot;
  }

  function note(message) {
    progress.textContent = message;
  }

  function refreshButtons() {
    const ready = Boolean(board) && !busy;
    const edited = dirty();
    planButton.disabled = busy;
    applyButton.disabled = busy || !board;
    playButton.disabled = !ready || edited;
    downloadButton.hidden = !ffmpeg;
    downloadButton.disabled = !ready || edited;
    videoNote.hidden = !ffmpegKnown || ffmpeg;
  }

  function applyMode() {
    const video = isVideoMode();
    draftFields.hidden = video;
    scriptFields.hidden = !video;
    scriptCard.hidden = !video;
    if (topics) topics.required = !video;
    document.querySelectorAll(".draft-only").forEach((node) => {
      if (video) {
        node.dataset.wasHidden = node.hidden ? "1" : "0";
        node.hidden = true;
      } else if (node.dataset.wasHidden === "0") {
        node.hidden = false;
      }
    });
  }

  function fill(plan) {
    headlineInput.value = plan.headline || "";
    eyebrowInput.value = plan.eyebrow || "";
    nodesInput.value = (plan.nodes || []).join("\n");
    captionsInput.value = (plan.captions || []).join("\n");
    snapshot = signature();
  }

  function showStill() {
    if (!board || !window.LinkedInMotion || !canvas) return;
    canvas.width = LinkedInMotion.width;
    canvas.height = LinkedInMotion.height;
    const ctx = canvas.getContext("2d", { alpha: false });
    if (!ctx) return;
    const total = LinkedInMotion.duration(board);
    LinkedInMotion.draw(ctx, board, Math.max(0, total - 0.05));
    canvas.hidden = false;
    empty.hidden = true;
    const beats = board.beats || [];
    caption.textContent = beats.length ? beats[beats.length - 1].caption || "" : "";
  }

  function stopPlayback() {
    playToken += 1;
  }

  function play() {
    if (!board || !window.LinkedInMotion || busy || dirty()) return;
    stopPlayback();
    const run = playToken;
    const total = LinkedInMotion.duration(board);
    const started = performance.now();
    const ctx = canvas.getContext("2d", { alpha: false });
    const frame = (now) => {
      if (run !== playToken) return;
      const time = Math.min((now - started) / 1000, total);
      LinkedInMotion.draw(ctx, board, time);
      const beat = board.beats[LinkedInMotion.beatAt(board, time)];
      caption.textContent = beat && beat.caption ? beat.caption : "";
      if (time < total) requestAnimationFrame(frame);
    };
    canvas.hidden = false;
    empty.hidden = true;
    requestAnimationFrame(frame);
  }

  async function requestPlan(payload) {
    const response = await fetch("/api/script", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || "The video plan could not be built.");
    if (!data.motion || !data.plan) throw new Error("The video plan could not be built.");
    return data;
  }

  async function showPlan(payload, pending) {
    if (busy) return false;
    busy = true;
    stopPlayback();
    refreshButtons();
    note(pending);
    try {
      await document.fonts.ready;
      const data = await requestPlan(payload);
      board = data.motion;
      fill(data.plan);
      showStill();
      note("This is the explainer. Edit any line, update the preview, then download the video.");
      return true;
    } catch (error) {
      note(error.message || "The video plan could not be built.");
      return false;
    } finally {
      busy = false;
      refreshButtons();
    }
  }

  function planFromScript() {
    const script = scriptInput.value.trim();
    if (!script) {
      note("Paste a script first.");
      scriptInput.focus();
      return;
    }
    showPlan({ script }, "Planning the video");
  }

  function currentPlan() {
    return {
      headline: headlineInput.value,
      eyebrow: eyebrowInput.value,
      nodes: lines(nodesInput.value),
      captions: lines(captionsInput.value),
    };
  }

  function fileName() {
    const slug = String((board && board.headline) || "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 42);
    return `${slug ? `explainer-${slug}` : "explainer"}.mp4`;
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

  async function download() {
    if (busy || !board || dirty() || !window.LinkedInMotion) return;
    stopPlayback();
    busy = true;
    refreshButtons();
    try {
      const fps = 10;
      const total = LinkedInMotion.duration(board);
      const count = Math.max(1, Math.round(total * fps));
      const exportCanvas = document.createElement("canvas");
      exportCanvas.width = LinkedInMotion.width;
      exportCanvas.height = LinkedInMotion.height;
      const ctx = exportCanvas.getContext("2d", { alpha: false });
      if (!ctx) throw new Error("This browser could not draw the explainer.");
      const body = new FormData();
      body.append("fps", String(fps));
      for (let frame = 0; frame < count; frame += 1) {
        LinkedInMotion.draw(ctx, board, frame / fps);
        const blob = await blobOf(exportCanvas);
        body.append("frames", blob, `frame-${String(frame + 1).padStart(3, "0")}.jpg`);
        if (frame % 8 === 0) note(`Making the explainer, ${frame + 1} of ${count}`);
        await new Promise((resolve) => setTimeout(resolve, 0));
      }
      note("Encoding the explainer");
      const response = await fetch("/api/motion", { method: "POST", body });
      if (!response.ok) {
        const failure = await response.json().catch(() => ({}));
        throw new Error(failure.error || "The explainer could not be made.");
      }
      saveBlob(await response.blob(), fileName());
      showStill();
      note("Saved the animated video.");
    } catch (error) {
      note(error.message || "The explainer could not be made.");
    } finally {
      busy = false;
      refreshButtons();
    }
  }

  document.querySelectorAll('input[name="mode"]').forEach((input) => {
    input.addEventListener("change", applyMode);
  });
  planButton.addEventListener("click", planFromScript);
  applyButton.addEventListener("click", () => showPlan(currentPlan(), "Updating the preview"));
  playButton.addEventListener("click", play);
  downloadButton.addEventListener("click", download);
  [headlineInput, eyebrowInput, nodesInput, captionsInput].forEach((field) => {
    field.addEventListener("input", () => {
      refreshButtons();
      if (dirty() && !busy) note("Update the preview so the video uses these words.");
    });
  });

  function setFfmpeg(available) {
    ffmpeg = Boolean(available);
    ffmpegKnown = true;
    refreshButtons();
  }

  applyMode();
  refreshButtons();
  window.LinkedInScript = { planFromScript, setFfmpeg, isVideoMode };
})();
