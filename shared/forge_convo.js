/* A Claude conversation, drawn: shared by the Claude app (its classic page,
 * Enjoy layout and Docs page, through claude_common.js) and Mission Control's
 * conversation view. Moved here from apps/claude/static/claude_common.js on
 * 2026-10-07 so both apps draw chats with one copy of the code.
 *
 *   ForgeConvo.draw(event, view, { shown(view), scroll(view, force),
 *                                  init(event), browserTool(card),
 *                                  assistant(message, view),
 *                                  step(card, view, block), stepDone(card, view),
 *                                  turnEnd(view, event) })
 *   ForgeConvo.newView(id)   an empty view for one conversation
 *   ForgeConvo.onStatus      where a page's status messages go
 *
 * Events are the Claude app's: Claude Code's stream-json lines plus its own
 * forge_* events. Opt-in extras a page turns on per view, so the Claude app
 * looks exactly as before:
 *   view.thinking = true   draw thinking blocks as folded "Thinking" cards
 *   view.times = true      a small clock time on each message (event.at)
 * and one opt-in hook: with hooks.step a page places each tool card and
 * thinking card itself (Mission Control folds a run of them into one "steps"
 * bar), stepDone(card) tells it a tool call finished and turnEnd(view, event)
 * that a turn ended (event: the "result" line, after its turn-end line is
 * drawn); without it the cards go into the reply as before. And two
 * events only Mission Control sends: forge_user may carry `via`
 * (where a message came from, e.g. "board note #997"), and forge_sys is a
 * plain grey line. ForgeConvo.copyImageUrl = null hides the Copy image
 * button on pages without the Claude app's clipboard route, and
 * ForgeConvo.filesBase is where attached pictures load from ("/api", the
 * Claude app's own; Mission Control sets its proxy "/api/claude").
 */
(() => {
const HEADERS = { "Content-Type": "application/json", "X-Forge": "1" };

async function api(path, options = {}) {
  const r = await fetch(path, { ...options, headers: { ...HEADERS, ...(options.headers || {}) } });
  if (!r.ok) {
    let detail = r.statusText;
    try { detail = (await r.json()).detail || detail; } catch (e) {}
    throw new Error(detail);
  }
  return r.json();
}
const post = (path, body) => api(path, { method: "POST", body: JSON.stringify(body || {}) });

function escapeHtml(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function inline(text) {
  let s = escapeHtml(text);
  s = s.replace(/`([^`]+)`/g, "<code>$1</code>");
  s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  s = s.replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a data-url="$2" title="$2">$1</a>');
  s = s.replace(/(^|[\s(])(https?:\/\/[^\s<)"]+)/g, '$1<a data-url="$2" title="$2">$2</a>');
  return s;
}

// Enough Markdown for Claude's answers: fenced code, headings, lists,
// paragraphs, inline code, bold and links. Everything is escaped first.
function markdown(text) {
  const out = [];
  const parts = String(text || "").split(/```/);
  parts.forEach((part, i) => {
    if (i % 2 === 1) {
      const body = part.replace(/^[\w+-]*\n/, "");
      out.push(`<pre><code>${escapeHtml(body)}</code></pre>`);
      return;
    }
    let list = null;
    let table = null;
    const flushList = () => { if (list) { out.push(`<${list.tag}>${list.items.join("")}</${list.tag}>`); list = null; } };
    const flush = () => { flushList(); flushTable(); };
    // | a | b | rows with a |---| line under the first are a table; without
    // one they stay plain lines
    const cells = (line) => line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());
    const flushTable = () => {
      if (!table) return;
      const rows = table;
      table = null;
      if (rows.length < 2 || !/^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(rows[1])) {
        rows.forEach((line) => out.push(`<p>${inline(line)}</p>`));
        return;
      }
      const align = cells(rows[1]).map((c) => (c.endsWith(":") ? (c.startsWith(":") ? "center" : "right") : ""));
      const cell = (tag, text, i) => `<${tag}${align[i] ? ` style="text-align:${align[i]}"` : ""}>${inline(text)}</${tag}>`;
      const head = cells(rows[0]).map((c, i) => cell("th", c, i)).join("");
      const body = rows.slice(2).map((r) => `<tr>${cells(r).map((c, i) => cell("td", c, i)).join("")}</tr>`).join("");
      out.push(`<div class="table-wrap"><table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`);
    };
    part.split(/\n{2,}/).forEach((block) => {
      block.split("\n").forEach((line) => {
        if (line.trim().startsWith("|")) {
          flushList();
          (table = table || []).push(line);
          return;
        }
        flushTable();
        const bullet = line.match(/^\s*[-*]\s+(.*)/);
        const numbered = line.match(/^\s*\d+[.)]\s+(.*)/);
        const heading = line.match(/^(#{1,3})\s+(.*)/);
        if (bullet || numbered) {
          const tag = bullet ? "ul" : "ol";
          if (!list || list.tag !== tag) { flushList(); list = { tag, items: [] }; }
          list.items.push(`<li>${inline((bullet || numbered)[1])}</li>`);
        } else if (heading) {
          flush();
          out.push(`<h${heading[1].length + 1}>${inline(heading[2])}</h${heading[1].length + 1}>`);
        } else if (line.trim()) {
          flush();
          out.push(`<p>${inline(line)}</p>`);
        }
      });
      flush();
    });
  });
  return out.join("");
}

function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
}

