/* Text preparation for the Docs page that needs no page, so node can test it
 * (tests/docs_text.test.js):
 *
 *   unwrap(text)
 *       Most docs here are hard-wrapped at about 80 columns. The shared
 *       markdown renderer makes every line its own paragraph, so a line that
 *       only continues the one above is joined to it first. Blank lines,
 *       headings, list items, table rows, quotes and code blocks keep their
 *       breaks. A --- front matter block becomes a yaml code block.
 */
((root) => {
  const STARTS_BLOCK = /^\s*([-*+]\s|\d+[.)]\s|#|\||>|```|---\s*$)/;
  const ENDS_BLOCK = /^\s*(#|\||```|---\s*$)/;

  function unwrap(text) {
    let lines = String(text || "").replace(/\r\n/g, "\n").split("\n");
    const out = [];
    if (lines[0] === "---") {
      const end = lines.indexOf("---", 1);
      if (end > 0) {
        out.push("```yaml", ...lines.slice(1, end), "```");
        lines = lines.slice(end + 1);
      }
    }
    let fenced = false;
    let joinable = false;
    for (const line of lines) {
      if (/^\s*```/.test(line)) {
        fenced = !fenced;
        out.push(line);
        joinable = false;
      } else if (fenced || !line.trim()) {
        out.push(line);
        joinable = false;
      } else if (joinable && !STARTS_BLOCK.test(line)) {
        out[out.length - 1] += ` ${line.trim()}`;
      } else {
        out.push(line);
        joinable = !ENDS_BLOCK.test(line);
      }
    }
    return out.join("\n");
  }

  const api = { unwrap };
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.DocsText = api;
})(typeof window !== "undefined" ? window : globalThis);
