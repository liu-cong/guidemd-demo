"""Standalone interactive picker page: all variants pre-rendered into one
self-contained HTML file (markdown converted client-side by CDN marked.js —
a demo artifact; the docs-site integration is docusaurus.py)."""

import json

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>@@TITLE@@ — llm-d guide</title>
<script src="https://cdn.jsdelivr.net/npm/marked@12/marked.min.js"></script>
<style>
  :root { --accent: #0e7490; --border: #e2e2e8; --muted: #6b6b76; }
  body { font: 16px/1.6 -apple-system, "Segoe UI", sans-serif; margin: 0; color: #1a1a22; }
  header { position: sticky; top: 0; background: #fff; border-bottom: 1px solid var(--border);
           padding: 0.75rem 2rem; display: flex; gap: 1.2rem; align-items: center;
           flex-wrap: wrap; z-index: 10; }
  header h1 { font-size: 1rem; margin: 0 1rem 0 0; }
  .dim label { display: block; font-size: 0.7rem; text-transform: uppercase;
               letter-spacing: 0.05em; color: var(--muted); }
  .dim select { font-size: 0.9rem; padding: 0.25rem 0.5rem; border: 1px solid var(--border);
                border-radius: 6px; background: #fff; }
  #tested { margin-left: auto; font-size: 0.8rem; }
  #tested .yes { color: #15803d; } #tested .no { color: #b45309; }
  main { max-width: 860px; margin: 0 auto; padding: 1rem 2rem 4rem; }
  main pre { background: #16161d; color: #e8e8f0; padding: 1rem; border-radius: 8px;
             overflow-x: auto; font-size: 0.85rem; line-height: 1.5; }
  main code { font-family: ui-monospace, "SF Mono", Menlo, monospace; }
  main :not(pre) > code { background: #ecfeff; padding: 0.1rem 0.35rem; border-radius: 4px;
                          font-size: 0.85em; }
  main blockquote { border-left: 3px solid var(--accent); margin: 1rem 0;
                    padding: 0.25rem 1rem; background: #f8fdfe; color: #3a3a44; }
  main h2 { border-bottom: 1px solid var(--border); padding-bottom: 0.3rem; margin-top: 2.5rem; }
  main table { border-collapse: collapse; }
  main th, main td { border: 1px solid var(--border); padding: 0.35rem 0.7rem; }
</style>
</head>
<body>
<header id="picker"><h1>@@TITLE@@</h1></header>
<main id="content"></main>
<script>
const GUIDE = @@DATA@@;
const ORDER = GUIDE.order, SUPPORTED = GUIDE.supported;
const key = c => ORDER.map(d => c[d]).join('|');
const prefixMatch = (c, picks, upto) => ORDER.slice(0, upto).every(d => c[d] === picks[d]);
const availableAt = (k, picks) => {
  const seen = [];
  for (const c of SUPPORTED)
    if (prefixMatch(c, picks, k) && !seen.includes(c[ORDER[k]])) seen.push(c[ORDER[k]]);
  return seen;
};
const header = document.getElementById('picker'), selects = {};
ORDER.forEach((dim, k) => {
  const spec = GUIDE.dimensions[dim], wrap = document.createElement('div');
  wrap.className = 'dim';
  const label = document.createElement('label');
  label.textContent = spec.label || dim;
  const sel = document.createElement('select');
  for (const v of spec.values) {
    const o = document.createElement('option');
    o.value = String(v); o.textContent = String(v); sel.appendChild(o);
  }
  sel.addEventListener('change', () => cascade(k));
  wrap.append(label, sel); header.appendChild(wrap); selects[dim] = sel;
});
const tested = document.createElement('div');
tested.id = 'tested'; header.appendChild(tested);
function cascade(changed) {
  const picks = {};
  ORDER.forEach((dim, k) => {
    const avail = availableAt(k, picks);
    let v = selects[dim].value;
    if (k > changed || !avail.includes(v))
      v = avail.includes(GUIDE.defaults[dim]) ? GUIDE.defaults[dim] : avail[0];
    picks[dim] = v;
  });
  show(picks);
}
function show(cell, updateUrl = true) {
  ORDER.forEach(d => { selects[d].value = cell[d]; });
  const picks = {};
  ORDER.forEach((dim, k) => {
    const avail = availableAt(k, picks);
    for (const o of selects[dim].options) o.disabled = !avail.includes(o.value);
    picks[dim] = cell[dim];
  });
  document.getElementById('content').innerHTML = marked.parse(GUIDE.docs[key(cell)]);
  const isTested = GUIDE.ci.some(c => ORDER.every(d => c[d] === cell[d]));
  tested.innerHTML = isTested ? '<span class="yes">✓ CI-tested configuration</span>'
                              : '<span class="no">⚠ supported, not CI-tested</span>';
  if (updateUrl) history.replaceState(null, '', '?' + new URLSearchParams(cell));
}
const params = new URLSearchParams(location.search);
const wanted = Object.fromEntries(ORDER.map(d => [d, params.get(d) || GUIDE.defaults[d]]));
const initial = SUPPORTED.find(c => ORDER.every(d => c[d] === wanted[d]))
  || SUPPORTED.find(c => ORDER.every(d => c[d] === GUIDE.defaults[d])) || SUPPORTED[0];
show({ ...initial }, false);
</script>
</body>
</html>
"""


def render_html(guide):
    docs = {}
    for cell in guide.matrix.supported:
        md, _ = guide.render(cell)
        docs["|".join(cell[d] for d in guide.matrix.order)] = md
    data = json.dumps({
        "order": guide.matrix.order,
        "dimensions": {d: {"label": s.get("label", d), "values": guide.matrix.values[d]}
                       for d, s in guide.matrix.dims.items()},
        "defaults": guide.matrix.defaults,
        "supported": guide.matrix.supported,
        "ci": guide.matrix.ci,
        "docs": docs,
    }).replace("</", "<\\/")
    title = guide.meta.get("title", guide.meta.get("name", ""))
    return HTML_PAGE.replace("@@TITLE@@", title).replace("@@DATA@@", data)