const isImage = (name) => /\.(png|jpe?g|gif|webp)$/i.test(String(name || ""));
const fileUrl = (conv, name) =>
  `${(window.ForgeConvo && window.ForgeConvo.filesBase) || "/api"}/conversations/${encodeURIComponent(conv)}/files/${encodeURIComponent(String(name).split("/").pop())}`;

// An attached file as a chip: images show a thumbnail, other files an icon.
function fileChip(conv, name) {
  const base = String(name).split("/").pop();
  const chip = el("span", "chip" + (isImage(base) ? " image" : ""));
  if (isImage(base) && conv) {
    const img = el("img");
    img.src = fileUrl(conv, base);
    img.alt = base;
    chip.appendChild(img);
  } else chip.appendChild(document.createTextNode("📄 "));
  chip.appendChild(el("span", "", base));
  return chip;
}

// An image in the conversation with a Copy button. WebKit's own right-click
// "Copy Image" works too; the button goes through the backend (wl-copy), which
// the desktop clipboard always accepts.
function shot(src, alt) {
  const fig = el("figure", "shot");
  const img = el("img");
  img.src = src;
  img.alt = alt || "image";
  const copy = el("button", "copy-img", "Copy image");
  copy.type = "button";
  copy.addEventListener("click", async (e) => {
    e.stopPropagation();
    try {
      const blob = await (await fetch(img.src)).blob();
      await post(ForgeConvo.copyImageUrl, { data: await readBase64(blob), media: blob.type || "image/png" });
      copy.textContent = "Copied ✓";
    } catch (err) {
      copy.textContent = "Could not copy";
      ForgeConvo.onStatus("Copy image: " + err.message);
    }
    setTimeout(() => { copy.textContent = "Copy image"; }, 1800);
  });
  if (ForgeConvo.copyImageUrl) fig.append(img, copy);
  else fig.append(img);
  return fig;
}

// One reply can arrive as several "assistant" events with the same id, one
// per content block (thinking, text, a tool call...). Each block keeps its own
// slot by its position in the reply, so a later block never wipes an earlier
// one: clearing the box per event is what made updates vanish when a tool
// call followed them (A29).
function claudeMessage(id, view) {
  let entry = view.live.get(id);
  if (!entry) {
    const box = el("div", "msg claude");
    entry = { box, slots: [], next: 0 };
    view.live.set(id, entry);
    view.box.appendChild(box);
  }
  return entry;
}

// A small clock time under a message, for pages that set view.times.
function stamp(box, at, view, first) {
  if (!view.times || !at) return;
  const when = new Date(at);
  if (Number.isNaN(when.getTime())) return;
  const label = when.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  if (label === view.lastStamp) return; // one clock per minute, not one per tool call
  view.lastStamp = label;
  const t = el("time", "at", label);
  t.dateTime = when.toISOString();
  if (first) box.prepend(t);
  else box.appendChild(t);
}

// A thinking block as a folded card (view.thinking). Claude Code keeps only
// a signature for some of them; those say so instead of showing nothing.
function thinkingCard(block) {
  const text = String(block.thinking || "").trim();
  const card = el("details", "thinking" + (text ? "" : " hidden-text"));
  const summary = el("summary");
  summary.append(el("span", "name", text ? "Thinking" : "Thought"), el("span", "brief", text ? text.split("\n")[0].slice(0, 140) : "the reasoning was not kept in the transcript"));
  card.appendChild(summary);
  if (text) {
    const body = el("div", "think-body");
    body.innerHTML = markdown(text);
    card.appendChild(body);
  }
  return card;
}

