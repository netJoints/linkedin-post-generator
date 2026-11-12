/* Motion film: pick a format, fill in its lines, and draw a short portrait film on this laptop. */
(function () {
  "use strict";

  const W = 1080;
  const H = 1350;
  const FPS = 10;
  const MAX_SECONDS = 16;
  const FONT = '"Avenir Next", "Segoe UI", "Helvetica Neue", sans-serif';
  const PAPER = "#EDE6D5";
  const BLUE = "#1B3ED2";
  const CYAN = "#45F0DD";
  const BLACK = "#07080A";
  const GRAPHITE = "#16161A";
  const WHITE = "#FFFFFF";
  const BARS = ["HOOK", "TYPE", "CURVE", "MORPH", "TILE", "NODES", "DATA", "END"];

  const formatSelect = document.querySelector("#reel-format");
  const formatNote = document.querySelector("#reel-format-note");
  const inputsBox = document.querySelector("#reel-inputs");
  const card = document.querySelector("#reel-card");
  const playButton = document.querySelector("#reel-play");
  const downloadButton = document.querySelector("#reel-download");
  const progress = document.querySelector("#reel-progress");
  const empty = document.querySelector("#reel-empty");
  const canvas = document.querySelector("#reel-canvas");
  const videoNote = document.querySelector("#reel-video-note");

  if (!canvas || !formatSelect || !inputsBox) return;

  const ctx = canvas.getContext("2d");
  canvas.width = W;
  canvas.height = H;

  let ffmpeg = false;
  let ffmpegKnown = false;
  let busy = false;
  let playToken = 0;
  const drafts = {};

  function isReelMode() {
    const picked = document.querySelector('input[name="mode"]:checked');
    return Boolean(picked && picked.value === "reel");
  }

  function clean(value, max) {
    return String(value || "")
      .replace(/[\u0000-\u001f\u007f]/g, " ")
      .replace(/\s+/g, " ")
      .trim()
      .slice(0, max);
  }

  function lines(value, count, max) {
    return String(value || "")
      .split(/\n/)
      .map((line) => clean(line, max))
      .filter(Boolean)
      .slice(0, count);
  }

  function damp(elapsed, w) {
    if (elapsed <= 0) return 0;
    const x = w * elapsed;
    return 1 - (1 + x) * Math.exp(-x);
  }

  function span(t, start, dur, w) {
    if (t <= start) return 0;
    if (t >= start + dur) return 1;
    return damp(t - start, w || 18);
  }

  function lerp(a, b, u) { return a + (b - a) * u; }

  function clamp(v, a, b) { return Math.max(a, Math.min(b, v)); }

  function grid(ink) {
    const step = 60;
    const tones = {
      paper: ["rgba(27,62,210,0.13)", "rgba(27,62,210,0.26)"],
      blueprint: ["rgba(255,255,255,0.22)", "rgba(255,255,255,0.40)"],
      hologram: ["rgba(69,240,221,0.18)", "rgba(69,240,221,0.34)"],
      dark: ["rgba(255,255,255,0.05)", "rgba(255,255,255,0.10)"],
    }[ink];
    ctx.lineWidth = 1;
    for (let x = 0; x <= W; x += step) {
      ctx.strokeStyle = (x / step) % 5 === 0 ? tones[1] : tones[0];
      ctx.beginPath();
      ctx.moveTo(x + 0.5, 0);
      ctx.lineTo(x + 0.5, H);
      ctx.stroke();
    }
    for (let y = 0; y <= H; y += step) {
      ctx.strokeStyle = (y / step) % 5 === 0 ? tones[1] : tones[0];
      ctx.beginPath();
      ctx.moveTo(0, y + 0.5);
      ctx.lineTo(W, y + 0.5);
      ctx.stroke();
    }
  }

  function fill(color, ink) {
    ctx.fillStyle = color;
    ctx.fillRect(0, 0, W, H);
    if (ink) grid(ink);
  }

  function wobble(t, i) {
    return Math.sin(t * 8 * Math.PI * 2 + i * 0.7) * 1.4;
  }

  function strokeLine(x1, y1, x2, y2, color, width, t) {
    ctx.strokeStyle = color;
    ctx.lineCap = "round";
    ctx.lineWidth = width;
    ctx.beginPath();
    const steps = 18;
    for (let i = 0; i <= steps; i += 1) {
      const u = i / steps;
      const x = lerp(x1, x2, u) + wobble(t, i);
      const y = lerp(y1, y2, u) + wobble(t, i + 3);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();
    ctx.lineWidth = width * 0.45;
    ctx.globalAlpha *= 0.4;
    ctx.stroke();
    ctx.globalAlpha /= 0.4;
  }

  function label(text, x, y, size, color, weight, align) {
    ctx.fillStyle = color;
    ctx.font = `${weight} ${size}px ${FONT}`;
    ctx.textAlign = align || "left";
    ctx.textBaseline = "middle";
    ctx.fillText(text, x, y);
    ctx.textAlign = "left";
  }

  function fit(text, weight, max, min, width) {
    let size = max;
    ctx.font = `${weight} ${size}px ${FONT}`;
    while (size > min && ctx.measureText(text).width > width) {
      size -= 4;
      ctx.font = `${weight} ${size}px ${FONT}`;
    }
    return size;
  }

  function layoutWords(text, weight, size, maxWidth, gap) {
    ctx.font = `${weight} ${size}px ${FONT}`;
    const space = ctx.measureText(" ").width;
    const rows = [];
    let row = [];
    let width = 0;
    text.split(" ").filter(Boolean).forEach((word, index) => {
      const w = ctx.measureText(word).width;
      if (row.length && width + space + w > maxWidth) {
        rows.push({ items: row, width });
        row = [];
        width = 0;
      }
      width = row.length ? width + space + w : w;
      row.push({ word, w, index });
    });
    if (row.length) rows.push({ items: row, width });
    const lineH = size * gap;
    let count = 0;
    rows.forEach((r, i) => {
      let x = W / 2 - r.width / 2;
      r.items.forEach((item) => {
        item.x = x;
        item.y = i * lineH + lineH / 2;
        x += item.w + space;
        count += 1;
      });
    });
    return {
      size,
      weight,
      rows,
      count,
      height: rows.length * lineH,
      widest: rows.reduce((m, r) => Math.max(m, r.width), 0),
    };
  }

  function fitLayout(text, weight, max, min, maxWidth, maxLines, gap) {
    for (let size = max; size >= min; size -= 4) {
      const layout = layoutWords(text, weight, size, maxWidth, gap || 1.1);
      if (layout.rows.length <= maxLines && layout.widest <= maxWidth) return layout;
    }
    return layoutWords(text, weight, min, maxWidth, gap || 1.1);
  }

  function eachWord(layout, fn) {
    layout.rows.forEach((r) => r.items.forEach(fn));
  }

  function drawWord(item, layout, top, color, dy) {
    ctx.fillStyle = color;
    ctx.font = `${layout.weight} ${layout.size}px ${FONT}`;
    ctx.textAlign = "left";
    ctx.textBaseline = "middle";
    ctx.fillText(item.word, item.x, top + item.y + (dy || 0));
  }

  function hatchText(text, x, y, size, color) {
    ctx.save();
    ctx.font = `800 ${size}px ${FONT}`;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    const width = ctx.measureText(text).width;
    const left = x - width / 2 - 20;
    ctx.fillStyle = color;
    ctx.fillText(text, x, y);
    ctx.globalCompositeOperation = "source-atop";
    ctx.strokeStyle = "rgba(237,230,213,0.62)";
    ctx.lineWidth = 3;
    ctx.beginPath();
    for (let i = left - size; i < left + width + size; i += 7) {
      ctx.moveTo(i, y - size);
      ctx.lineTo(i + size * 0.8, y + size);
    }
    ctx.stroke();
    ctx.restore();
  }

  function rails(y, gap, len, color, t) {
    const x = W / 2 - len / 2;
    strokeLine(x, y - gap / 2, x + len, y - gap / 2, color, 4, t);
    strokeLine(x, y + gap / 2, x + len, y + gap / 2, color, 4, t);
  }

  function splitEnd(end) {
    const words = end.split(" ");
    return words.length > 1 ? [words.slice(0, -1).join(" "), words[words.length - 1]] : [end];
  }

  /* Line film: one drawn line carries the title, a few words, points, facts, and an end card. */

  function lineInk(t) {
    if (t < 9.6) return "paper";
    if (t < 14.2) return "blueprint";
    return "hologram";
  }

  function lineGround(t) {
    fill(PAPER);
    if (t >= 9.6 && t < 14.2) {
      const u = span(t, 9.6, 0.4, 22);
      ctx.save();
      ctx.beginPath();
      ctx.rect(0, 0, W * u, H);
      ctx.clip();
      fill(BLUE);
      ctx.restore();
      if (u < 1) {
        ctx.fillStyle = WHITE;
        ctx.fillRect(W * u - 3, 0, 6, H);
      }
    } else if (t >= 14.2) {
      fill(BLUE);
      const y = lerp(-8, H + 8, span(t, 14.2, 0.35, 28));
      ctx.save();
      ctx.beginPath();
      ctx.rect(0, 0, W, y);
      ctx.clip();
      fill(BLACK);
      ctx.restore();
      ctx.fillStyle = CYAN;
      ctx.fillRect(0, y - 2, W, 4);
    }
    grid(lineInk(t));
  }

  function drawLine(copy, t) {
    const ink = lineInk(t);
    const line = ink === "paper" ? BLUE : ink === "blueprint" ? WHITE : CYAN;
    lineGround(t);
    const bar = clamp(Math.floor(t / 2), 0, 7);
    const beat = clamp(Math.floor(t * 2) + 1, 1, 32);
    label(`FIG. 0${bar + 1}  —  ${BARS[bar]}`, 48, 56, 24, line, 600);
    label(`BEAT  ${String(beat).padStart(2, "0")}  /  32`, W - 48, H - 56, 24, line, 600, "right");
    const mid = H / 2;

    if (t < 2) {
      const crush = span(t, 0.36, 0.5, 16);
      const rise = span(t, 1.0, 0.4, 14);
      const open = span(t, 1.5, 0.4, 14);
      const title = copy.title.toUpperCase();
      ctx.save();
      ctx.translate(W / 2, lerp(mid, mid + 40 * crush, crush));
      ctx.scale(1, Math.max(0.08, lerp(1, 0.08, crush * (1 - rise))));
      if (rise < 0.85) hatchText(title, 0, 0, fit(title, 800, 150, 64, 900), GRAPHITE);
      ctx.restore();
      const railLen = lerp(940, lerp(860, 720, open), rise);
      const gap = lerp(0, 220 * open, rise);
      if (gap < 8) strokeLine(W / 2 - railLen / 2, mid, W / 2 + railLen / 2, mid, line, 5, t);
      else rails(mid, gap, railLen, line, t);
    } else if (t < 4) {
      const words = copy.words;
      const index = clamp(Math.floor(((t - 2) / 2) * words.length), 0, words.length - 1);
      const enter = damp((t - 2) - index * (2 / words.length), 22);
      const crush = t > 3.7 ? span(t, 3.7, 0.3, 20) : 0;
      const word = words[index].toUpperCase();
      rails(mid, lerp(180, 8, crush), lerp(880, 940, crush), line, t);
      ctx.save();
      ctx.translate(W / 2, mid);
      ctx.globalAlpha = enter;
      ctx.scale(lerp(1.15, 1, enter), lerp(0.2, 1, enter) * lerp(1, 0.05, crush));
      hatchText(word, 0, 0, fit(word, 800, 140, 56, 860), GRAPHITE);
      ctx.restore();
    } else if (t < 6) {
      const amp = lerp(0, 92, span(t, 4.15, 0.45, 12)) * (1 - span(t, 5.45, 0.4, 14));
      const len = 860;
      ctx.strokeStyle = line;
      ctx.lineWidth = 5;
      ctx.lineCap = "round";
      ctx.beginPath();
      for (let i = 0; i <= 64; i += 1) {
        const u = i / 64;
        const x = W / 2 - len / 2 + u * len;
        const y = mid + Math.sin(u * Math.PI * 2.75 + t * 3) * amp + wobble(t, i);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();
    } else if (t < 8) {
      const n = [3, 4, 6][t < 6.7 ? 0 : t < 7.35 ? 1 : 2];
      const radius = 250;
      ctx.save();
      ctx.translate(W / 2, mid);
      ctx.rotate((t - 6) * 0.8);
      ctx.beginPath();
      for (let i = 0; i <= n; i += 1) {
        const a = -Math.PI / 2 + (i / n) * Math.PI * 2;
        if (i === 0) ctx.moveTo(Math.cos(a) * radius, Math.sin(a) * radius);
        else ctx.lineTo(Math.cos(a) * radius, Math.sin(a) * radius);
      }
      ctx.closePath();
      ctx.strokeStyle = line;
      ctx.lineWidth = 5;
      ctx.stroke();
      ctx.clip();
      ctx.globalAlpha = 0.45;
      ctx.lineWidth = 2;
      for (let y = -radius; y < radius; y += 10) {
        ctx.beginPath();
        ctx.moveTo(-radius, y);
        ctx.lineTo(radius, y + 40);
        ctx.stroke();
      }
      ctx.restore();
    } else if (t < 10) {
      const cells = t < 8.6 ? 7 : 19;
      const r = t < 8.6 ? 70 : 46;
      ctx.strokeStyle = line;
      ctx.lineWidth = 3;
      let n = 0;
      for (let row = -2; row <= 2 && n < cells; row += 1) {
        for (let col = -2; col <= 2 && n < cells; col += 1) {
          if (cells === 7 && Math.abs(row) + Math.abs(col) > 2) continue;
          const x = W / 2 + col * r * 1.85;
          const y = mid + row * r * 1.7;
          ctx.beginPath();
          for (let i = 0; i <= 6; i += 1) {
            const a = -Math.PI / 2 + (i / 6) * Math.PI * 2;
            if (i === 0) ctx.moveTo(x + Math.cos(a) * r * 0.72, y + Math.sin(a) * r * 0.72);
            else ctx.lineTo(x + Math.cos(a) * r * 0.72, y + Math.sin(a) * r * 0.72);
          }
          ctx.stroke();
          n += 1;
        }
      }
    } else if (t < 12) {
      const names = copy.nodes;
      const xs = names.map((_, i) => W / 2 + (i - (names.length - 1) / 2) * 310);
      if (xs.length > 1) {
        ctx.strokeStyle = WHITE;
        ctx.lineWidth = 3;
        ctx.beginPath();
        ctx.moveTo(xs[0], mid);
        ctx.lineTo(xs[xs.length - 1], mid);
        ctx.stroke();
      }
      names.forEach((name, i) => {
        ctx.globalAlpha = span(t, 10.05 + i * 0.18, 0.25, 18);
        ctx.beginPath();
        ctx.arc(xs[i], mid, 18, 0, Math.PI * 2);
        ctx.strokeStyle = WHITE;
        ctx.lineWidth = 3;
        ctx.stroke();
        const text = name.toUpperCase();
        label(text, xs[i], mid + 56, fit(text, 600, 26, 16, 290), WHITE, 600, "center");
        ctx.globalAlpha = 1;
      });
    } else if (t < 14.2) {
      const facts = copy.facts.length ? copy.facts : [{ value: copy.end, label: "" }];
      facts.forEach((fact, i) => {
        const y = 400 + i * 230;
        const value = fact.value.toUpperCase();
        ctx.globalAlpha = span(t, 12.1 + i * 0.4, 0.35, 16);
        label(value, 130, y, fit(value, 800, 96, 44, 860), WHITE, 800);
        if (fact.label) label(fact.label.toUpperCase(), 130, y + 66, fit(fact.label.toUpperCase(), 600, 26, 16, 860), WHITE, 600);
        ctx.globalAlpha = 1;
      });
      strokeLine(90, 320, 90, 320 + 700 * span(t, 12.05, 1.2, 10), WHITE, 4, t);
    } else {
      const u = span(t, 14.55, 0.45, 16);
      const endLines = splitEnd(copy.end).map((part) => part.toUpperCase());
      ctx.save();
      ctx.translate(W / 2, mid);
      ctx.globalAlpha = u;
      ctx.scale(lerp(1.08, 1, u), lerp(0.4, 1, u));
      endLines.forEach((part, i) => {
        const y = endLines.length > 1 ? (i === 0 ? -80 : 80) : 0;
        label(part, 0, y, fit(part, 800, 140, 56, 900), CYAN, 800, "center");
      });
      ctx.restore();
      const len = lerp(160, 780, u);
      strokeLine(W / 2 - len / 2, mid + 220, W / 2 + len / 2, mid + 220, CYAN, 4, t);
    }
  }

  /* Quote: words land one at a time; the last word is drawn in blue and underlined. */

  function quoteTiming(copy) {
    const n = copy.quote.split(" ").filter(Boolean).length;
    const step = Math.min(0.3, 5 / Math.max(1, n));
    return { step, last: 0.6 + (n - 1) * step };
  }

  function drawQuote(copy, t) {
    fill(PAPER, "paper");
    const layout = fitLayout(copy.quote, 800, 104, 48, 900, 8, 1.12);
    const top = H / 2 - layout.height / 2 - (copy.who ? 50 : 0);
    const { step, last } = quoteTiming(copy);
    const mark = span(t, 0.15, 0.4, 16);
    ctx.globalAlpha = mark;
    label("\u201C", 90, top - 70 + (1 - mark) * 30, 200, BLUE, 800);
    ctx.globalAlpha = 1;
    eachWord(layout, (item) => {
      const a = span(t, 0.6 + item.index * step, 0.3, 20);
      if (a <= 0) return;
      ctx.globalAlpha = a;
      drawWord(item, layout, top, item.index === layout.count - 1 ? BLUE : GRAPHITE, (1 - a) * 28);
      ctx.globalAlpha = 1;
      if (item.index === layout.count - 1) {
        const u = span(t, last + 0.35, 0.6, 12);
        const y = top + item.y + layout.size * 0.62;
        if (u > 0) strokeLine(item.x, y, item.x + item.w * u, y, BLUE, 6, t);
      }
    });
    if (copy.who) {
      const u = span(t, last + 1.0, 0.4, 16);
      const y = top + layout.height + 110;
      ctx.globalAlpha = u;
      strokeLine(W / 2 - 40, y - 46, W / 2 + 40, y - 46, BLUE, 3, t);
      label(copy.who.toUpperCase(), W / 2, y, fit(copy.who.toUpperCase(), 600, 34, 20, 900), BLUE, 600, "center");
      ctx.globalAlpha = 1;
    }
  }

  /* Big number: one figure counts up and locks under a cyan rule. */

  function parseFigure(text) {
    const match = /^([^\d]*)(\d[\d,]*(?:\.\d+)?)(.*)$/.exec(text);
    if (!match) return null;
    const digits = match[2];
    return {
      prefix: match[1],
      suffix: match[3],
      target: parseFloat(digits.replace(/,/g, "")),
      decimals: (digits.split(".")[1] || "").length,
      commas: digits.includes(","),
    };
  }

  function showFigure(figure, u) {
    const value = figure.target * u;
    const body = figure.commas
      ? value.toLocaleString("en-US", { minimumFractionDigits: figure.decimals, maximumFractionDigits: figure.decimals })
      : value.toFixed(figure.decimals);
    return `${figure.prefix}${body}${figure.suffix}`;
  }

  function drawNumber(copy, t) {
    fill(BLACK, "hologram");
    const figure = parseFigure(copy.number);
    const size = fit(copy.number, 900, 300, 90, 940);
    const count = t < 0.9 ? 0 : t > 3.9 ? 1 : 1 - Math.pow(1 - (t - 0.9) / 3, 3);
    const text = figure ? showFigure(figure, count) : copy.number;
    const mid = H / 2 - 40;
    ctx.font = `900 ${size}px ${FONT}`;
    const finalWidth = ctx.measureText(copy.number).width;
    const left = W / 2 - finalWidth / 2;
    if (copy.label) {
      const top = copy.label.toUpperCase();
      ctx.globalAlpha = span(t, 0.3, 0.4, 16);
      label(top, W / 2, mid - size * 0.62 - 40, fit(top, 600, 36, 20, 940), CYAN, 600, "center");
      ctx.globalAlpha = 1;
    }
    ctx.globalAlpha = figure ? Math.min(1, t / 0.6) : span(t, 0.9, 0.5, 14);
    label(text, left, mid, size, WHITE, 900);
    ctx.globalAlpha = 1;
    const rule = span(t, 3.9, 0.5, 14);
    if (rule > 0) {
      ctx.fillStyle = CYAN;
      ctx.fillRect(left, mid + size * 0.52, finalWidth * rule, 10);
    }
    if (copy.sub) {
      const layout = fitLayout(copy.sub, 600, 48, 28, 900, 3, 1.2);
      const top = mid + size * 0.52 + 70;
      const a = span(t, 4.4, 0.4, 16);
      ctx.globalAlpha = a;
      eachWord(layout, (item) => drawWord(item, layout, top, WHITE, (1 - a) * 20));
      ctx.globalAlpha = 1;
    }
  }

  /* Word swap: a sentence holds still while the blank cycles through words; earlier words get struck. */

  function swapStart(i) { return 0.8 + i * 2.2; }

  function drawSwap(copy, t) {
    fill(PAPER, "paper");
    const parts = copy.sentence.split("___");
    const before = clean(parts[0], 60);
    const after = clean(parts.slice(1).join(" "), 60);
    const longest = copy.words.reduce((a, b) => (b.length > a.length ? b : a), "");
    const wordSize = fit(longest, 900, 170, 64, 940);
    const mid = H / 2 + 20;
    if (before) {
      const layout = fitLayout(before, 800, 96, 44, 900, 3, 1.1);
      const top = mid - wordSize * 0.7 - 30 - layout.height;
      eachWord(layout, (item) => drawWord(item, layout, top, GRAPHITE));
    }
    if (after) {
      const layout = fitLayout(after, 800, 96, 44, 900, 3, 1.1);
      eachWord(layout, (item) => drawWord(item, layout, mid + wordSize * 0.7 + 30, GRAPHITE));
    }
    let index = -1;
    copy.words.forEach((_, i) => { if (t >= swapStart(i)) index = i; });
    ctx.save();
    ctx.beginPath();
    ctx.rect(0, mid - wordSize * 0.75, W, wordSize * 1.5);
    ctx.clip();
    if (index < 0) {
      strokeLine(W / 2 - 160, mid + wordSize * 0.35, W / 2 + 160, mid + wordSize * 0.35, BLUE, 6, t);
    } else {
      const local = t - swapStart(index);
      const enter = damp(local, 20);
      const lastWord = index === copy.words.length - 1;
      if (index > 0 && enter < 1) {
        ctx.globalAlpha = 1 - enter;
        label(copy.words[index - 1], W / 2, mid - wordSize * 1.1 * enter, wordSize, GRAPHITE, 900, "center");
        ctx.globalAlpha = 1;
      }
      const word = copy.words[index];
      const y = mid + wordSize * 1.1 * (1 - enter);
      label(word, W / 2, y, wordSize, lastWord ? BLUE : GRAPHITE, 900, "center");
      ctx.font = `900 ${wordSize}px ${FONT}`;
      const w = ctx.measureText(word).width;
      if (lastWord) {
        const u = span(t, swapStart(index) + 0.4, 0.5, 12);
        if (u > 0) strokeLine(W / 2 - w / 2, y + wordSize * 0.5, W / 2 - w / 2 + w * u, y + wordSize * 0.5, BLUE, 8, t);
      } else {
        const u = span(t, swapStart(index) + 1.2, 0.4, 16);
        if (u > 0) strokeLine(W / 2 - w / 2 - 10, y, W / 2 - w / 2 - 10 + (w + 20) * u, y, BLUE, 8, t);
      }
    }
    ctx.restore();
  }

  /* Before and after: loose notes pile up, a line sweeps down, and one clean line is left. */

  const PILE = [
    { x: 330, y: 380, r: -0.08 },
    { x: 740, y: 560, r: 0.06 },
    { x: 360, y: 780, r: 0.05 },
    { x: 720, y: 990, r: -0.07 },
  ];

  function drawBeforeScene(copy, t) {
    fill(PAPER, "paper");
    label("BEFORE", 60, 72, 28, BLUE, 700);
    copy.before.forEach((item, i) => {
      const spot = PILE[i];
      const a = span(t, 0.4 + i * 0.45, 0.35, 18);
      if (a <= 0) return;
      const size = fit(item, 700, 44, 24, 600);
      ctx.font = `700 ${size}px ${FONT}`;
      const w = ctx.measureText(item).width + 80;
      const h = size + 60;
      ctx.save();
      ctx.translate(spot.x, spot.y + (1 - a) * 40);
      ctx.rotate(spot.r + Math.sin(t * 2 + i) * 0.01);
      ctx.globalAlpha = a;
      ctx.fillStyle = WHITE;
      ctx.fillRect(-w / 2, -h / 2, w, h);
      ctx.strokeStyle = GRAPHITE;
      ctx.lineWidth = 3;
      ctx.strokeRect(-w / 2, -h / 2, w, h);
      label(item, 0, 0, size, GRAPHITE, 700, "center");
      ctx.restore();
    });
  }

  function drawAfterScene(copy, t) {
    fill(BLUE, "blueprint");
    label("AFTER", 60, 72, 28, WHITE, 700);
    const layout = fitLayout(copy.after, 800, 100, 48, 900, 4, 1.1);
    const top = H / 2 - layout.height / 2 - 40;
    const a = span(t, 5.0, 0.4, 16);
    ctx.globalAlpha = a;
    eachWord(layout, (item) => drawWord(item, layout, top, WHITE, (1 - a) * 24));
    ctx.globalAlpha = 1;
    const tick = span(t, 5.5, 0.5, 14);
    if (tick > 0) {
      const cx = W / 2;
      const cy = top - 110;
      ctx.strokeStyle = CYAN;
      ctx.lineWidth = 10;
      ctx.lineCap = "round";
      ctx.beginPath();
      ctx.moveTo(cx - 44, cy);
      const first = clamp(tick * 2, 0, 1);
      ctx.lineTo(lerp(cx - 44, cx - 12, first), lerp(cy, cy + 32, first));
      if (tick > 0.5) ctx.lineTo(lerp(cx - 12, cx + 52, (tick - 0.5) * 2), lerp(cy + 32, cy - 40, (tick - 0.5) * 2));
      ctx.stroke();
    }
    if (copy.end) {
      const u = span(t, 7.0, 0.4, 16);
      const text = copy.end.toUpperCase();
      ctx.globalAlpha = u;
      label(text, W / 2, top + layout.height + 110, fit(text, 700, 40, 22, 900), CYAN, 700, "center");
      ctx.globalAlpha = 1;
    }
  }

  function drawBeforeAfter(copy, t) {
    drawBeforeScene(copy, t);
    if (t < 4.0) return;
    const y = lerp(0, H, span(t, 4.0, 0.9, 10));
    ctx.save();
    ctx.beginPath();
    ctx.rect(0, 0, W, y);
    ctx.clip();
    drawAfterScene(copy, t);
    ctx.restore();
    if (y < H) {
      ctx.fillStyle = CYAN;
      ctx.fillRect(0, y - 3, W, 6);
    }
  }

  /* Hook cuts: short lines hard-cut one after another; the last word of each gets a cyan bar. */

  const HOOK_STEP = 1.8;

  function drawHook(copy, t) {
    fill(GRAPHITE, "dark");
    const n = copy.phrases.length;
    const index = clamp(Math.floor((t - 0.2) / HOOK_STEP), 0, n - 1);
    const start = 0.2 + index * HOOK_STEP;
    if (t < 0.2) return;
    const local = t - start;
    const layout = fitLayout(copy.phrases[index], 900, 124, 56, 900, 4, 1.15);
    const top = H / 2 - layout.height / 2;
    const scale = lerp(1.12, 1, damp(local, 24));
    label(`${index + 1} / ${n}`, W - 60, 72, 28, CYAN, 700, "right");
    ctx.save();
    ctx.translate(W / 2, H / 2);
    ctx.scale(scale, scale);
    ctx.translate(-W / 2, -H / 2);
    const bar = span(t, start + 0.35, 0.3, 20);
    eachWord(layout, (item) => {
      const lastWord = item.index === layout.count - 1;
      if (lastWord && bar > 0) {
        ctx.fillStyle = CYAN;
        ctx.fillRect(item.x - 12, top + item.y - layout.size * 0.55, (item.w + 24) * bar, layout.size * 1.1);
      }
      drawWord(item, layout, top, lastWord && bar > 0.5 ? BLACK : WHITE);
    });
    ctx.restore();
    if (index === n - 1) {
      const u = span(t, start + 0.9, 0.4, 16);
      if (u > 0) {
        const y = H - 200;
        ctx.globalAlpha = u;
        ctx.strokeStyle = CYAN;
        ctx.lineWidth = 8;
        ctx.lineCap = "round";
        ctx.lineJoin = "round";
        ctx.beginPath();
        ctx.moveTo(W / 2, y - 70 + (1 - u) * 20);
        ctx.lineTo(W / 2, y + 20);
        ctx.moveTo(W / 2 - 34, y - 14);
        ctx.lineTo(W / 2, y + 20);
        ctx.lineTo(W / 2 + 34, y - 14);
        ctx.stroke();
        ctx.globalAlpha = 1;
      }
    }
  }

  const FORMATS = [
    {
      id: "line",
      name: "Line film — event or launch recap",
      note: "Sixteen seconds. One line stays on screen through paper, blueprint, and a dark end card.",
      ground: PAPER,
      fields: [
        { key: "title", label: "Title", max: 22, placeholder: "Cisco Live", required: true },
        { key: "words", label: "Words", area: 4, max: 80, placeholder: "Trusted\nScalable\nAssured", hint: "Up to four short words. Each one replaces the last on the line." },
        { key: "nodes", label: "Three points", max: 80, placeholder: "Chatbots, Agents, Physical", hint: "Separate them with commas." },
        { key: "facts", label: "Facts", area: 3, max: 160, placeholder: "GA Dec '26 | Experience metrics\nAvailable now | MCP server", hint: "Up to three lines: big text, a vertical bar, then the small label. Use only figures you can stand behind." },
        { key: "end", label: "End line", max: 28, placeholder: "Agentic enterprise", required: true },
      ],
      seconds: () => 16,
      read(v) {
        const title = clean(v.title, 22);
        const end = clean(v.end, 28);
        if (!title || !end) return null;
        const words = lines(v.words, 4, 18);
        return {
          title,
          end,
          words: words.length ? words : [title],
          nodes: clean(v.nodes, 80).split(",").map((part) => clean(part, 16)).filter(Boolean).slice(0, 3),
          facts: lines(v.facts, 3, 48).map((line) => {
            const parts = line.split("|");
            return { value: clean(parts[0], 16), label: clean(parts.slice(1).join(" "), 32) };
          }).filter((fact) => fact.value),
        };
      },
      draw: drawLine,
    },
    {
      id: "quote",
      name: "Quote — a line someone said",
      note: "Ten seconds. The words land one at a time and the last word is underlined.",
      ground: PAPER,
      fields: [
        { key: "quote", label: "Quote", area: 4, max: 160, placeholder: "The network is the first thing an agent touches.", required: true, hint: "Up to 160 characters. Quote only what was really said." },
        { key: "who", label: "Who said it", max: 40, placeholder: "Speaker name, title" },
      ],
      seconds: () => 10,
      read(v) {
        const quote = clean(v.quote, 160).replace(/^["\u201C]+|["\u201D]+$/g, "");
        if (!quote) return null;
        return { quote, who: clean(v.who, 40) };
      },
      draw: drawQuote,
    },
    {
      id: "number",
      name: "Big number — one figure that matters",
      note: "Eight seconds. The figure counts up from zero, then a line of context lands under it.",
      ground: BLACK,
      fields: [
        { key: "label", label: "What it measures", max: 40, placeholder: "Hardware readiness" },
        { key: "number", label: "The number", max: 14, placeholder: "83%", required: true, hint: "Prefixes and suffixes like $, %, x, or M are kept." },
        { key: "sub", label: "Context", max: 80, placeholder: "of the installed base can run it today", hint: "Use only figures you can stand behind." },
      ],
      seconds: () => 8,
      read(v) {
        const number = clean(v.number, 14);
        if (!number) return null;
        return { number, label: clean(v.label, 40), sub: clean(v.sub, 80) };
      },
      draw: drawNumber,
    },
    {
      id: "swap",
      name: "Word swap — not this, not this, this",
      note: "About eight seconds. The sentence holds while the blank cycles. Earlier words are struck out; the last one stays.",
      ground: PAPER,
      fields: [
        { key: "sentence", label: "Sentence", max: 60, placeholder: "Your network should be ___", required: true, hint: "Put ___ where the words go. Without it, the words go at the end." },
        { key: "words", label: "Words", area: 3, max: 60, placeholder: "faster\nbigger\nassured", required: true, hint: "Two or three. The last one is the answer." },
      ],
      seconds: (copy) => Math.min(MAX_SECONDS, swapStart(copy.words.length - 1) + 2.4),
      read(v) {
        let sentence = clean(v.sentence, 60);
        const words = lines(v.words, 3, 18);
        if (!sentence || !words.length) return null;
        if (!sentence.includes("___")) sentence = `${sentence} ___`;
        return { sentence, words };
      },
      draw: drawSwap,
    },
    {
      id: "before-after",
      name: "Before and after — the change you made",
      note: "Ten seconds. Loose notes pile up, a line sweeps down, and one clean line is left.",
      ground: PAPER,
      fields: [
        { key: "before", label: "Before", area: 4, max: 120, placeholder: "Five dashboards\nTickets by email\nGuessing at root cause", required: true, hint: "Up to four short pain points, one per line." },
        { key: "after", label: "After", max: 60, placeholder: "One view of the whole network", required: true },
        { key: "end", label: "Sign-off", max: 40, placeholder: "Cisco Live Melbourne" },
      ],
      seconds: () => 10,
      read(v) {
        const before = lines(v.before, 4, 28);
        const after = clean(v.after, 60);
        if (!before.length || !after) return null;
        return { before, after, end: clean(v.end, 40) };
      },
      draw: drawBeforeAfter,
    },
    {
      id: "hook",
      name: "Hook cuts — stop the scroll",
      note: "About two seconds per line, hard cuts, and a cyan bar on each last word. Ends on an arrow toward your post.",
      ground: GRAPHITE,
      fields: [
        { key: "phrases", label: "Lines", area: 4, max: 160, placeholder: "Most AI pilots stall.\nNot on the model.\nOn the network.", required: true, hint: "Two to four short lines, one per line." },
      ],
      seconds: (copy) => Math.min(MAX_SECONDS, 0.2 + copy.phrases.length * HOOK_STEP + 1.4),
      read(v) {
        const phrases = lines(v.phrases, 4, 40);
        if (!phrases.length) return null;
        return { phrases };
      },
      draw: drawHook,
    },
  ];

  function currentFormat() {
    return FORMATS.find((format) => format.id === formatSelect.value) || FORMATS[0];
  }

  function fieldInputs() {
    return Array.from(inputsBox.querySelectorAll("input, textarea"));
  }

  function rawValues() {
    const values = {};
    fieldInputs().forEach((input) => { values[input.dataset.key] = input.value; });
    return values;
  }

  function readCopy() {
    return currentFormat().read(rawValues());
  }

  function needs(format) {
    const names = format.fields.filter((field) => field.required).map((field) => field.label.toLowerCase());
    if (names.length <= 1) return `Add ${names[0] || "the lines"}.`;
    return `Add ${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}.`;
  }

  function refresh() {
    const ready = Boolean(readCopy()) && !busy;
    playButton.disabled = !ready;
    downloadButton.hidden = !ffmpeg;
    downloadButton.disabled = !ready;
    videoNote.hidden = !ffmpegKnown || ffmpeg;
    formatSelect.disabled = busy;
    fieldInputs().forEach((field) => { field.disabled = busy; });
  }

  function hint() {
    if (busy) return;
    const format = currentFormat();
    const copy = readCopy();
    progress.textContent = copy
      ? `Play runs the ${Math.round(format.seconds(copy))} seconds. Download video saves a 1080 × 1350 MP4.`
      : needs(format);
  }

  function buildFields() {
    const format = currentFormat();
    const saved = drafts[format.id] || {};
    inputsBox.replaceChildren();
    formatNote.textContent = format.note;
    format.fields.forEach((field) => {
      const wrap = document.createElement("label");
      wrap.append(document.createTextNode(field.label));
      const input = document.createElement(field.area ? "textarea" : "input");
      if (field.area) input.rows = field.area;
      else {
        input.type = "text";
        input.autocomplete = "off";
      }
      input.maxLength = field.max;
      input.placeholder = field.placeholder || "";
      input.dataset.key = field.key;
      input.value = saved[field.key] || "";
      input.addEventListener("input", () => {
        drafts[format.id] = rawValues();
        refresh();
        hint();
      });
      wrap.append(input);
      inputsBox.append(wrap);
      if (field.hint) {
        const note = document.createElement("p");
        note.className = "hint";
        note.textContent = field.hint;
        inputsBox.append(note);
      }
    });
    playToken += 1;
    canvas.hidden = true;
    empty.hidden = false;
    document.querySelector("#reel-stage").style.background = format.ground;
    refresh();
    hint();
  }

  function showFrame(format, copy, t) {
    empty.hidden = true;
    canvas.hidden = false;
    if (card) card.hidden = !isReelMode();
    format.draw(copy, t);
  }

  function play() {
    const format = currentFormat();
    const copy = readCopy();
    if (!copy || busy) return;
    const seconds = format.seconds(copy);
    const token = ++playToken;
    const started = performance.now();
    function frame(now) {
      if (token !== playToken) return;
      const t = Math.min(seconds, (now - started) / 1000);
      showFrame(format, copy, t);
      if (t < seconds) requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
  }

  function jpegBlob() {
    return new Promise((resolve) => {
      canvas.toBlob((blob) => resolve(blob), "image/jpeg", 0.72);
    });
  }

  async function download() {
    const format = currentFormat();
    const copy = readCopy();
    if (!copy || busy || !ffmpeg) return;
    playToken += 1;
    busy = true;
    refresh();
    progress.textContent = "Saving the film…";
    const body = new FormData();
    body.append("fps", String(FPS));
    try {
      const count = Math.min(MAX_SECONDS * FPS, Math.ceil(format.seconds(copy) * FPS));
      for (let frame = 0; frame < count; frame += 1) {
        showFrame(format, copy, frame / FPS);
        const blob = await jpegBlob();
        if (!blob) throw new Error("frame");
        body.append("frames", blob, `frame-${String(frame + 1).padStart(3, "0")}.jpg`);
        if (frame % 20 === 0) progress.textContent = `Saving the film… ${frame + 1} of ${count}`;
      }
      const response = await fetch("/api/motion", { method: "POST", body });
      if (!response.ok) {
        let message = "The film could not be saved.";
        try {
          const payload = await response.json();
          if (payload && payload.error) message = String(payload.error);
        } catch (err) { /* keep the fallback */ }
        throw new Error(message);
      }
      const video = await response.blob();
      const url = URL.createObjectURL(video);
      const link = document.createElement("a");
      link.href = url;
      link.download = `motion-${format.id}.mp4`;
      link.click();
      URL.revokeObjectURL(url);
      progress.textContent = "The MP4 downloaded.";
    } catch (err) {
      progress.textContent = err && err.message && err.message !== "frame" ? err.message : "The film could not be saved.";
    } finally {
      busy = false;
      refresh();
    }
  }

  FORMATS.forEach((format) => {
    const option = document.createElement("option");
    option.value = format.id;
    option.textContent = format.name;
    formatSelect.append(option);
  });
  formatSelect.addEventListener("change", buildFields);
  playButton.addEventListener("click", play);
  downloadButton.addEventListener("click", download);
  document.querySelectorAll('input[name="mode"]').forEach((input) => {
    input.addEventListener("change", refresh);
  });

  window.LinkedInReel = {
    isReelMode,
    formats: FORMATS.map((format) => format.id),
    setFfmpeg(on) {
      ffmpegKnown = true;
      ffmpeg = Boolean(on);
      refresh();
    },
  };

  buildFields();
}());
