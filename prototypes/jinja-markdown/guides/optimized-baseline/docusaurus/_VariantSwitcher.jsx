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
  const tested = data.ci.some((c) => data.order.every((d) => c[d] === current[d]));
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
      <span style={{fontSize: '0.8rem'}}>
        {tested ? '✓ CI-tested configuration' : '⚠ supported, not CI-tested'}
      </span>
    </div>
  );
}
