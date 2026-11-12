/* Animated video from scripts: one card per script, played in order, saved as one video. */
(function () {
  "use strict";

  const MIN_CARDS = 6;
  const MAX_CARDS = 10;
  const LAYOUTS = [
    ["auto", "Auto"],
    ["statement", "Statement"],
    ["question", "Question"],
    ["steps", "Steps"],
    ["checklist", "Checklist"],
    ["compare", "Compare"],
    ["diagram", "Diagram"],
  ];
  const EXAMPLES = [
    "Human-only NetOps can no longer keep pace with modern networks.\nThat is why autonomy must earn trust every time it acts.",
    "How an agent closes a ticket\n1. It reads the alert and the topology.\n2. It proposes a fix with the evidence.\n3. A person approves the change.",
    "Before you ship an agent:\nLog every tool call.\nScope its permissions.\nKeep a human on approvals.",
    "Before: Tickets wait for a change window.\nAfter: Fixes ship with evidence attached.",
    "Autonomy must earn trust every time it acts.",
    "Where would you start: the alerts, or the change window?",
  ];

  const draftFields = document.querySelector("#draft-fields");
  const scriptFields = document.querySelector("#script-fields");
  const scriptCard = document.querySelector("#script-card");
  const topics = document.querySelector("#topics");
  const inputs = document.querySelector("#scene-inputs");
  const addButton = document.querySelector("#add-scene");
  const planButton = document.querySelector("#plan-video");
  const total = document.querySelector("#scene-total");
  const list = document.querySelector("#scene-list");
  const playButton = document.querySelector("#script-play");
  const playAllButton = document.querySelector("#script-play-all");
  const downloadButton = document.querySelector("#script-download");
  const progress = document.querySelector("#script-progress");
  const empty = document.querySelector("#script-empty");
  const canvas = document.querySelector("#script-canvas");
  const caption = document.querySelector("#script-caption");
  const videoNote = document.querySelector("#script-video-note");

  let scenes = [];
  let selected = 0;
  let snapshot = "";
  let ffmpeg = false;
  let ffmpegKnown = false;
  let busy = false;
  let playToken = 0;

  function isVideoMode() {
    const picked = document.querySelector('input[name="mode"]:checked');
    return Boolean(picked && picked.value === "video");
  }

  function cardFields() {
    return Array.from(inputs.querySelectorAll(".scene-input")).map((block) => ({
      script: block.querySelector("textarea"),
      layout: block.querySelector("select"),
    }));
  }

  function payload() {
    return {
      scenes: cardFields().map((field) => ({ script: field.script.value, layout: field.layout.value })),
    };
  }

  function signature() {
    return JSON.stringify(payload());
  }

  function dirty() {
    return Boolean(snapshot) && signature() !== snapshot;
  }

  function ready() {
    return scenes.filter((scene) => scene.motion);
  }

  function note(message) {
    progress.textContent = message;
  }

  function refreshButtons() {
    const usable = ready().length > 0 && !busy && !dirty();
    planButton.disabled = busy;
    addButton.disabled = busy || cardFields().length >= MAX_CARDS;
    playButton.disabled = !usable || !(scenes[selected] && scenes[selected].motion);
    playAllButton.disabled = !usable;
    downloadButton.hidden = !ffmpeg;
    downloadButton.disabled = !usable;
    videoNote.hidden = !ffmpegKnown || ffmpeg;
  }

  function addCard() {
    const count = cardFields().length;
    if (count >= MAX_CARDS) return;
    const number = count + 1;
    const block = document.createElement("div");
    block.className = "scene-input";
    const head = document.createElement("div");
    head.className = "scene-input-head";
    const title = document.createElement("span");
    title.textContent = `Card ${number}`;
    const select = document.createElement("select");
    select.setAttribute("aria-label", `Card ${number} layout`);
    LAYOUTS.forEach(([value, name]) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = name;
      select.append(option);
    });
    head.append(title, select);
    const area = document.createElement("textarea");
    area.rows = 4;
    area.maxLength = 1200;
    area.setAttribute("aria-label", `Card ${number} script`);
    area.placeholder = EXAMPLES[count % EXAMPLES.length];
    block.append(head, area);
    inputs.append(block);
    [area, select].forEach((field) => {
      field.addEventListener("input", () => {
        refreshButtons();
        if (dirty() && !busy) note("Plan the video again so it uses these words.");
      });
    });
    refreshButtons();
  }

  function applyMode() {
    const picked = document.querySelector('input[name="mode"]:checked');
    const mode = picked ? picked.value : "draft";
    const video = mode === "video";
    const pics = mode === "pics";
    const stills = mode === "stills";
    const reel = mode === "reel";
    const focused = video || pics || stills || reel;
    draftFields.hidden = focused;
    scriptFields.hidden = !video;
    scriptCard.hidden = !video;
    const picsFields = document.querySelector("#pics-fields");
    const picsCard = document.querySelector("#pics-card");
    if (picsFields) picsFields.hidden = !pics;
    if (picsCard) picsCard.hidden = !pics || picsCard.dataset.ready !== "1";
    const stillsFields = document.querySelector("#stills-fields");
    const stillsCard = document.querySelector("#stills-card");
    if (stillsFields) stillsFields.hidden = !stills;
    if (stillsCard) stillsCard.hidden = !stills || stillsCard.dataset.ready !== "1";
    const reelFields = document.querySelector("#reel-fields");
    const reelCard = document.querySelector("#reel-card");
    if (reelFields) reelFields.hidden = !reel;
    if (reelCard) reelCard.hidden = !reel;
    if (topics) topics.required = !focused;
    const model = document.querySelector("#model");
    if (model) model.required = !focused;
    document.querySelectorAll(".draft-only").forEach((node) => {
      if (focused) {
        if (node.dataset.wasHidden === undefined) node.dataset.wasHidden = node.hidden ? "1" : "0";
        node.hidden = true;
      } else if (node.dataset.wasHidden === "0") {
        node.hidden = false;
      }
    });
  }

  function summary(plan) {
    return [plan.headline, ...(plan.items || [])].filter(Boolean).join(" · ");
  }

  function renderList() {
    list.replaceChildren();
    scenes.forEach((scene, index) => {
      const item = document.createElement("li");
      const button = document.createElement("button");
      button.type = "button";
      button.setAttribute("aria-current", index === selected ? "true" : "false");
      const name = document.createElement("span");
      name.className = "scene-name";
      const detail = document.createElement("span");
      if (scene.motion) {
        name.textContent = `Card ${scene.card} · ${scene.plan.name} · ${Math.round(scene.plan.seconds)} s`;
        detail.className = "scene-summary";
        detail.textContent = summary(scene.plan);
      } else {
        name.textContent = `Card ${scene.card} · not used`;
        detail.className = "scene-error";
        detail.textContent = scene.error || "This card could not be planned.";
      }
      button.append(name, detail);
      if (scene.plan && scene.plan.note) {
        const extra = document.createElement("span");
        extra.className = "scene-note";
        extra.textContent = scene.plan.note;
        button.append(extra);
      }
      button.addEventListener("click", () => {
        selected = index;
        stopPlayback();
        renderList();
        showStill();
        refreshButtons();
      });
      item.append(button);
      list.append(item);
    });
    const count = ready().length;
    const seconds = ready().reduce((sum, scene) => sum + LinkedInMotion.duration(scene.motion), 0);
    total.textContent = count
      ? `${count} ${count === 1 ? "card" : "cards"}, about ${Math.round(seconds)} seconds. Pick a card to preview it.`
      : "No card could be planned yet.";
  }

  function context() {
    canvas.width = LinkedInMotion.width;
    canvas.height = LinkedInMotion.height;
    return canvas.getContext("2d", { alpha: false });
  }

  function showStill() {
    const scene = scenes[selected];
    if (!scene || !scene.motion || !window.LinkedInMotion || !canvas) return;
    const ctx = context();
    if (!ctx) return;
    const board = scene.motion;
    LinkedInMotion.draw(ctx, board, Math.max(0, LinkedInMotion.duration(board) - 0.45));
    canvas.hidden = false;
    empty.hidden = true;
    const beats = board.beats || [];
    caption.textContent = beats.length ? beats[beats.length - 1].caption || "" : "";
  }

  function stopPlayback() {
    playToken += 1;
  }

  function playScenes(order) {
    if (!order.length || !window.LinkedInMotion || busy || dirty()) return;
    stopPlayback();
    const run = playToken;
    const ctx = context();
    if (!ctx) return;
    let step = 0;
    let started = performance.now();
    const frame = (now) => {
      if (run !== playToken) return;
      const board = order[step].motion;
      const length = LinkedInMotion.duration(board);
      let time = (now - started) / 1000;
      if (time >= length && step < order.length - 1) {
        step += 1;
        started = now;
        time = 0;
      }
      const current = order[step].motion;
      time = Math.min(time, LinkedInMotion.duration(current));
      LinkedInMotion.draw(ctx, current, time);
      const beat = (current.beats || [])[LinkedInMotion.beatAt(current, time)];
      caption.textContent = beat && beat.caption ? beat.caption : "";
      if (step < order.length - 1 || time < LinkedInMotion.duration(current)) requestAnimationFrame(frame);
    };
    canvas.hidden = false;
    empty.hidden = true;
    requestAnimationFrame(frame);
  }

  async function planFromScript() {
    if (busy) return;
    const body = payload();
    if (!body.scenes.some((scene) => scene.script.trim())) {
      note("Write a script in at least one card.");
      const first = cardFields()[0];
      if (first) first.script.focus();
      return;
    }
    busy = true;
    stopPlayback();
    refreshButtons();
    note("Planning the cards");
    try {
      await document.fonts.ready;
      const response = await fetch("/api/scenes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || "The video plan could not be built.");
      if (!Array.isArray(data.scenes)) throw new Error("The video plan could not be built.");
      scenes = data.scenes;
      snapshot = JSON.stringify(body);
      const first = scenes.findIndex((scene) => scene.motion);
      selected = first < 0 ? 0 : first;
      renderList();
      showStill();
      const failed = scenes.length - ready().length;
      note(failed
        ? `${failed} ${failed === 1 ? "card needs" : "cards need"} more words and will be left out. Fix them or download without them.`
        : "Play the cards, then download the full video.");
    } catch (error) {
      note(error.message || "The video plan could not be built.");
    } finally {
      busy = false;
      refreshButtons();
    }
  }

  function fileName() {
    const first = ready()[0];
    const slug = String((first && (first.motion.headline || first.plan.items[0])) || "")
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

  async function failure(response, fallback) {
    const data = await response.json().catch(() => ({}));
    return new Error(data.error || fallback);
  }

  async function renderScene(ctx, target, board, label) {
    const fps = 10;
    const count = Math.max(1, Math.round(LinkedInMotion.duration(board) * fps));
    const body = new FormData();
    body.append("fps", String(fps));
    for (let frame = 0; frame < count; frame += 1) {
      LinkedInMotion.draw(ctx, board, frame / fps);
      body.append("frames", await blobOf(target), `frame-${String(frame + 1).padStart(3, "0")}.jpg`);
      if (frame % 10 === 0) note(`${label}, frame ${frame + 1} of ${count}`);
      await new Promise((resolve) => setTimeout(resolve, 0));
    }
    note(`${label}, encoding`);
    const response = await fetch("/api/motion", { method: "POST", body });
    if (!response.ok) throw await failure(response, "A card could not be made.");
    return response.blob();
  }

  async function download() {
    const order = ready();
    if (busy || !order.length || dirty() || !window.LinkedInMotion) return;
    stopPlayback();
    busy = true;
    refreshButtons();
    try {
      const target = document.createElement("canvas");
      target.width = LinkedInMotion.width;
      target.height = LinkedInMotion.height;
      const ctx = target.getContext("2d", { alpha: false });
      if (!ctx) throw new Error("This browser could not draw the explainer.");
      const videos = [];
      for (let index = 0; index < order.length; index += 1) {
        videos.push(await renderScene(ctx, target, order[index].motion, `Card ${index + 1} of ${order.length}`));
      }
      let video = videos[0];
      if (videos.length > 1) {
        note("Joining the cards into one video");
        const body = new FormData();
        videos.forEach((blob, index) => {
          body.append("videos", blob, `scene-${String(index + 1).padStart(2, "0")}.mp4`);
        });
        const response = await fetch("/api/stitch", { method: "POST", body });
        if (!response.ok) throw await failure(response, "The cards could not be joined.");
        video = await response.blob();
      }
      saveBlob(video, fileName());
      showStill();
      note(`Saved the full video: ${order.length} ${order.length === 1 ? "card" : "cards"}.`);
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
  addButton.addEventListener("click", addCard);
  planButton.addEventListener("click", planFromScript);
  playButton.addEventListener("click", () => {
    const scene = scenes[selected];
    if (scene && scene.motion) playScenes([scene]);
  });
  playAllButton.addEventListener("click", () => playScenes(ready()));
  downloadButton.addEventListener("click", download);

  function setFfmpeg(available) {
    ffmpeg = Boolean(available);
    ffmpegKnown = true;
    refreshButtons();
  }

  for (let index = 0; index < MIN_CARDS; index += 1) addCard();
  applyMode();
  refreshButtons();
  window.LinkedInScript = { planFromScript, setFfmpeg, isVideoMode };
})();