function textSlot(entry, index) {
  if (!entry.slots[index]) {
    const node = el("div", "bubble");
    entry.box.appendChild(node);
    entry.slots[index] = { node, raw: "" };
  }
  return entry.slots[index];
}

function toolBrief(block) {
  const input = block.input || {};
  return input.url || input.query || input.command || input.file_path || input.pattern || input.description
    || (input.tab !== undefined ? `tab ${input.tab}` : "") || "";
}

function toolCard(block, view) {
  const browser = String(block.name).startsWith("mcp__forge-browser__");
  const card = el("details", `toolcard pending${browser ? " browser" : ""}`);
  const summary = el("summary");
  const name = browser ? `🌐 Browser: ${block.name.split("__").pop()}` : `⚙ ${block.name}`;
  summary.append(el("span", "name", name), el("span", "brief", toolBrief(block)), el("span", "state"));
  const input = el("pre", "", JSON.stringify(block.input || {}, null, 2));
  card.append(summary, input);
  view.tools.set(block.id, card);
  return card;
}

// Streamed text is drawn at most once per STREAM_MS, not per delta: parsing
// and redrawing the whole reply on every word kept the panel near a full
// core while Claude wrote (Emerson #185).
const STREAM_MS = 100;
const pending = new Map(); // text slot -> its page's scroll
let flushTimer = 0;

function flushStream() {
  flushTimer = 0;
  const scrolls = new Set(pending.values());
  pending.forEach((_, slot) => { slot.node.innerHTML = markdown(slot.raw); });
  pending.clear();
  scrolls.forEach((scroll) => scroll());
}

