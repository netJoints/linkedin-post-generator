(function () {
  "use strict";

  const FEED_W = 1080;
  const FEED_H = 1350;
  const COVER_W = 1920;
  const COVER_H = 1080;
  const FONT = '"Avenir Next", "Segoe UI", "Helvetica Neue", sans-serif';
  const INK = "#071422";
  const PAPER = "#f3f6fa";
  const INK_TEXT = "#f4f8fc";
  const PAPER_TEXT = "#122033";
  const INK_MUTED = "#c5d4e2";
  const PAPER_MUTED = "#3e5368";
  const ACCENT = "#049fd9";
  const ACCENT_DEEP = "#0b6f93";

  const canvas = document.querySelector("#cards-canvas");
  const empty = document.querySelector("#cards-empty");
  const caption = document.querySelector("#cards-caption");
  const nav = document.querySelector("#cards-nav");
  const dots = document.querySelector("#cards-dots");
  const prev = document.querySelector("#cards-prev");
  const next = document.querySelector("#cards-next");
  const pdfButton = document.querySelector("#cards-pdf");
  const imagesButton = document.querySelector("#cards-images");
  const coverButton = document.querySelector("#cards-cover");
  const videoButton = document.querySelector("#cards-video");
  const videoNote = document.querySelector("#cards-video-note");
  const progress = document.querySelector("#progress");

  if (!canvas) return;

  const preview = canvas.getContext("2d", { alpha: false });
  let deck = { eyebrow: "", footer: "", slides: [] };
  let index = 0;
  let ffmpeg = false;
  let busy = false;
  let token = 0;

  function pad(value) {
    return String(value).padStart(2, "0");
  }

  function setTracking(ctx, value) {
    if ("letterSpacing" in ctx) ctx.letterSpacing = value;
  }

  function wrapText(ctx, words, font, maxWidth, maxLines) {
    ctx.font = font;
    const lines = [];
    let current = "";
    for (const word of words) {
      const trial = current ? `${current} ${word}` : word;
      if (!current || ctx.measureText(trial).width <= maxWidth) {
        current = trial;
        continue;
      }
      lines.push(current);
      current = word;
      if (lines.length === maxLines) {
        current = "";
        break;
      }
    }
    if (current && lines.length < maxLines) lines.push(current);
    return lines;
  }

  function ellipsize(ctx, line, font, maxWidth) {
    ctx.font = font;
    let text = line;
    while (text.length > 1 && ctx.measureText(`${text}…`).width > maxWidth) {
      text = text.slice(0, -1);
    }
    return `${text.replace(/[\s,;:—-]+$/, "")}…`;
  }

  function fitText(ctx, text, maxWidth, maxLines, weight, start, minSize) {
    const words = String(text || "").trim().split(/\s+/).filter(Boolean);
    if (!words.length) return { font: `${weight} ${minSize}px ${FONT}`, size: minSize, lines: [] };
    let size = start;
    while (size >= minSize) {
      const font = `${weight} ${size}px ${FONT}`;
      const lines = wrapText(ctx, words, font, maxWidth, maxLines);
      const used = lines.join(" ").split(/\s+/).filter(Boolean).length;
      if (lines.length && lines.length <= maxLines && used === words.length) {
        return { font, size, lines };
      }
      if (size === minSize) break;
      size = Math.max(minSize, size - 4);
    }
    const font = `${weight} ${minSize}px ${FONT}`;
    const lines = wrapText(ctx, words, font, maxWidth, maxLines);
    const used = lines.join(" ").split(/\s+/).filter(Boolean).length;
    if (lines.length && used < words.length) {
      lines[lines.length - 1] = ellipsize(ctx, lines[lines.length - 1], font, maxWidth);
    }
    return { font, size: minSize, lines };
  }

  function drawLines(ctx, fitted, x, y, color, leading) {
    ctx.font = fitted.font;
    ctx.fillStyle = color;
    ctx.textBaseline = "top";
    setTracking(ctx, "0px");
    let cursor = y;
    for (const line of fitted.lines) {
      ctx.fillText(line, x, cursor);
      cursor += Math.round(fitted.size * leading);
    }
    return cursor;
  }

  function fillRoundRect(ctx, x, y, width, height, radius) {
    ctx.beginPath();
    if (typeof ctx.roundRect === "function") ctx.roundRect(x, y, width, height, radius);
    else ctx.rect(x, y, width, height);
    ctx.fill();
  }

  function paintBackdrop(ctx, width, height, dark) {
    ctx.fillStyle = dark ? INK : PAPER;
    ctx.fillRect(0, 0, width, height);
    ctx.fillStyle = ACCENT;
    ctx.fillRect(0, 0, width, Math.round(height * 0.012));
  }

  function paintEyebrow(ctx, text, x, y, dark) {
    const label = String(text || "").toUpperCase();
    if (!label) return y;
    ctx.textBaseline = "top";
    ctx.font = `700 26px ${FONT}`;
    setTracking(ctx, "3px");
    ctx.fillStyle = dark ? "#8fd8f3" : ACCENT_DEEP;
    ctx.fillText(label, x, y);
    setTracking(ctx, "0px");
    return y + 44;
  }

  function paintFooter(ctx, page, total, dark, footer, width, height) {
    const y = height - 112;
    ctx.textBaseline = "top";
    ctx.font = `600 24px ${FONT}`;
    setTracking(ctx, "0px");
    ctx.fillStyle = dark ? "#93a9bd" : "#5c6e80";
    if (footer) {
      const fitted = fitText(ctx, footer, width * 0.55, 1, 600, 24, 20);
      ctx.font = fitted.font;
      ctx.fillText(fitted.lines[0] || "", Math.round(width * 0.08), y);
    }
    const label = `${pad(page)}  /  ${pad(total)}`;
    ctx.font = `600 24px ${FONT}`;
    const labelWidth = ctx.measureText(label).width;
    ctx.fillText(label, width - Math.round(width * 0.08) - labelWidth, y);
  }

  function renderFeed(ctx, slide, page, total, meta) {
    const dark = slide.kind === "hook" || slide.kind === "close";
    const inset = 88;
    const width = FEED_W;
    const textWidth = width - inset * 2;
    paintBackdrop(ctx, width, FEED_H, dark);
    paintEyebrow(ctx, meta.eyebrow, inset, 112, dark);
    if (dark) {
      const title = fitText(ctx, slide.title, textWidth, 5, 700, 84, 56);
      const body = fitText(ctx, slide.body, textWidth, 3, 500, 36, 30);
      const titleBlock = title.lines.length * Math.round(title.size * 1.12);
      const bodyBlock = body.lines.length ? 28 + body.lines.length * Math.round(body.size * 1.3) : 0;
      let y = Math.max(250, Math.round((FEED_H - titleBlock - bodyBlock) / 2));
      y = drawLines(ctx, title, inset, y, INK_TEXT, 1.12);
      if (body.lines.length) drawLines(ctx, body, inset, y + 28, INK_MUTED, 1.3);
    } else {
      ctx.textBaseline = "top";
      ctx.font = `700 68px ${FONT}`;
      setTracking(ctx, "0px");
      ctx.fillStyle = ACCENT;
      ctx.fillText(pad(page), inset, 210);
      let y = 300;
      const title = fitText(ctx, slide.title, textWidth, 4, 700, 58, 42);
      y = drawLines(ctx, title, inset, y, PAPER_TEXT, 1.14);
      ctx.fillStyle = ACCENT;
      ctx.fillRect(inset, y + 8, 72, 6);
      y += 40;
      if (slide.kind === "checklist") {
        for (const item of slide.items || []) {
          if (y > FEED_H - 180) break;
          const fitted = fitText(ctx, item, textWidth - 56, 2, 600, 36, 30);
          ctx.fillStyle = ACCENT;
          fillRoundRect(ctx, inset, y + 8, 16, 16, 4);
          const nextY = drawLines(ctx, fitted, inset + 40, y, PAPER_TEXT, 1.25);
          y = Math.max(nextY, y + 36) + 26;
        }
      } else if (slide.body) {
        const body = fitText(ctx, slide.body, textWidth, 5, 500, 36, 30);
        drawLines(ctx, body, inset, y, PAPER_MUTED, 1.32);
      }
    }
    paintFooter(ctx, page, total, dark, meta.footer, width, FEED_H);
  }

  function renderCover(ctx, slide, meta) {
    paintBackdrop(ctx, COVER_W, COVER_H, true);
    const inset = 120;
    paintEyebrow(ctx, meta.eyebrow, inset, 150, true);
    const title = fitText(ctx, slide.title, 1500, 4, 700, 84, 56);
    const body = fitText(ctx, slide.body, 1400, 2, 500, 36, 30);
    const titleBlock = title.lines.length * Math.round(title.size * 1.12);
    const bodyBlock = body.lines.length ? 24 + body.lines.length * Math.round(body.size * 1.3) : 0;
    let y = Math.max(280, Math.round((COVER_H - titleBlock - bodyBlock) / 2));
    y = drawLines(ctx, title, inset, y, INK_TEXT, 1.12);
    if (body.lines.length) drawLines(ctx, body, inset, y + 24, INK_MUTED, 1.3);
    if (meta.footer) {
      ctx.font = `600 28px ${FONT}`;
      ctx.fillStyle = "#93a9bd";
      ctx.textBaseline = "top";
      ctx.fillText(meta.footer, inset, COVER_H - 110);
    }
  }

  function makeCanvas(width, height) {
    const board = document.createElement("canvas");
    board.width = width;
    board.height = height;
    const ctx = board.getContext("2d", { alpha: false });
    if (!ctx) throw new Error("This browser could not draw the cards.");
    return { board, ctx };
  }

  function feedCanvas(slide, page, total) {
    const { board, ctx } = makeCanvas(FEED_W, FEED_H);
    renderFeed(ctx, slide, page, total, deck);
    return board;
  }

  function coverCanvas() {
    const slide = deck.slides.find((item) => item.kind === "hook") || deck.slides[0];
    const { board, ctx } = makeCanvas(COVER_W, COVER_H);
    renderCover(ctx, slide, deck);
    return board;
  }

  function blobOf(board, type, quality) {
    return new Promise((resolve, reject) => {
      board.toBlob((blob) => {
        if (!blob) reject(new Error("A card could not be drawn."));
        else resolve(blob);
      }, type, quality);
    });
  }

  function saveBlob(blob, name) {
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = name;
    link.click();
    setTimeout(() => URL.revokeObjectURL(link.href), 1500);
  }

  function concat(parts) {
    const size = parts.reduce((sum, part) => sum + part.length, 0);
    const out = new Uint8Array(size);
    let offset = 0;
    for (const part of parts) {
      out.set(part, offset);
      offset += part.length;
    }
    return out;
  }

  const CRC_TABLE = (() => {
    const table = new Uint32Array(256);
    for (let n = 0; n < 256; n += 1) {
      let c = n;
      for (let k = 0; k < 8; k += 1) c = (c & 1) ? (0xedb88320 ^ (c >>> 1)) : (c >>> 1);
      table[n] = c >>> 0;
    }
    return table;
  })();

  function crc32(bytes) {
    let c = 0xffffffff;
    for (let i = 0; i < bytes.length; i += 1) c = CRC_TABLE[(c ^ bytes[i]) & 0xff] ^ (c >>> 8);
    return (c ^ 0xffffffff) >>> 0;
  }

  function zipStore(files) {
    const encoder = new TextEncoder();
    const parts = [];
    const central = [];
    let offset = 0;
    for (const file of files) {
      const name = encoder.encode(file.name);
      const crc = crc32(file.data);
      const local = new DataView(new ArrayBuffer(30));
      local.setUint32(0, 0x04034b50, true);
      local.setUint16(4, 20, true);
      local.setUint16(8, 0, true);
      local.setUint32(14, crc, true);
      local.setUint32(18, file.data.length, true);
      local.setUint32(22, file.data.length, true);
      local.setUint16(26, name.length, true);
      const localBytes = new Uint8Array(local.buffer);
      parts.push(localBytes, name, file.data);
      const row = new DataView(new ArrayBuffer(46));
      row.setUint32(0, 0x02014b50, true);
      row.setUint16(4, 20, true);
      row.setUint16(6, 20, true);
      row.setUint32(16, crc, true);
      row.setUint32(20, file.data.length, true);
      row.setUint32(24, file.data.length, true);
      row.setUint16(28, name.length, true);
      row.setUint32(42, offset, true);
      central.push(new Uint8Array(row.buffer), name);
      offset += localBytes.length + name.length + file.data.length;
    }
    const centralStart = offset;
    const centralBytes = concat(central);
    const end = new DataView(new ArrayBuffer(22));
    end.setUint32(0, 0x06054b50, true);
    end.setUint16(8, files.length, true);
    end.setUint16(10, files.length, true);
    end.setUint32(12, centralBytes.length, true);
    end.setUint32(16, centralStart, true);
    return concat([...parts, centralBytes, new Uint8Array(end.buffer)]);
  }

async function deflateBytes(bytes) {
  const stream = new CompressionStream("deflate");
  const reader = stream.readable.getReader();
  const chunks = [];
  const reading = (async () => {
    while (true) {
      const step = await reader.read();
      if (step.done) break;
      chunks.push(step.value);
    }
  })();
  const writer = stream.writable.getWriter();
  await writer.write(bytes);
  await writer.close();
  await reading;
  return concat(chunks);
}

  async function buildPdf(boards) {
    const encoder = new TextEncoder();
    const images = [];
    for (const board of boards) {
      const ctx = board.getContext("2d");
      const pixels = ctx.getImageData(0, 0, board.width, board.height).data;
      const raw = new Uint8Array(board.width * board.height * 3);
      let cursor = 0;
      for (let i = 0; i < pixels.length; i += 4) {
        raw[cursor] = pixels[i];
        raw[cursor + 1] = pixels[i + 1];
        raw[cursor + 2] = pixels[i + 2];
        cursor += 3;
      }
      images.push({ width: board.width, height: board.height, data: await deflateBytes(raw) });
    }
    const count = 2 + images.length * 3;
    const objects = new Array(count + 1);
    const pageIds = images.map((_, imageIndex) => 5 + imageIndex * 3);
    objects[1] = encoder.encode("<< /Type /Catalog /Pages 2 0 R >>");
    objects[2] = encoder.encode(
      `<< /Type /Pages /Count ${images.length} /Kids [${pageIds.map((id) => `${id} 0 R`).join(" ")}] >>`
    );
    images.forEach((image, imageIndex) => {
      const imageId = 3 + imageIndex * 3;
      const contentId = imageId + 1;
      const pageId = imageId + 2;
      const header = encoder.encode(
        `<< /Type /XObject /Subtype /Image /Width ${image.width} /Height ${image.height} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /FlateDecode /Length ${image.data.length} >>\nstream\n`
      );
      const footer = encoder.encode("\nendstream");
      const body = new Uint8Array(header.length + image.data.length + footer.length);
      body.set(header, 0);
      body.set(image.data, header.length);
      body.set(footer, header.length + image.data.length);
      objects[imageId] = body;
      const draw = `q\n${image.width} 0 0 ${image.height} 0 0 cm\n/Im0 Do\nQ\n`;
      objects[contentId] = encoder.encode(
        `<< /Length ${draw.length} >>\nstream\n${draw}endstream`
      );
      objects[pageId] = encoder.encode(
        `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${image.width} ${image.height}] /Contents ${contentId} 0 R /Resources << /XObject << /Im0 ${imageId} 0 R >> >> >>`
      );
    });
    const parts = [new Uint8Array([0x25, 0x50, 0x44, 0x46, 0x2d, 0x31, 0x2e, 0x34, 0x0a, 0x25, 0xff, 0xff, 0xff, 0xff, 0x0a])];
    let position = parts[0].length;
    const xref = [0];
    for (let id = 1; id <= count; id += 1) {
      xref.push(position);
      const lead = encoder.encode(`${id} 0 obj\n`);
      const tail = encoder.encode("\nendobj\n");
      parts.push(lead, objects[id], tail);
      position += lead.length + objects[id].length + tail.length;
    }
    let table = `xref\n0 ${count + 1}\n0000000000 65535 f \n`;
    for (let id = 1; id <= count; id += 1) {
      table += `${String(xref[id]).padStart(10, "0")} 00000 n \n`;
    }
    table += `trailer\n<< /Size ${count + 1} /Root 1 0 R >>\nstartxref\n${position}\n%%EOF\n`;
    parts.push(encoder.encode(table));
    return new Blob([concat(parts)], { type: "application/pdf" });
  }

  function fileName(slide, page) {
    const kind = slide.kind || "card";
    return `${pad(page)}-${kind}.png`;
  }

  function paint() {
    const slides = deck.slides;
    const slide = slides[index];
    if (!slide || !preview) return;
    renderFeed(preview, slide, index + 1, slides.length, deck);
    const bits = [`Card ${index + 1} of ${slides.length}`, slide.title];
    if (slide.body) bits.push(slide.body);
    if (slide.items && slide.items.length) bits.push(slide.items.join(" · "));
    caption.textContent = bits.join(" — ");
    prev.disabled = index === 0;
    next.disabled = index === slides.length - 1;
    Array.prototype.forEach.call(dots.children, (dot, dotIndex) => {
      dot.setAttribute("aria-current", dotIndex === index ? "true" : "false");
    });
  }

  function renderDots() {
    dots.replaceChildren();
    deck.slides.forEach((slide, dotIndex) => {
      const button = document.createElement("button");
      button.type = "button";
      button.setAttribute("aria-label", `Card ${dotIndex + 1}: ${slide.title}`);
      button.addEventListener("click", () => {
        index = dotIndex;
        paint();
      });
      dots.append(button);
    });
  }

  function setDownloads(enabled) {
    const on = enabled && deck.slides.length > 0 && !busy;
    pdfButton.disabled = !on;
    imagesButton.disabled = !on;
    coverButton.disabled = !on;
    videoButton.disabled = !on;
  }

  function noteStatus(message) {
    if (message) progress.textContent = message;
  }

  async function exportAll(kind) {
    if (busy || !deck.slides.length) return;
    busy = true;
    setDownloads(false);
    const mine = token;
    try {
      if (kind === "pdf") {
        noteStatus("Preparing the PDF");
        const boards = deck.slides.map((slide, slideIndex) => feedCanvas(slide, slideIndex + 1, deck.slides.length));
        saveBlob(await buildPdf(boards), "linkedin-cards.pdf");
      } else if (kind === "images") {
        noteStatus("Preparing the images");
        const files = [];
        for (let slideIndex = 0; slideIndex < deck.slides.length; slideIndex += 1) {
          const board = feedCanvas(deck.slides[slideIndex], slideIndex + 1, deck.slides.length);
          const bytes = new Uint8Array(await (await blobOf(board, "image/png")).arrayBuffer());
          files.push({ name: fileName(deck.slides[slideIndex], slideIndex + 1), data: bytes });
        }
        saveBlob(new Blob([zipStore(files)], { type: "application/zip" }), "linkedin-cards.zip");
      } else if (kind === "cover") {
        noteStatus("Preparing the article cover");
        saveBlob(await blobOf(coverCanvas(), "image/png"), "linkedin-article-cover.png");
      } else if (kind === "video") {
        noteStatus("Making the video");
        const body = new FormData();
        for (let slideIndex = 0; slideIndex < deck.slides.length; slideIndex += 1) {
          const board = feedCanvas(deck.slides[slideIndex], slideIndex + 1, deck.slides.length);
          const blob = await blobOf(board, "image/jpeg", 0.92);
          body.append("frames", blob, `card-${pad(slideIndex + 1)}.jpg`);
        }
        const response = await fetch("/api/video", { method: "POST", body });
        if (!response.ok) {
          const failure = await response.json().catch(() => ({}));
          throw new Error(failure.error || "The video could not be made.");
        }
        saveBlob(await response.blob(), "linkedin-cards.mp4");
      }
      if (mine === token) noteStatus("Ready. Copy the text, then download the cards and attach them on LinkedIn.");
    } catch (error) {
      if (mine === token) noteStatus(error.message || "The download could not be prepared.");
    } finally {
      busy = false;
      setDownloads(true);
    }
  }

  function reset() {
    token += 1;
    deck = { eyebrow: "", footer: "", slides: [] };
    index = 0;
    busy = false;
    canvas.hidden = true;
    empty.hidden = false;
    empty.textContent = "The cards will land here.";
    caption.textContent = "";
    nav.hidden = true;
    dots.replaceChildren();
    setDownloads(false);
  }

  async function show(incoming) {
    const mine = ++token;
    await document.fonts.ready;
    if (mine !== token) return;
    const slides = Array.isArray(incoming && incoming.slides) ? incoming.slides : [];
    deck = {
      eyebrow: String((incoming && incoming.eyebrow) || "").slice(0, 40),
      footer: String((incoming && incoming.footer) || "").slice(0, 40),
      slides: slides.filter((slide) => slide && slide.title).slice(0, 10).map((slide) => ({
        kind: slide.kind || "point",
        title: String(slide.title),
        body: String(slide.body || ""),
        items: Array.isArray(slide.items) ? slide.items.map((item) => String(item)).filter(Boolean).slice(0, 5) : [],
      })),
    };
    index = 0;
    if (!deck.slides.length) {
      canvas.hidden = true;
      empty.hidden = false;
      empty.textContent = "The draft did not include enough text to build cards.";
      caption.textContent = "";
      nav.hidden = true;
      setDownloads(false);
      return;
    }
    canvas.width = FEED_W;
    canvas.height = FEED_H;
    empty.hidden = true;
    canvas.hidden = false;
    nav.hidden = false;
    renderDots();
    paint();
    setDownloads(true);
  }

  function setFfmpeg(available) {
    ffmpeg = Boolean(available);
    videoButton.hidden = !ffmpeg;
    videoNote.hidden = ffmpeg;
  }

  function move(step) {
    const target = index + step;
    if (target < 0 || target >= deck.slides.length) return;
    index = target;
    paint();
  }

  prev.addEventListener("click", () => move(-1));
  next.addEventListener("click", () => move(1));
  pdfButton.addEventListener("click", () => exportAll("pdf"));
  imagesButton.addEventListener("click", () => exportAll("images"));
  coverButton.addEventListener("click", () => exportAll("cover"));
  videoButton.addEventListener("click", () => exportAll("video"));

  document.addEventListener("keydown", (event) => {
    if (canvas.hidden) return;
    const tag = (event.target && event.target.tagName) || "";
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
    if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
      move(event.key === "ArrowRight" ? 1 : -1);
      event.preventDefault();
    }
  });

  window.LinkedInCards = { reset, show, setFfmpeg };
  reset();
})();
