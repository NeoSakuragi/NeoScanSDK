/* PIECE KNOBS in the Assembly pages (Bruno 2026-10-10: "each special move comes with its key params and default values,
 * adjustable in the Assembly; clearly surface where values are overridden and offer going back to default"). One panel
 * for the arbitration sheet (arbitrage.js: under each picked S- piece of a slot) and the Workshop (workshop.js: under each
 * unlocked special). The knobs are data: review/<f>_workshop.json specials[].knobs (tools/brawler/knobs.py, from
 * arb_pieces/<f>.json): {id, name, unit, default, min, max, step}. Values travel as {knob id: value}, a default left out.
 *   KnobUI.panel({defs, values, label, onChange(values)})  -> element (.reset(): every knob back to its default)
 * E-ink: an overridden knob is shown by text and shape, never colour: its value in bold, "changed from N <unit>", a solid
 * 3 px border round its row; each has "Back to default"; the panel has "Reset all knobs". */
(function () {
  'use strict';
  const h = (t, a, ...kids) => {
    const e = document.createElement(t);
    for (const [k, v] of Object.entries(a || {})) { if (k === 'text') e.textContent = v; else if (k.startsWith('on')) e[k] = v; else if (v !== null && v !== undefined) e.setAttribute(k, v); }
    for (const c of kids.flat()) if (c !== null && c !== undefined) e.append(c);
    return e;
  };
  const CSS = `
.knobs { border: 2px solid #000; padding: 6px 8px; margin: 4px 0; display: flex; flex-direction: column; gap: 6px; background: #fff; color: #000; }
.knobs .khead { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; justify-content: space-between; }
.knobs .khead b { font-size: 14px; }
.knobs .krow { border: 1px dashed #000; padding: 5px 7px; display: grid; grid-template-columns: minmax(0, 1fr); gap: 4px; }
.knobs .krow.over { border: 3px solid #000; }
.knobs .kname { font-size: 14px; }
.knobs .kctl { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.knobs .kctl button { font: inherit; font-size: 14px; min-width: 40px; min-height: 36px; background: #fff; color: #000; border: 2px solid #000; cursor: pointer; }
.knobs .kctl input[type=number] { font: inherit; font-size: 15px; width: 5.5em; border: 2px solid #000; padding: 4px; background: #fff; color: #000; }
.knobs .kctl input[type=range] { flex: 1 1 140px; min-width: 120px; accent-color: #000; }
.knobs .krow.over .kval { font-weight: 700; }
.knobs .kdef { font-size: 13px; }
.knobs .kchg { font-size: 13px; font-weight: 700; }
.knobs .kchg:empty { display: none; }
.knobs .kback { font: inherit; font-size: 13px; background: #fff; color: #000; border: 2px solid #000; padding: 3px 8px; cursor: pointer; }
.knobs .kback[hidden] { display: none; }
.knobs button:focus-visible, .knobs input:focus-visible { outline: 3px dashed #000; outline-offset: 2px; }
.knobs .kreset { font: inherit; font-size: 13px; background: #fff; color: #000; border: 2px solid #000; padding: 3px 8px; cursor: pointer; }`;
  let styled = false;
  const css = () => { if (!styled) { styled = true; document.head.append(h('style', { text: CSS })); } };
  const fmt = v => (Math.round(v * 100) / 100).toString();
  const snap = (d, v) => { v = Math.min(d.max, Math.max(d.min, v)); const n = Math.round((v - d.min) / d.step); return Math.round((d.min + n * d.step) * 10000) / 10000; };

  function panel(o) {
    css();
    const defs = o.defs || [], vals = Object.assign({}, o.values || {});
    const box = h('div', { class: 'knobs', role: 'group', 'aria-label': (o.label || 'Knobs') });
    const resetAll = h('button', { type: 'button', class: 'kreset', text: 'Reset all knobs' });
    const count = h('span', { class: 'kdef' });
    box.append(h('div', { class: 'khead' }, h('b', { text: o.label || 'Knobs' }), count, resetAll));
    const rows = defs.map(d => {
      const num = h('input', { type: 'number', min: String(d.min), max: String(d.max), step: String(d.step), 'aria-label': d.name + ' (' + d.unit + ')' });
      const rng = h('input', { type: 'range', min: String(d.min), max: String(d.max), step: String(d.step), 'aria-label': d.name + ' slider' });
      const minus = h('button', { type: 'button', text: '−', 'aria-label': d.name + ': less' });
      const plus = h('button', { type: 'button', text: '+', 'aria-label': d.name + ': more' });
      const chg = h('span', { class: 'kchg', 'aria-live': 'polite' });
      const back = h('button', { type: 'button', class: 'kback', text: 'Back to default', hidden: '' });
      const row = h('div', { class: 'krow', 'data-knob': d.id },
        h('span', { class: 'kname' }, h('span', { text: d.name + ' ' }), h('span', { class: 'kval' }), h('span', { text: ' ' + d.unit })),
        h('div', { class: 'kctl' }, minus, num, plus, rng),
        h('div', { class: 'kctl' }, h('span', { class: 'kdef', text: `Default ${fmt(d.default)} ${d.unit} (range ${fmt(d.min)}–${fmt(d.max)})` }), chg, back));
      const show = () => {
        const v = d.id in vals ? vals[d.id] : d.default, over = v !== d.default;
        num.value = fmt(v); rng.value = String(v);
        row.querySelector('.kval').textContent = fmt(v);
        row.classList.toggle('over', over);
        chg.textContent = over ? `changed from ${fmt(d.default)}` : '';
        back.hidden = !over;
      };
      const set = v => {
        if (!isFinite(v)) { show(); return; }
        v = snap(d, v);
        if (v === d.default) delete vals[d.id]; else vals[d.id] = v;
        show(); summary(); if (o.onChange) o.onChange(Object.assign({}, vals));
      };
      minus.onclick = () => set((d.id in vals ? vals[d.id] : d.default) - d.step);
      plus.onclick = () => set((d.id in vals ? vals[d.id] : d.default) + d.step);
      num.onchange = () => set(parseFloat(num.value));
      rng.oninput = () => { const v = snap(d, parseFloat(rng.value)); num.value = fmt(v); row.querySelector('.kval').textContent = fmt(v); };
      rng.onchange = () => set(parseFloat(rng.value));
      back.onclick = () => set(d.default);
      row._show = show;
      return row;
    });
    const summary = () => {
      const n = Object.keys(vals).length;
      count.textContent = n ? `${n} changed` : 'all at default';
      resetAll.hidden = !n;
    };
    box.reset = () => { for (const k of Object.keys(vals)) delete vals[k]; rows.forEach(r => r._show()); summary(); if (o.onChange) o.onChange({}); };
    resetAll.onclick = () => box.reset();
    rows.forEach(r => { r._show(); box.append(r); });
    summary();
    return box;
  }
  window.KnobUI = { panel };
})();
