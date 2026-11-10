/* Portrait explainer: a headline, a diagram that connects, and a changing bottom line. */
(function () {
  "use strict";

  const W = 1080;
  const H = 1350;
  const FONT = '"Avenir Next", "Segoe UI", "Helvetica Neue", sans-serif';

  function clamp01(value) {
    return Math.max(0, Math.min(1, value));
  }

  function ease(value) {
    const t = clamp01(value);
    return t * t * (3 - 2 * t);
  }

  function duration(board) {
    const beats = (board.beats || []).length || 1;
    return beats * (Number(board.seconds) || 3.2) + (Number(board.tail) || 1.4);
  }

  function beatAt(board, time) {
    const beats = board.beats || [];
    if (!beats.length) return 0;
    const index = Math.floor(Math.max(0, time) / (Number(board.seconds) || 3.2));
    return Math.max(0, Math.min(beats.length - 1, index));
  }

  function bare(word) {
    return String(word || "").toLowerCase().replace(/^[^a-z0-9]+|[^a-z0-9]+$/g, "");
  }

  function fit(ctx, text, maxWidth, maxLines, weight, start, minSize) {
    let size = start;
    const words = String(text || "").split(/\s+/).filter(Boolean);
    while (size >= minSize) {
      ctx.font = `${weight} ${size}px ${FONT}`;
      const lines = wrapWords(ctx, words, maxWidth, maxLines);
      if (lines.join(" ") === words.join(" ") || size === minSize) return { size, lines };
      size -= 2;
    }
    ctx.font = `${weight} ${minSize}px ${FONT}`;
    return { size: minSize, lines: wrapWords(ctx, words, maxWidth, maxLines) };
  }

  function wrapWords(ctx, words, maxWidth, maxLines) {
    const lines = [];
    let current = "";
    for (let index = 0; index < words.length; index += 1) {
      const word = words[index];
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

  function roundRect(ctx, x, y, width, height, radius) {
    const r = Math.min(radius, width / 2, height / 2);
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + width, y, x + width, y + height, r);
    ctx.arcTo(x + width, y + height, x, y + height, r);
    ctx.arcTo(x, y + height, x, y, r);
    ctx.arcTo(x, y, x + width, y, r);
    ctx.closePath();
  }

  function paintBackdrop(ctx) {
    const sky = ctx.createLinearGradient(0, 0, 0, H);
    sky.addColorStop(0, "#0b1826");
    sky.addColorStop(0.45, "#07131f");
    sky.addColorStop(1, "#050d16");
    ctx.fillStyle = sky;
    ctx.fillRect(0, 0, W, H);
    const glow = ctx.createRadialGradient(520, 760, 30, 540, 780, 640);
    glow.addColorStop(0, "rgba(28, 96, 138, 0.42)");
    glow.addColorStop(1, "rgba(28, 96, 138, 0)");
    ctx.fillStyle = glow;
    ctx.fillRect(0, 0, W, H);
    ctx.fillStyle = "rgba(150, 190, 214, 0.16)";
    for (let y = 430; y <= 1080; y += 36) {
      for (let x = 72; x <= 1008; x += 36) {
        ctx.fillRect(x, y, 1.5, 1.5);
      }
    }
    const shade = ctx.createRadialGradient(540, 700, 240, 540, 700, 860);
    shade.addColorStop(0, "rgba(0, 0, 0, 0)");
    shade.addColorStop(1, "rgba(0, 0, 0, 0.38)");
    ctx.fillStyle = shade;
    ctx.fillRect(0, 0, W, H);
  }

  function drawHeadline(ctx, board) {
    const inset = 72;
    const emphasis = new Set((board.emphasis || []).map(bare));
    ctx.textBaseline = "top";
    ctx.font = `600 20px ${FONT}`;
    if ("letterSpacing" in ctx) ctx.letterSpacing = "3.5px";
    ctx.fillStyle = "#8ec8e6";
    const eyebrow = String(board.eyebrow || "").toUpperCase();
    let y = 78;
    if (eyebrow) {
      ctx.fillText(eyebrow, inset, y);
      y += 36;
      ctx.fillStyle = "#5ec4ef";
      ctx.fillRect(inset, y, 56, 4);
      y += 28;
    } else {
      y = 96;
    }
    if ("letterSpacing" in ctx) ctx.letterSpacing = "0px";
    const fitted = fit(ctx, board.headline, W - inset * 2, 3, 700, 58, 40);
    const words = String(board.headline || "").split(/\s+/).filter(Boolean);
    const lineHeight = Math.round(fitted.size * 1.12);
    let cursor = 0;
    ctx.font = `700 ${fitted.size}px ${FONT}`;
    ctx.textBaseline = "top";
    for (const line of fitted.lines) {
      const parts = line.split(/\s+/).filter(Boolean);
      let x = inset;
      for (const part of parts) {
        const word = words[cursor] || part;
        cursor += 1;
        ctx.fillStyle = emphasis.has(bare(word)) ? "#9adfff" : "#f4f8fb";
        ctx.fillText(word, x, y);
        x += ctx.measureText(`${word} `).width;
      }
      y += lineHeight;
    }
    return y;
  }

  function center(box) {
    return { x: box.x + box.w / 2, y: box.y + box.h / 2 };
  }

  function port(box, toward) {
    const from = center(box);
    const dx = toward.x - from.x;
    const dy = toward.y - from.y;
    if (!dx && !dy) return from;
    const sx = dx === 0 ? Infinity : (box.w / 2) / Math.abs(dx);
    const sy = dy === 0 ? Infinity : (box.h / 2) / Math.abs(dy);
    const scale = Math.min(sx, sy) * 0.9;
    return { x: from.x + dx * scale, y: from.y + dy * scale };
  }

  function control(start, end) {
    const dx = end.x - start.x;
    const dy = end.y - start.y;
    const len = Math.hypot(dx, dy) || 1;
    const aligned = Math.abs(dx) < 36 || Math.abs(dy) < 36;
    const bend = aligned ? 0 : Math.min(36, len * 0.12);
    return {
      x: (start.x + end.x) / 2 - (dy / len) * bend,
      y: (start.y + end.y) / 2 + (dx / len) * bend,
    };
  }

  function hasCaptions(board) {
    return (board.beats || []).some((beat) => String(beat.caption || "").trim());
  }

  function bottomLimit(board) {
    return hasCaptions(board) ? 1120 : 1250;
  }

  function layout(board, diagramTop) {
    if (board.layout === "steps" || board.layout === "checklist") return stackLayout(board, diagramTop);
    if (board.layout === "compare") return compareLayout(board, diagramTop);
    return hubLayout(board, diagramTop);
  }

  function stackLayout(board, top) {
    const nodes = board.nodes || [];
    const boxes = {};
    if (!nodes.length) return boxes;
    const gap = 22;
    const room = bottomLimit(board) - top - 24;
    const h = Math.max(84, Math.min(176, (room - gap * (nodes.length - 1)) / nodes.length));
    const total = nodes.length * h + (nodes.length - 1) * gap;
    let y = top + 12 + Math.max(0, (room - total) / 2);
    nodes.forEach((node) => {
      boxes[node.id] = { node, x: 72, y, w: W - 144, h };
      y += h + gap;
    });
    return boxes;
  }

  function compareLayout(board, top) {
    const nodes = board.nodes || [];
    const boxes = {};
    const columns = board.columns || [];
    const headed = columns.some((name) => String(name || "").trim());
    const colW = 440;
    const xs = { left: 72, right: W - 72 - colW };
    const start = top + (headed ? 76 : 20);
    const room = bottomLimit(board) - start - 12;
    ["left", "right"].forEach((side) => {
      const items = nodes.filter((node) => node.place === side);
      if (!items.length) return;
      const gap = 24;
      const h = Math.max(120, Math.min(340, (room - gap * (items.length - 1)) / items.length));
      const total = items.length * h + (items.length - 1) * gap;
      let y = start + Math.max(0, (room - total) / 2);
      items.forEach((node) => {
        boxes[node.id] = { node, x: xs[side], y, w: colW, h };
        y += h + gap;
      });
    });
    return boxes;
  }

  function hubLayout(board, diagramTop) {
    const nodes = board.nodes || [];
    const tops = nodes.filter((node) => node.place === "top");
    const bottoms = nodes.filter((node) => node.place === "bottom");
    const hub = nodes.find((node) => node.place === "hub");
    const side = nodes.find((node) => node.place === "side");
    const boxes = {};
    const hubW = 340;
    const hubH = 128;
    const nodeW = 248;
    const nodeH = 96;
    const gapX = 64;
    const gapY = 86;
    if (hub) boxes[hub.id] = { node: hub, x: 0, y: 0, w: hubW, h: hubH };
    if (side) {
      boxes[side.id] = {
        node: side,
        x: hubW + gapX,
        y: (hubH - nodeH) / 2,
        w: nodeW,
        h: nodeH,
      };
    }
    const placeCentered = (items, y) => {
      if (!items.length) return;
      const total = items.length * nodeW + (items.length - 1) * 28;
      let x = hubW / 2 - total / 2;
      items.forEach((node) => {
        boxes[node.id] = { node, x, y, w: nodeW, h: nodeH };
        x += nodeW + 28;
      });
    };
    placeCentered(tops, -(gapY + nodeH));
    placeCentered(bottoms, hubH + gapY);
    const placed = Object.keys(boxes).map((id) => boxes[id]);
    if (!placed.length) return boxes;
    const minX = Math.min(...placed.map((box) => box.x));
    const maxX = Math.max(...placed.map((box) => box.x + box.w));
    const minY = Math.min(...placed.map((box) => box.y));
    const maxY = Math.max(...placed.map((box) => box.y + box.h));
    const shiftX = W / 2 - (minX + maxX) / 2;
    const shiftY = (diagramTop + 24 + 1104) / 2 - (minY + maxY) / 2;
    placed.forEach((box) => {
      box.x += shiftX;
      box.y += shiftY;
    });
    return boxes;
  }

  function nodeProgress(board, node, time) {
    const seconds = Number(board.seconds) || 3.2;
    let beatIndex = -1;
    let order = 0;
    (board.beats || []).forEach((beat, index) => {
      const at = (beat.reveal || []).indexOf(node.id);
      if (at !== -1) {
        beatIndex = index;
        order = at;
      }
    });
    if (beatIndex < 0) return time > 0.2 ? 1 : 0;
    const start = beatIndex * seconds + 0.12 + order * 0.2;
    return ease((time - start) / 0.42);
  }

  function edgeProgress(board, edge, time) {
    const seconds = Number(board.seconds) || 3.2;
    const start = (Number(edge.beat) || 0) * seconds + 0.48;
    return ease((time - start) / 0.8);
  }

  function drawEdge(ctx, from, to, progress, tone, time) {
    if (progress <= 0.01 || !from || !to) return;
    const start = port(from, center(to));
    const end = port(to, center(from));
    const mid = control(start, end);
    const alert = tone === "alert";
    let length = 0;
    let previous = start;
    for (let step = 1; step <= 16; step += 1) {
      const t = step / 16;
      const u = 1 - t;
      const point = {
        x: u * u * start.x + 2 * u * t * mid.x + t * t * end.x,
        y: u * u * start.y + 2 * u * t * mid.y + t * t * end.y,
      };
      length += Math.hypot(point.x - previous.x, point.y - previous.y);
      previous = point;
    }
    let alpha = 1;
    if (alert && progress >= 1) alpha = 0.72 + 0.28 * (0.5 + 0.5 * Math.sin(time * 3.2));
    ctx.save();
    ctx.globalAlpha = alpha;
    ctx.beginPath();
    ctx.moveTo(start.x, start.y);
    ctx.quadraticCurveTo(mid.x, mid.y, end.x, end.y);
    ctx.setLineDash([length]);
    ctx.lineDashOffset = length * (1 - progress);
    ctx.lineCap = "round";
    ctx.strokeStyle = alert ? "#ef6b5c" : "#7fa9c4";
    ctx.lineWidth = alert ? 4 : 2.5;
    if (alert) {
      ctx.shadowColor = "rgba(239, 107, 92, 0.85)";
      ctx.shadowBlur = 12;
    }
    ctx.stroke();
    ctx.restore();
    ctx.setLineDash([]);
  }

  function drawGlyph(ctx, place, tone, x, y) {
    ctx.save();
    ctx.translate(x, y);
    ctx.strokeStyle = tone === "alert" ? "#ef6b5c" : "#8fd4f5";
    ctx.fillStyle = tone === "alert" ? "rgba(239, 107, 92, 0.16)" : "rgba(94, 196, 239, 0.12)";
    ctx.lineWidth = 2;
    if (place === "hub") {
      ctx.beginPath();
      ctx.moveTo(-12, 4);
      ctx.bezierCurveTo(-12, -8, -4, -12, 0, -6);
      ctx.bezierCurveTo(4, -14, 16, -12, 16, -2);
      ctx.bezierCurveTo(22, -2, 22, 8, 14, 8);
      ctx.lineTo(-10, 8);
      ctx.bezierCurveTo(-16, 8, -16, 4, -12, 4);
      ctx.closePath();
      ctx.fill();
      ctx.stroke();
    } else if (place === "bottom") {
      ctx.beginPath();
      ctx.ellipse(0, -6, 10, 4, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(-10, -6);
      ctx.lineTo(-10, 6);
      ctx.ellipse(0, 6, 10, 4, 0, Math.PI, 0, true);
      ctx.lineTo(10, -6);
      ctx.stroke();
    } else if (tone === "alert") {
      ctx.beginPath();
      ctx.moveTo(0, -12);
      ctx.lineTo(11, 0);
      ctx.lineTo(0, 12);
      ctx.lineTo(-11, 0);
      ctx.closePath();
      ctx.fill();
      ctx.stroke();
    } else {
      roundRect(ctx, -11, -9, 22, 16, 3);
      ctx.fill();
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(-6, -2);
      ctx.lineTo(-1, 3);
      ctx.lineTo(7, -5);
      ctx.stroke();
    }
    ctx.restore();
  }

  function drawNode(ctx, box, progress, time) {
    if (progress <= 0.01) return;
    const node = box.node;
    const alert = node.tone === "alert";
    const hub = node.place === "hub";
    const cx = box.x + box.w / 2;
    const cy = box.y + box.h / 2;
    const scale = 0.92 + 0.08 * progress;
    let alpha = progress;
    if (alert && progress >= 1) alpha = 0.88 + 0.12 * (0.5 + 0.5 * Math.sin(time * 3.2));
    ctx.save();
    ctx.translate(cx, cy);
    ctx.scale(scale, scale);
    ctx.globalAlpha = alpha;
    ctx.translate(-box.w / 2, -box.h / 2);
    ctx.shadowColor = "rgba(0, 0, 0, 0.35)";
    ctx.shadowBlur = hub ? 28 : 16;
    ctx.shadowOffsetY = 8;
    roundRect(ctx, 0, 0, box.w, box.h, hub ? 28 : 18);
    ctx.fillStyle = alert ? "#2a1618" : hub ? "#102c44" : "#0e2234";
    ctx.fill();
    ctx.shadowColor = "transparent";
    ctx.shadowBlur = 0;
    ctx.lineWidth = hub || alert ? 2.5 : 1.5;
    ctx.strokeStyle = alert ? "#ef6b5c" : hub ? "#67c8f0" : "#3f7598";
    ctx.stroke();
    drawGlyph(ctx, node.place, node.tone, 36, box.h / 2);
    const textX = 62;
    const textWidth = box.w - textX - 18;
    const oneLine = fit(ctx, node.label, textWidth, 1, 600, hub ? 30 : 24, 20);
    const fitted = oneLine.lines.join(" ") === String(node.label || "").trim()
      ? oneLine
      : fit(ctx, node.label, textWidth, 2, 600, hub ? 28 : 22, 18);
    ctx.font = `600 ${fitted.size}px ${FONT}`;
    ctx.textBaseline = "middle";
    ctx.fillStyle = "#e8f2f8";
    const block = fitted.lines.length * (fitted.size + 4);
    let textY = box.h / 2 - block / 2 + fitted.size / 2;
    for (const line of fitted.lines) {
      ctx.fillText(line, textX, textY);
      textY += fitted.size + 4;
    }
    ctx.restore();
  }

  function drawCaption(ctx, board, time) {
    const beats = board.beats || [];
    if (!beats.length) return;
    const seconds = Number(board.seconds) || 3.2;
    const index = beatAt(board, time);
    const local = time - index * seconds;
    const fade = index === 0 ? ease(local / 0.4) : ease(local / 0.35);
    const current = beats[index].caption || "";
    const previous = index > 0 ? beats[index - 1].caption || "" : "";
    ctx.textBaseline = "top";
    const drawLine = (text, alpha) => {
      if (!text || alpha <= 0.02) return;
      const fitted = fit(ctx, text, W - 144, 2, 600, 40, 28);
      ctx.globalAlpha = alpha;
      ctx.font = `600 ${fitted.size}px ${FONT}`;
      ctx.fillStyle = "#f7fbfe";
      let y = 1184;
      for (const line of fitted.lines) {
        ctx.fillText(line, 72, y);
        y += fitted.size + 8;
      }
      ctx.globalAlpha = 1;
    };
    if (previous && previous !== current) drawLine(previous, 1 - fade);
    drawLine(current, previous && previous !== current ? fade : Math.max(fade, index === 0 ? fade : 1));
  }

  const PANEL = {
    neutral: { fill: "#0e2234", stroke: "#3f7598", text: "#e8f2f8", badge: "#5ec4ef" },
    muted: { fill: "#161d26", stroke: "#4a5866", text: "#b9c6d0", badge: "#8a97a3" },
    good: { fill: "#0f2c3a", stroke: "#5ec4ef", text: "#f4f8fb", badge: "#7fe0b0" },
  };

  function drawBadge(ctx, kind, label, x, y, color) {
    ctx.save();
    ctx.translate(x, y);
    ctx.lineWidth = 3;
    ctx.strokeStyle = color;
    ctx.fillStyle = "rgba(255, 255, 255, 0.04)";
    ctx.beginPath();
    ctx.arc(0, 0, 24, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
    ctx.lineCap = "round";
    ctx.beginPath();
    if (kind === "number") {
      ctx.fillStyle = color;
      ctx.font = `700 24px ${FONT}`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(String(label), 0, 1);
    } else if (kind === "check") {
      ctx.moveTo(-10, 1);
      ctx.lineTo(-3, 8);
      ctx.lineTo(11, -7);
      ctx.stroke();
    } else if (kind === "cross") {
      ctx.moveTo(-8, -8);
      ctx.lineTo(8, 8);
      ctx.moveTo(8, -8);
      ctx.lineTo(-8, 8);
      ctx.stroke();
    } else {
      ctx.fillStyle = color;
      ctx.arc(0, 0, 7, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.restore();
  }

  function fitBox(ctx, text, width, height) {
    for (let size = 44; size >= 20; size -= 2) {
      const lines = Math.max(1, Math.floor(height / (size * 1.22)));
      const fitted = fit(ctx, text, width, lines, 600, size, size);
      if (fitted.lines.join(" ") === String(text || "").split(/\s+/).filter(Boolean).join(" ")) return fitted;
    }
    return fit(ctx, text, width, Math.max(1, Math.floor(height / 24)), 600, 20, 20);
  }

  function drawPanel(ctx, box, progress) {
    if (progress <= 0.01) return;
    const node = box.node;
    const palette = PANEL[node.tone] || PANEL.neutral;
    let kind = "dot";
    if (node.place === "step") kind = "number";
    else if (node.place === "check" || node.place === "right") kind = "check";
    else if (node.place === "left") kind = "cross";
    const slide = node.place === "right" ? 40 : -40;
    ctx.save();
    ctx.globalAlpha = progress;
    ctx.translate(box.x + slide * (1 - progress), box.y);
    ctx.shadowColor = "rgba(0, 0, 0, 0.35)";
    ctx.shadowBlur = 18;
    ctx.shadowOffsetY = 8;
    roundRect(ctx, 0, 0, box.w, box.h, 20);
    ctx.fillStyle = palette.fill;
    ctx.fill();
    ctx.shadowColor = "transparent";
    ctx.shadowBlur = 0;
    ctx.lineWidth = node.tone === "good" ? 2.5 : 1.5;
    ctx.strokeStyle = palette.stroke;
    ctx.stroke();
    drawBadge(ctx, kind, node.order || "", 52, box.h / 2, palette.badge);
    const textX = 96;
    const fitted = fitBox(ctx, node.label, box.w - textX - 28, box.h - 28);
    ctx.font = `600 ${fitted.size}px ${FONT}`;
    ctx.textBaseline = "middle";
    ctx.fillStyle = palette.text;
    const lineHeight = Math.round(fitted.size * 1.22);
    let textY = box.h / 2 - ((fitted.lines.length - 1) * lineHeight) / 2;
    for (const line of fitted.lines) {
      ctx.fillText(line, textX, textY);
      textY += lineHeight;
    }
    ctx.restore();
  }

  function drawColumns(ctx, board, boxes, top, time) {
    const columns = board.columns || [];
    const placed = Object.keys(boxes).map((id) => boxes[id]);
    const sideProgress = (side) => Math.max(0, ...placed
      .filter((box) => box.node.place === side)
      .map((box) => nodeProgress(board, box.node, time)));
    const left = sideProgress("left");
    const right = sideProgress("right");
    ctx.save();
    ctx.textBaseline = "top";
    ctx.font = `700 26px ${FONT}`;
    if ("letterSpacing" in ctx) ctx.letterSpacing = "3px";
    [["left", 72, left, "#8a97a3"], ["right", W - 72 - 440, right, "#7fe0b0"]].forEach(([side, x, progress, color], index) => {
      const name = String(columns[index] || "").toUpperCase();
      if (!name || progress <= 0.01) return;
      ctx.globalAlpha = progress;
      ctx.fillStyle = color;
      ctx.fillText(name, x + 4, top + 24);
      ctx.fillRect(x + 4, top + 62, 40, 3);
    });
    if ("letterSpacing" in ctx) ctx.letterSpacing = "0px";
    const ys = placed.map((box) => box.y + box.h / 2);
    if (right > 0.01 && ys.length) {
      const y = (Math.min(...ys) + Math.max(...ys)) / 2;
      ctx.globalAlpha = right;
      ctx.strokeStyle = "#5ec4ef";
      ctx.lineWidth = 4;
      ctx.lineCap = "round";
      ctx.beginPath();
      ctx.moveTo(526 - 12 * (1 - right), y - 16);
      ctx.lineTo(546, y);
      ctx.lineTo(526 - 12 * (1 - right), y + 16);
      ctx.stroke();
    }
    ctx.restore();
  }

  function drawFocus(ctx, board, time) {
    const inset = 72;
    const emphasis = new Set((board.emphasis || []).map(bare));
    const question = board.layout === "question";
    const options = (board.nodes || []).filter((node) => node.place === "option");
    ctx.textBaseline = "top";
    const eyebrow = String(board.eyebrow || "").toUpperCase();
    if (eyebrow) {
      ctx.font = `600 22px ${FONT}`;
      if ("letterSpacing" in ctx) ctx.letterSpacing = "3.5px";
      ctx.fillStyle = "#8ec8e6";
      ctx.fillText(eyebrow, inset, 96);
      if ("letterSpacing" in ctx) ctx.letterSpacing = "0px";
    }
    const words = String(board.headline || "").split(/\s+/).filter(Boolean);
    const fitted = fit(ctx, board.headline, W - inset * 2, 6, 700, 88, 52);
    const lineHeight = Math.round(fitted.size * 1.14);
    const optionRoom = options.length ? 150 : 0;
    const area = bottomLimit(board) - 180;
    const block = fitted.lines.length * lineHeight + optionRoom;
    let y = 180 + Math.max(0, (area - block) / 2);
    if (question) {
      ctx.save();
      ctx.globalAlpha = 0.1 * ease(time / 0.6);
      ctx.fillStyle = "#5ec4ef";
      ctx.font = `800 520px ${FONT}`;
      ctx.textAlign = "right";
      ctx.fillText("?", W - 30, y - 140);
      ctx.restore();
    }
    ctx.fillStyle = "#5ec4ef";
    ctx.fillRect(inset, y - 44, 96 * ease(time / 0.5), 6);
    ctx.font = `700 ${fitted.size}px ${FONT}`;
    let cursor = 0;
    for (const line of fitted.lines) {
      let x = inset;
      for (const part of line.split(/\s+/).filter(Boolean)) {
        const word = words[cursor] || part;
        const appear = ease((time - 0.15 - cursor * 0.09) / 0.35);
        cursor += 1;
        ctx.globalAlpha = appear;
        ctx.fillStyle = emphasis.has(bare(word)) ? "#9adfff" : "#f4f8fb";
        ctx.fillText(word, x, y + 14 * (1 - appear));
        x += ctx.measureText(`${word} `).width;
      }
      y += lineHeight;
    }
    ctx.globalAlpha = 1;
    if (!options.length) return;
    y += 48;
    ctx.font = `600 32px ${FONT}`;
    let x = inset;
    options.forEach((node) => {
      const progress = nodeProgress(board, node, time);
      const label = String(node.label || "");
      const width = Math.min(W - inset * 2, ctx.measureText(label).width + 72);
      if (x + width > W - inset) {
        x = inset;
        y += 100;
      }
      if (progress > 0.01) {
        ctx.save();
        ctx.globalAlpha = progress;
        ctx.translate(0, 16 * (1 - progress));
        roundRect(ctx, x, y, width, 80, 40);
        ctx.fillStyle = "#0f2c3a";
        ctx.fill();
        ctx.lineWidth = 2;
        ctx.strokeStyle = "#5ec4ef";
        ctx.stroke();
        ctx.fillStyle = "#f4f8fb";
        ctx.textBaseline = "middle";
        ctx.fillText(label, x + 36, y + 41);
        ctx.restore();
      }
      x += width + 24;
    });
  }

  function drawProgress(ctx, board) {
    const count = Number(board.count) || 1;
    if (count < 2) return;
    const position = Math.max(1, Math.min(count, Number(board.position) || 1));
    const gap = 14;
    const dot = 10;
    const wide = 34;
    const total = (count - 1) * (dot + gap) + wide;
    let x = W / 2 - total / 2;
    ctx.save();
    for (let index = 1; index <= count; index += 1) {
      const current = index === position;
      ctx.fillStyle = current ? "#5ec4ef" : index < position ? "rgba(94, 196, 239, 0.45)" : "rgba(150, 190, 214, 0.22)";
      roundRect(ctx, x, 1306, current ? wide : dot, dot, dot / 2);
      ctx.fill();
      x += (current ? wide : dot) + gap;
    }
    ctx.restore();
  }

  function drawFade(ctx, board, time) {
    if (!board.fade) return;
    const total = duration(board);
    const shade = Math.max(1 - clamp01(time / 0.35), clamp01((time - (total - 0.35)) / 0.35));
    if (shade <= 0.01) return;
    ctx.save();
    ctx.globalAlpha = shade;
    ctx.fillStyle = "#050d16";
    ctx.fillRect(0, 0, W, H);
    ctx.restore();
  }

  function draw(ctx, board, time) {
    if (!ctx || !board) return;
    paintBackdrop(ctx);
    if (board.layout === "statement" || board.layout === "question") {
      drawFocus(ctx, board, time);
    } else {
      const headlineBottom = board.headline ? drawHeadline(ctx, board) : drawHeadline(ctx, board) - 40;
      const top = headlineBottom + 36;
      const boxes = layout(board, top);
      const panels = board.layout === "steps" || board.layout === "checklist" || board.layout === "compare";
      if (board.layout === "compare") drawColumns(ctx, board, boxes, top, time);
      (board.edges || []).forEach((edge) => {
        if (panels) return;
        drawEdge(ctx, boxes[edge.from], boxes[edge.to], edgeProgress(board, edge, time), edge.tone, time);
      });
      Object.keys(boxes).forEach((id) => {
        const box = boxes[id];
        const progress = nodeProgress(board, box.node, time);
        if (panels) drawPanel(ctx, box, progress);
        else drawNode(ctx, box, progress, time);
      });
    }
    drawCaption(ctx, board, time);
    drawProgress(ctx, board);
    drawFade(ctx, board, time);
  }

  window.LinkedInMotion = { draw, duration, beatAt, width: W, height: H };
})();
