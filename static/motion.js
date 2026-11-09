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

  function layout(board, diagramTop) {
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

  function draw(ctx, board, time) {
    if (!ctx || !board) return;
    paintBackdrop(ctx);
    const headlineBottom = drawHeadline(ctx, board);
    const boxes = layout(board, headlineBottom + 36);
    (board.edges || []).forEach((edge) => {
      drawEdge(ctx, boxes[edge.from], boxes[edge.to], edgeProgress(board, edge, time), edge.tone, time);
    });
    Object.keys(boxes).forEach((id) => {
      const box = boxes[id];
      drawNode(ctx, box, nodeProgress(board, box.node, time), time);
    });
    drawCaption(ctx, board, time);
  }

  window.LinkedInMotion = { draw, duration, beatAt, width: W, height: H };
})();