function draw(event, view, hooks = {}) {
  const log = view.box;
  const scroll = (force) => hooks.scroll && hooks.scroll(view, force);
  if (hooks.shown) hooks.shown(view);
  if (event.type === "forge_persona") view.persona = event;
  switch (event.type) {
    case "forge_user": {
      const box = el("div", "msg user");
      if (event.text) box.appendChild(el("div", "bubble", event.text));
      if ((event.files || []).length) {
        const files = el("div", "files");
        event.files.filter((f) => !isImage(f)).forEach((f) => files.appendChild(fileChip(view.id, f)));
        if (files.children.length) box.appendChild(files);
        event.files.filter(isImage).forEach((f) => box.appendChild(shot(fileUrl(view.id, f), f)));
      }
      if (event.during_turn) box.appendChild(el("div", "joined", "added while Claude was working"));
      if (event.via) box.appendChild(el("div", "joined via", event.via));
      stamp(box, event.at, view);
      log.appendChild(box);
      scroll(true);
      break;
    }
    case "system":
      if (event.subtype === "init" && hooks.init) hooks.init(event);
      if (event.subtype === "compact_boundary") {
        const meta = event.compact_metadata || {};
        const before = meta.pre_tokens ? ` (from ${Math.round(meta.pre_tokens / 1000)}k tokens)` : "";
        log.appendChild(el("div", "divider", `conversation compacted${before}`));
        scroll();
      }
      break;
    case "forge_sys":
      log.appendChild(el("div", event.tone === "bad" ? "sys bad" : "sys", event.text || ""));
      scroll();
      break;
    case "forge_asked":
      log.appendChild(el("div", event.error ? "sys bad" : "sys", event.error
        ? `Claude asked to run ${event.command}, but it could not be sent: ${event.error}`
        : `Claude asked to run ${event.command}`));
      scroll();
      break;
    case "stream_event": {
      const ev = event.event || {};
      if (ev.type === "message_start" && ev.message) view.streaming = ev.message.id;
      if (ev.type === "content_block_delta" && ev.delta && ev.delta.type === "text_delta" && view.streaming) {
        const entry = claudeMessage(view.streaming, view);
        const slot = textSlot(entry, Number.isInteger(ev.index) ? ev.index : entry.next);
        slot.raw += ev.delta.text;
        pending.set(slot, scroll);
        if (!flushTimer) flushTimer = setTimeout(flushStream, STREAM_MS);
      }
      break;
    }
    case "assistant": {
      const message = event.message || {};
      const entry = claudeMessage(message.id || `m${event.seq}`, view);
      const firstSight = !entry.stamped;
      (message.content || []).forEach((block) => {
        const index = entry.next++;
        if (block.type === "thinking" && view.thinking) {
          const card = thinkingCard(block);
          if (hooks.step) hooks.step(card, view, block);
          else entry.box.appendChild(card);
        } else if (block.type === "text" && block.text) {
          const slot = textSlot(entry, index);
          slot.raw = block.text;
          pending.delete(slot);
          slot.node.innerHTML = markdown(block.text);
        } else if (block.type === "tool_use") {
          const fresh = !view.tools.has(block.id);
          const card = view.tools.get(block.id) || toolCard(block, view);
          if (hooks.step) { if (fresh) hooks.step(card, view, block); }
          else if (card.parentNode !== entry.box) entry.box.appendChild(card);
          if (fresh && String(block.name || "").startsWith("mcp__forge-browser__") && hooks.browserTool) hooks.browserTool(card);
        }
      });
      if (firstSight && view.times && event.at) {
        entry.stamped = true;
        stamp(entry.box, event.at, view, true);
      }
      if (hooks.assistant) hooks.assistant(message, view);
      scroll();
      break;
    }
    case "user": {
      const content = (event.message || {}).content;
      (Array.isArray(content) ? content : []).forEach((block) => {
        if (block.type !== "tool_result") return;
        const card = view.tools.get(block.tool_use_id);
        if (!card) return;
        const text = Array.isArray(block.content)
          ? block.content.map((c) => c.text || (c.type === "image" ? "[image]" : "")).join("\n")
          : String(block.content || "");
        card.classList.remove("pending");
        card.classList.add(block.is_error ? "error" : "done");
        card.appendChild(el("pre", "", text.length > 4000 ? text.slice(0, 4000) + "\n…" : text));
        (Array.isArray(block.content) ? block.content : []).forEach((c) => {
          const src = c.type === "image" && c.source && c.source.type === "base64" && c.source.data;
          if (src) card.appendChild(shot(`data:${c.source.media_type || "image/png"};base64,${src}`));
        });
        // a coloured tag on the closed card says a picture is inside (Emerson)
        const pics = card.querySelectorAll(":scope > .shot").length;
        if (pics && !card.classList.contains("has-pic")) {
          card.classList.add("has-pic");
          card.querySelector("summary .state").before(el("span", "pic-tag", pics > 1 ? `🖼 ${pics} pictures` : "🖼 picture"));
        }
        if (hooks.stepDone) hooks.stepDone(card, view);
      });
      break;
    }
    case "result": {
      const seconds = ((event.duration_ms || 0) / 1000).toFixed(1);
      const cost = event.total_cost_usd ? ` · $${Number(event.total_cost_usd).toFixed(4)}` : "";
      if (event.is_error || (event.subtype && event.subtype !== "success")) {
        log.appendChild(el("div", "sys bad", `Claude stopped: ${event.subtype || "error"} ${event.result || ""}`));
      }
      log.appendChild(el("div", "turn-end", `${seconds}s${cost}`));
      log.querySelectorAll(".toolcard.pending").forEach((c) => c.classList.replace("pending", "done"));
      if (hooks.turnEnd) hooks.turnEnd(view, event);
      scroll();
      break;
    }
    case "forge_exit": {
      // a card, like a failed tool call: what happened, then its error output
      const card = el("div", "crash-card");
      card.append(el("div", "crash-head", `Claude Code stopped unexpectedly (exit code ${event.code}). Send a message to carry on.`));
      if (event.stderr) card.append(el("pre", "", event.stderr));
      log.appendChild(card);
      scroll();
      break;
    }
    case "forge_resumed":
      log.appendChild(el("div", "sys", "Forge restarted while this was working, so it carries on from here."));
      break;
    case "forge_stopped":
      log.appendChild(el("div", "sys", event.during_turn ? "Stopped. The next message carries on from here." : "Stopped."));
      break;
    default:
      break;
  }
}

function readBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",")[1] || "");
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}


function newView(id) {
  return { id, box: el("div", "view"), live: new Map(), tools: new Map(), seq: -1,
    streaming: null, persona: null, scroll: null, bulk: false, meta: null, busy: false, filling: null };
}

window.ForgeConvo = {
  HEADERS, api, post, escapeHtml, inline, markdown, el, isImage, fileUrl, fileChip, shot, readBase64,
  claudeMessage, textSlot, toolBrief, toolCard, thinkingCard, draw, newView, onStatus: () => {},
  copyImageUrl: "/api/clipboard/image", filesBase: "/api",
};
})();
