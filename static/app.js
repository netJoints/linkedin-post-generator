const form = document.querySelector("#draft-form");
const modelSelect = document.querySelector("#model");
const generateButton = document.querySelector("#generate");
const stopButton = document.querySelector("#stop");
const progress = document.querySelector("#progress");
const banner = document.querySelector("#status-banner");
const liveCard = document.querySelector("#live-card");
const live = document.querySelector("#live");
const articleEl = document.querySelector("#article");
const shortEl = document.querySelector("#short");
const articleCount = document.querySelector("#article-count");
const shortCount = document.querySelector("#short-count");
const sourcesEl = document.querySelector("#sources");
const sourceList = document.querySelector("#source-list");

const drafts = { article: "", short: "" };
let controller = null;

function words(text) {
  const trimmed = text.trim();
  if (!trimmed) return "0 words";
  const count = trimmed.split(/\s+/).length;
  return `${count} words · ${trimmed.length} characters`;
}

function setBusy(busy) {
  generateButton.disabled = busy;
  stopButton.hidden = !busy;
  modelSelect.disabled = busy;
}

function showEmpty() {
  articleEl.className = "copy document empty";
  shortEl.className = "copy post empty";
  articleEl.textContent = "The article will land here.";
  shortEl.textContent = "The shorter feed post will land here.";
  articleCount.textContent = "";
  shortCount.textContent = "";
}

function renderArticle(text) {
  articleEl.className = "copy document";
  articleEl.replaceChildren();
  const lines = text.replace(/^\s+/, "").split("\n");
  const title = (lines[0] || "").trim();
  const rest = lines.slice(1).join("\n").trim();
  const heading = document.createElement("strong");
  heading.className = "title";
  heading.textContent = title;
  articleEl.append(heading, document.createTextNode(rest ? `\n${rest}` : ""));
}

function renderShort(text) {
  shortEl.className = "copy post";
  shortEl.textContent = text;
}

function renderSources(sources) {
  sourceList.replaceChildren();
  if (!sources.length) {
    sourcesEl.hidden = true;
    return;
  }
  sourcesEl.hidden = false;
  for (const source of sources) {
    const item = document.createElement("li");
    if (source.error) {
      item.textContent = `${source.url} — ${source.error}`;
    } else {
      const link = document.createElement("a");
      link.href = source.url;
      link.target = "_blank";
      link.rel = "noreferrer";
      link.textContent = source.title || source.url;
      item.append(link);
      const note = source.kind === "video" ? " · video title only, no transcript" : " · page text";
      item.append(document.createTextNode(note));
    }
    sourceList.append(item);
  }
}

function enableOutputs(ready) {
  for (const button of document.querySelectorAll("[data-copy], [data-download]")) {
    button.disabled = !ready;
  }
}

async function refreshModels() {
  try {
    const response = await fetch("/api/health");
    const health = await response.json();
    if (!health.ollama) {
      banner.hidden = false;
      banner.textContent = "Ollama is not running. Start it, then reload this page.";
      generateButton.disabled = true;
      return;
    }
    const ready = new Set(health.models || []);
    let selectedStillThere = false;
    for (const option of modelSelect.options) {
      const installed = ready.has(option.value);
      option.disabled = !installed;
      if (installed && option.value === modelSelect.value) selectedStillThere = true;
    }
    if (!selectedStillThere) {
      const first = [...modelSelect.options].find((option) => !option.disabled);
      if (first) modelSelect.value = first.value;
    }
    if (![...modelSelect.options].some((option) => !option.disabled)) {
      banner.hidden = false;
      banner.textContent = "Neither Mistral Small 3.2 nor Gemma 4 12B is installed in Ollama.";
      generateButton.disabled = true;
      return;
    }
    banner.hidden = true;
  } catch {
    banner.hidden = false;
    banner.textContent = "This page could not reach the local app.";
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  controller = new AbortController();
  setBusy(true);
  enableOutputs(false);
  drafts.article = "";
  drafts.short = "";
  showEmpty();
  live.textContent = "";
  liveCard.hidden = false;
  sourcesEl.hidden = true;
  progress.textContent = "Starting";

  try {
    const response = await fetch("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal: controller.signal,
      body: JSON.stringify({
        model: modelSelect.value,
        company: document.querySelector("#company").value,
        topics: document.querySelector("#topics").value,
        urls: document.querySelector("#urls").value,
      }),
    });
    if (!response.ok) {
      const failure = await response.json().catch(() => ({}));
      throw new Error(failure.error || "The draft could not be started.");
    }
    await readStream(response);
  } catch (error) {
    if (error.name === "AbortError") {
      progress.textContent = "Stopped.";
    } else {
      progress.textContent = error.message;
    }
  } finally {
    setBusy(false);
    controller = null;
  }
});

stopButton.addEventListener("click", () => controller?.abort());

async function readStream(response) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    for (const line of lines) {
      if (!line.trim()) continue;
      handleEvent(JSON.parse(line));
    }
    if (done) break;
  }
}

function handleEvent(event) {
  if (event.type === "status") {
    progress.textContent = event.message;
    return;
  }
  if (event.type === "token") {
    live.textContent += event.text;
    liveCard.hidden = false;
    return;
  }
  if (event.type === "error") {
    progress.textContent = event.message;
    return;
  }
  if (event.type === "done") {
    drafts.article = event.article || "";
    drafts.short = event.short || "";
    liveCard.hidden = true;
    if (drafts.article) renderArticle(drafts.article);
    else {
      articleEl.className = "copy document empty";
      articleEl.textContent = "The model did not return an article.";
    }
    if (drafts.short) renderShort(drafts.short);
    else {
      shortEl.className = "copy post empty";
      shortEl.textContent = "The model did not return a short post. The article is still above.";
    }
    articleCount.textContent = drafts.article ? words(drafts.article) : "";
    shortCount.textContent = drafts.short ? words(drafts.short) : "";
    renderSources(event.sources || []);
    enableOutputs(Boolean(drafts.article || drafts.short));
    progress.textContent = "Ready to paste into LinkedIn.";
  }
}

document.querySelectorAll("[data-copy]").forEach((button) => {
  button.addEventListener("click", async () => {
    const text = drafts[button.dataset.copy];
    if (!text) return;
    await navigator.clipboard.writeText(text);
    const original = button.textContent;
    button.textContent = "Copied";
    setTimeout(() => { button.textContent = original; }, 1200);
  });
});

document.querySelectorAll("[data-download]").forEach((button) => {
  button.addEventListener("click", () => {
    const key = button.dataset.download;
    const text = drafts[key];
    if (!text) return;
    const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = key === "article" ? "linkedin-article.txt" : "linkedin-post.txt";
    link.click();
    URL.revokeObjectURL(link.href);
  });
});

refreshModels();
