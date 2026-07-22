"""llm-d.ai integration: per-variant static .mdx pages + VariantSwitcher.

The default variant is the listed, canonical page; every other supported
variant is `unlisted: true` (reachable via the switcher / deep links,
hidden from sidebar, search and sitemap). All content is fully static —
the switcher only navigates between real pages.
"""

import json
import re
from pathlib import Path

from .matrix import variant_slug

ALERT_MAP = {"NOTE": "note", "TIP": "tip", "IMPORTANT": "info",
             "WARNING": "warning", "CAUTION": "danger"}
RE_ALERT = re.compile(r"^> \[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*$")


def alerts_to_admonitions(md):
    """GitHub `> [!NOTE]` blockquotes -> Docusaurus `:::note` admonitions."""
    out, lines, i = [], md.splitlines(), 0
    while i < len(lines):
        m = RE_ALERT.match(lines[i])
        if not m:
            out.append(lines[i])
            i += 1
            continue
        out.append(f":::{ALERT_MAP[m.group(1)]}")
        i += 1
        while i < len(lines) and lines[i].startswith(">"):
            out.append(lines[i][2:] if lines[i].startswith("> ") else lines[i][1:])
            i += 1
        out.append(":::")
    return "\n".join(out) + "\n"


def emit_docusaurus(guide, out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    order = guide.matrix.order
    default = guide.matrix.default_cell()
    title = guide.meta.get("title", guide.meta.get("name", "guide"))
    slugs = {}
    for cell in guide.matrix.supported:
        md, _ = guide.render(cell)
        body = alerts_to_admonitions(md)
        body = re.sub(r"^# .*\n", "", body, count=1)  # title comes from front matter
        is_default = cell == default
        slug = "index" if is_default else variant_slug(cell, order)
        slugs["|".join(cell[d] for d in order)] = slug
        fm = ["---", f"title: {title}"]
        if not is_default:
            fm += ["unlisted: true"]
        fm += ["---", "",
               "import VariantSwitcher from './_VariantSwitcher';", "",
               f"<VariantSwitcher current={{{json.dumps(dict(cell))}}} />", ""]
        (out / f"{slug}.mdx").write_text("\n".join(fm) + "\n" + body)
    data = {"order": order,
            "dimensions": {d: {"label": s.get("label", d),
                               "values": guide.matrix.values[d]}
                           for d, s in guide.matrix.dims.items()},
            "defaults": guide.matrix.defaults,
            "supported": guide.matrix.supported,
            "slugs": slugs}
    (out / "_variants.json").write_text(json.dumps(data, indent=1))
    (out / "_VariantSwitcher.jsx").write_text(VARIANT_SWITCHER)
    return len(guide.matrix.supported)


VARIANT_SWITCHER = """\
// Reference implementation — pairs with the .mdx pages emitted by
// `guidegen.py emit-docusaurus`. Cascading pickers in dimension order;
// picking a variant NAVIGATES to that variant's own static page, so every
// variant is a real Docusaurus doc (theme, search, versioning included).
import React from 'react';
import {useHistory} from '@docusaurus/router';
import useBaseUrl from '@docusaurus/useBaseUrl';
import data from './_variants.json';

const key = (cell) => data.order.map((d) => cell[d]).join('|');
const availableAt = (k, picks) => {
  const seen = [];
  for (const c of data.supported) {
    if (data.order.slice(0, k).every((d) => c[d] === picks[d]) &&
        !seen.includes(c[data.order[k]])) seen.push(c[data.order[k]]);
  }
  return seen;
};

export default function VariantSwitcher({current}) {
  const history = useHistory();
  const base = useBaseUrl('.');
  const go = (cell) => {
    const slug = data.slugs[key(cell)];
    history.push(slug === 'index' ? base : `${base}/${slug}`);
  };
  const onChange = (dim, value) => {
    const changed = data.order.indexOf(dim);
    const picks = {};
    data.order.forEach((d, k) => {
      const avail = availableAt(k, picks);
      let v = k === changed ? value : current[d];
      if (k > changed || !avail.includes(v))
        v = avail.includes(data.defaults[d]) ? data.defaults[d] : avail[0];
      picks[d] = v;
    });
    go(picks);
  };
  const picks = {};
  return (
    <div style={{display: 'flex', gap: '1rem', flexWrap: 'wrap',
                 alignItems: 'flex-end', margin: '1rem 0'}}>
      {data.order.map((dim, k) => {
        const avail = availableAt(k, picks);
        picks[dim] = current[dim];
        return (
          <label key={dim} style={{fontSize: '0.75rem'}}>
            {data.dimensions[dim].label || dim}
            <br />
            <select value={current[dim]} onChange={(e) => onChange(dim, e.target.value)}>
              {data.dimensions[dim].values.map((v) => (
                <option key={v} value={v} disabled={!avail.includes(v)}>{v}</option>
              ))}
            </select>
          </label>
        );
      })}
    </div>
  );
}
"""
