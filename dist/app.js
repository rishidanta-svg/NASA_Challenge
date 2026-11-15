'use strict';
// Littoral: every number shown comes from window.LITTORAL_DATA (dist/data.js),
// which src/export_app_data.py generates from the validation pipeline's outputs.
const D = window.LITTORAL_DATA;
const $ = s => document.querySelector(s), $$ = s => [...document.querySelectorAll(s)];
const esc = s => String(s).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));

if (!D) {
  document.body.innerHTML = '<p style="padding:40px">dist/data.js is missing. Run <code>python run_validation.py</code> (or <code>python src/export_app_data.py</code>) first.</p>';
  throw new Error('no data');
}

const SENSORS = [  // [product key, short label, colour, default on]
  ['S2_NDWI', 'Sentinel-2 NDWI', '#38bdf8', true],
  ['S1_VV', 'Sentinel-1 VV', '#f59e0b', true],
  ['NISAR_HH', 'NISAR HH', '#c084fc', true],
  ['S2_MNDWI', 'Sentinel-2 MNDWI', '#7dd3fc', false],
  ['S1_VH', 'Sentinel-1 VH', '#fcd34d', false],
  ['NISAR_HV', 'NISAR HV', '#e9d5ff', false],
].filter(s => D.products[s[0]] && D.profiles[0].sensors[s[0]]);
const LIDAR = [['B2_dunetoe', 'Dune toe', '#f8fafc', true], ['B1_wetdry', 'Wet/dry edge', '#94a3b8', true],
  ['B3_contour', `${D.contour_z.toFixed(1)} m contour`, '#64748b', false]];
const DATE_LABEL = {'2026-06': 'June', '2026-09': 'September', '2026-10': 'October'};
// start on the row nearest y = 950 m where the lidar dune toe exists on both June and October
const startRow = (() => { let best = -1; D.profiles.forEach((p, i) => {
  if (p.lidar['2026-06'].B2_dunetoe !== null && p.lidar['2026-10'].B2_dunetoe !== null
      && (best < 0 || Math.abs(p.y - 950) < Math.abs(D.profiles[best].y - 950))) best = i; }); return Math.max(best, 0); })();
const state = {date: '2026-06', row: startRow, page: 'explore',
  on: Object.fromEntries([...SENSORS, ...LIDAR].map(s => [s[0], s[3]])), sep: false};

// ---------------------------------------------------------------- header text
$('#yRange').textContent = `${D.site.y_range[0]}–${D.site.y_range[1]}`;
$('#latlon').textContent = `${D.site.lat[0].toFixed(3)}° N · ${Math.abs(D.site.lon[0]).toFixed(3)}° W`;
$('#headline').textContent = `Lidar measured a median beach lowering of ${D.lowering.median_dz_m.toFixed(3)} m between June and October `
  + `(${D.lowering.area_m2.toLocaleString()} m² lowered by more than ${D.lowering.threshold_m} m). `
  + `Satellites are compared with it below: each one marks a different feature.`;
$('#thr').textContent = D.lowering.threshold_m;
$('#footerState').textContent = `Data generated ${D.generated_utc} UTC from the validation pipeline`;
$('#frame').textContent = D.site.frame + '.';

// ---------------------------------------------------------------- navigation
function go(page) {
  if (!['explore', 'sensors', 'events', 'evidence'].includes(page)) page = 'explore';
  state.page = page;
  $$('.workspace').forEach(el => el.classList.toggle('active', el.id === page));
  $$('nav button').forEach(b => b.classList.toggle('active', b.dataset.page === page));
  history.replaceState(null, '', '#' + page);
  redraw();
}
$$('nav button').forEach(b => b.onclick = () => go(b.dataset.page));
window.addEventListener('hashchange', () => go(location.hash.slice(1)));

// ---------------------------------------------------------------- controls
function toggles(el, list) {
  el.innerHTML = list.map(([k, label, color]) => `<label class="switch-row"><span><i class="key" style="background:${color}"></i>${esc(label)}`
    + `${D.products[k] && D.products[k].experimental ? ' <em>(experimental)</em>' : ''}</span>`
    + `<input type="checkbox" data-toggle="${k}" ${state.on[k] ? 'checked' : ''}></label>`).join('');
}
toggles($('#sensorToggles'), SENSORS);
toggles($('#lidarToggles'), LIDAR);
$$('[data-toggle]').forEach(b => b.onchange = () => { state.on[b.dataset.toggle] = b.checked; redraw(); });
$$('[data-date]').forEach(b => b.onclick = () => {
  state.date = b.dataset.date;
  $$('[data-date]').forEach(x => x.classList.toggle('active', x === b));
  redraw();
});
$('#showSep').onchange = e => { state.sep = e.target.checked; redraw(); };

// ---------------------------------------------------------------- colour scale for elevation change
const G = D.grid, vals = G.dz_cm.filter(v => v !== null).map(v => v / 100).sort((a, b) => a - b);
const q = p => vals[Math.min(vals.length - 1, Math.floor(p * vals.length))];
const LO = q(0.02), HI = Math.max(q(0.98), D.lowering.threshold_m * 2);
function dzColor(v) {
  if (Math.abs(v) <= D.lowering.threshold_m) return [120, 128, 136];
  if (v < 0) { const t = Math.min(1, v / LO); return [Math.round(150 + 105 * t), Math.round(120 - 60 * t), Math.round(90 - 60 * t)]; }
  const t = Math.min(1, v / HI); return [Math.round(90 - 50 * t), Math.round(140 + 40 * t), Math.round(170 + 80 * t)];
}
$('#legendBar').style.background = `linear-gradient(90deg, rgb(${dzColor(LO)}), rgb(${dzColor(-D.lowering.threshold_m * 1.01)}), rgb(120,128,136), rgb(${dzColor(D.lowering.threshold_m * 1.01)}), rgb(${dzColor(HI)}))`;
$('#legendValues').innerHTML = `<span>${LO.toFixed(2)}</span><span>0</span><span>+${HI.toFixed(2)}</span>`;

// ---------------------------------------------------------------- map (FRF frame: y alongshore → right, x cross-shore ↓ toward ocean)
const canvas = $('#map'), ctx = canvas.getContext('2d');
const XMIN = 40, XMAX = 130, YMIN = G.y0, YMAX = G.y0 + G.dy * G.ny;
let M = null;
function drawMap() {
  if (state.page !== 'explore') return;
  const r = $('#mapArea').getBoundingClientRect();
  if (!r.width) return;
  const dpr = Math.min(devicePixelRatio || 1, 2), W = r.width, H = r.height, pad = {l: 50, r: 16, t: 26, b: 36};
  canvas.width = W * dpr; canvas.height = H * dpr; canvas.style.width = W + 'px'; canvas.style.height = H + 'px';
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.fillStyle = '#0f1c26'; ctx.fillRect(0, 0, W, H);
  const sy = (W - pad.l - pad.r) / (YMAX - YMIN), sx = (H - pad.t - pad.b) / (XMAX - XMIN);
  M = {px: y => pad.l + (y - YMIN) * sy, py: x => pad.t + (x - XMIN) * sx, pad, W, H, sy, sx};
  // elevation-change cells
  for (let j = 0; j < G.ny; j++) for (let i = 0; i < G.nx; i++) {
    const v = G.dz_cm[j * G.nx + i]; if (v === null) continue;
    const x = G.x0 + i * G.dx, y = G.y0 + j * G.dy; if (x < XMIN || x > XMAX) continue;
    ctx.fillStyle = `rgb(${dzColor(v / 100)})`;
    ctx.fillRect(M.px(y - G.dy / 2), M.py(x - G.dx / 2), G.dy * sy + 0.6, G.dx * sx + 0.6);
  }
  // edge lines along the beach for the chosen date
  const line = (key, color, dash, getter) => {
    ctx.beginPath(); let open = false;
    D.profiles.forEach(p => { const x = getter(p); if (x === null || x === undefined) { open = false; return; }
      if (!open) { ctx.moveTo(M.px(p.y), M.py(x)); open = true; } else ctx.lineTo(M.px(p.y), M.py(x)); });
    ctx.strokeStyle = color; ctx.lineWidth = 2.2; ctx.setLineDash(dash); ctx.stroke(); ctx.setLineDash([]);
  };
  ctx.save(); ctx.beginPath(); ctx.rect(pad.l, pad.t, W - pad.l - pad.r, H - pad.t - pad.b); ctx.clip();
  LIDAR.forEach(([k, , c]) => state.on[k] && line(k, c, [6, 4], p => p.lidar[state.date][k]));
  SENSORS.forEach(([k, , c]) => state.on[k] && line(k, c, [], p => p.sensors[k][state.date]));
  ctx.restore();
  // selected row
  const sel = D.profiles[state.row];
  ctx.strokeStyle = '#ffffff'; ctx.lineWidth = 1.5; ctx.setLineDash([2, 3]);
  ctx.beginPath(); ctx.moveTo(M.px(sel.y), pad.t); ctx.lineTo(M.px(sel.y), H - pad.b); ctx.stroke(); ctx.setLineDash([]);
  // axes
  ctx.fillStyle = '#9fb3c3'; ctx.font = '11px Inter, system-ui, sans-serif'; ctx.textAlign = 'center';
  for (let y = 700; y <= 1200; y += 100) ctx.fillText(y, M.px(y), H - pad.b + 16);
  ctx.fillText('alongshore y (m) →', W / 2, H - 4);
  ctx.textAlign = 'right';
  for (let x = XMIN; x <= XMAX; x += 30) ctx.fillText(x, pad.l - 6, M.py(x) + 4);
  ctx.save(); ctx.translate(12, H / 2); ctx.rotate(-Math.PI / 2); ctx.textAlign = 'center'; ctx.fillText('x (m) → ocean', 0, 0); ctx.restore();
  ctx.textAlign = 'left';
  $('#mapCredit').textContent = `Lines: ${DATE_LABEL[state.date]} edges. USACE FRF tower lidar (QC flag 1), 2 m cells. `
    + `Ocean at the bottom; ` + (Math.abs(sx / sy - 1) < 0.05 ? 'equal scale in both directions.'
      : `cross-shore distances drawn at ${(sx / sy).toFixed(1)}× the alongshore scale.`);
}
canvas.onclick = e => {
  if (!M) return;
  const r = canvas.getBoundingClientRect(), y = YMIN + (e.clientX - r.left - M.pad.l) / M.sy;
  let best = 0; D.profiles.forEach((p, i) => { if (Math.abs(p.y - y) < Math.abs(D.profiles[best].y - y)) best = i; });
  state.row = best; redraw();
};

// ---------------------------------------------------------------- cross-section
function series(p, d) {  // [[x,z],...] with null breaks across gaps
  return p.z[d].map((z, i) => [p.x0 + i * p.dx, z]);
}
function pathOf(pts, sx, sy) {
  let s = '', open = false;
  pts.forEach(([x, z]) => { if (z === null) { open = false; return; } s += (open ? 'L' : 'M') + sx(x).toFixed(1) + ',' + sy(z).toFixed(1); open = true; });
  return s;
}
function drawProfile() {
  if (state.page !== 'explore') return;
  const el = $('#profile'), p = D.profiles[state.row];
  const w = Math.max(el.clientWidth, 320), h = Math.max(el.clientHeight, 160), L = 44, R = 14, T = 8, B = 24;
  const J = series(p, '2026-06'), O = series(p, '2026-10'), S = series(p, '2026-09');
  const zs = [...J, ...O, ...(state.sep ? S : [])].map(v => v[1]).filter(v => v !== null);
  const zMin = Math.floor(Math.min(...zs, 0)), zMax = Math.ceil(Math.max(...zs));
  const sx = x => L + (x - XMIN) / (XMAX - XMIN) * (w - L - R), sy = z => T + (zMax - z) / (zMax - zMin) * (h - T - B);
  let s = '';
  for (let z = zMin; z <= zMax; z += Math.max(1, Math.round((zMax - zMin) / 4))) s += `<line x1="${L}" x2="${w - R}" y1="${sy(z)}" y2="${sy(z)}" stroke="#263746" stroke-dasharray="2 4"/><text x="${L - 6}" y="${sy(z) + 4}" text-anchor="end" fill="#8fa3b5" font-size="10">${z}</text>`;
  for (let x = XMIN; x <= XMAX; x += 10) s += `<text x="${sx(x)}" y="${h - 6}" text-anchor="middle" fill="#8fa3b5" font-size="10">${x}</text>`;
  // lowered / raised area between June and October (only where both exist)
  J.forEach(([x, zj], i) => { const zo = O[i][1]; if (zj === null || zo === null || i + 1 >= J.length) return;
    const zj2 = J[i + 1][1], zo2 = O[i + 1][1]; if (zj2 === null || zo2 === null) return;
    const fill = zo < zj ? 'rgba(239,68,68,.28)' : 'rgba(56,189,248,.22)';
    s += `<path d="M${sx(x)},${sy(zj)}L${sx(x + p.dx)},${sy(zj2)}L${sx(x + p.dx)},${sy(zo2)}L${sx(x)},${sy(zo)}Z" fill="${fill}"/>`; });
  // edges: June dotted, October solid
  const vline = (x, color, dash, text) => { if (x === null || x === undefined || x < XMIN || x > XMAX) return;
    s += `<line x1="${sx(x)}" x2="${sx(x)}" y1="${T}" y2="${h - B}" stroke="${color}" stroke-width="2" ${dash ? 'stroke-dasharray="3 3"' : ''}><title>${esc(text)}: x = ${x} m</title></line>`; };
  $('#sensorKey').innerHTML = SENSORS.filter(([k]) => state.on[k]).map(([, label, c]) => `<span class="sk"><i style="background:${c}"></i>${esc(label)}</span>`).join('');
  SENSORS.forEach(([k, label, c]) => { if (!state.on[k]) return; vline(p.sensors[k]['2026-06'], c, true, label + ' Jun'); vline(p.sensors[k]['2026-10'], c, false, label + ' Oct'); });
  if (state.sep) SENSORS.forEach(([k, label, c]) => state.on[k] && vline(p.sensors[k]['2026-09'], c, true, label + ' Sep'));
  s += `<path d="${pathOf(J, sx, sy)}" fill="none" stroke="#60a5fa" stroke-width="2.4"/>`;
  s += `<path d="${pathOf(O, sx, sy)}" fill="none" stroke="#f87171" stroke-width="2.4"/>`;
  if (state.sep) s += `<path d="${pathOf(S, sx, sy)}" fill="none" stroke="#9ca3af" stroke-width="1.6" stroke-dasharray="4 3"/>`;
  // lidar boundary markers
  const zAt = (pts, x) => { let b = null; pts.forEach(([px, pz]) => { if (pz !== null && (b === null || Math.abs(px - x) < Math.abs(b[0] - x))) b = [px, pz]; }); return b; };
  LIDAR.forEach(([k, label, c]) => { if (!state.on[k]) return;
    [['2026-06', J], ['2026-10', O]].forEach(([d, pts]) => { const x = p.lidar[d][k]; if (x === null) return; const b = zAt(pts, x); if (!b) return;
      s += `<circle cx="${sx(x)}" cy="${sy(b[1])}" r="5" fill="${c}" stroke="#0b1118" stroke-width="1.5"><title>${esc(label)} (${DATE_LABEL[d]}): x = ${x} m</title></circle>`; }); });
  s += `<line class="cursor" x1="0" x2="0" y1="${T}" y2="${h - B}" stroke="#e2e8f0" opacity="0"/>`;
  el.innerHTML = `<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="Lidar cross-section at y = ${p.y} m with sensor edges">${s}</svg>`;
  el.onpointermove = e => { const r = el.getBoundingClientRect(), x = XMIN + ((e.clientX - r.left) / r.width * w - L) / (w - L - R) * (XMAX - XMIN);
    const i = Math.round((x - p.x0) / p.dx); if (i < 0 || i >= J.length) return;
    const c = el.querySelector('.cursor'); c.setAttribute('x1', sx(x)); c.setAttribute('x2', sx(x)); c.setAttribute('opacity', '.5');
    const f = v => v === null ? 'no data' : v.toFixed(2) + ' m';
    const dz = J[i][1] !== null && O[i][1] !== null ? ` · change ${(O[i][1] - J[i][1]).toFixed(2)} m` : '';
    $('#chartReadout').textContent = `x = ${J[i][0]} m · June ${f(J[i][1])} · October ${f(O[i][1])}${dz}`; };
  $('#profileTitle').innerHTML = `Row y = ${p.y} m <span>· 10 m wide, median of 10 lidar lines</span>`;
}

function drawInspector() {
  const p = D.profiles[state.row];
  $('#inspectorTitle').textContent = `y = ${p.y} m`;
  $('#mapTitle').textContent = `Selected row y = ${p.y} m`;
  const f = v => v === null || v === undefined ? '—' : v.toFixed(1);
  const sh = (a, b) => a === null || b === null || a === undefined || b === undefined ? '—' : ((b - a > 0 ? '+' : '') + (b - a).toFixed(1));
  let rows = '<tr><th></th><th>Jun</th><th>Oct</th><th>shift</th></tr>';
  LIDAR.forEach(([k, label]) => { const j = p.lidar['2026-06'][k], o = p.lidar['2026-10'][k]; rows += `<tr><td>Lidar ${esc(label.toLowerCase())}</td><td>${f(j)}</td><td>${f(o)}</td><td>${sh(j, o)}</td></tr>`; });
  SENSORS.forEach(([k, label]) => { const j = p.sensors[k]['2026-06'], o = p.sensors[k]['2026-10']; rows += `<tr><td>${esc(label)}</td><td>${f(j)}</td><td>${f(o)}</td><td>${sh(j, o)}</td></tr>`; });
  $('#rowTable').innerHTML = rows;
}

// ---------------------------------------------------------------- sensors & trust
const tagClass = t => t.startsWith('SUPPORTED') ? 'tag-sup' : t.startsWith('PLAUSIBLE') ? 'tag-pla' : t.startsWith('NOT DEM') ? 'tag-not' : t === 'EXPERIMENTAL' ? 'tag-exp' : 'tag-note';
$('#sensorTable').innerHTML = '<thead><tr><th>Sensor</th><th>Compared with</th><th>Rows</th><th>Bias (m)</th><th>RMSE (m) [95%]</th><th>RMSE by date (Jun / Sep / Oct)</th><th>Within 1 pixel</th><th>Evidence</th></tr></thead><tbody>'
  + D.table.map(r => `<tr><td><b>${esc(r.label)}</b>${r.experimental ? '<small>experimental, uses lidar beach slope</small>' : ''}</td><td>${esc(r.compared_with)}</td><td>${r.N}</td>`
    + `<td>${r.bias_m > 0 ? '+' : ''}${r.bias_m.toFixed(1)}</td><td>${r.rmse_m.toFixed(1)} [${r.rmse_lo.toFixed(1)}–${r.rmse_hi.toFixed(1)}]</td>`
    + `<td>${D.dates.map(d => r.rmse_by_date[d] === null ? '—' : r.rmse_by_date[d].toFixed(1)).join(' / ')}</td><td>${r.pct_within_pixel}% of ${r.pixel_m} m</td>`
    + `<td><span class="tag ${tagClass(r.tag)}">${esc(r.tag)}</span>${r.detail ? `<small>${esc(r.detail)}</small>` : ''}</td></tr>`).join('') + '</tbody>';
const cap = s => s.charAt(0).toUpperCase() + s.slice(1);
const claimCard = c => `<article class="claim card"><span class="tag ${tagClass(c.tag)}">${esc(c.tag)}</span><h3>${esc(cap(c.headline))}</h3><p>${esc(c.detail)}</p></article>`;
$('#claims').innerHTML = D.claims.filter(c => c.section !== 'independent').map(claimCard).join('');
$('#strictClaims').innerHTML = D.claims.filter(c => c.section === 'independent').map(claimCard).join('');
$('#strictTable').innerHTML = D.strict.length
  ? '<thead><tr><th>Group</th><th>Method</th><th>Rows</th><th>RMSE (m) [95%]</th><th>RMSE by date (Jun / Sep / Oct)</th></tr></thead><tbody>'
    + D.strict.map(r => `<tr${r.is_baseline ? ' class="baseline"' : ''}><td>${esc(r.group)}</td><td><b>${esc(r.method)}</b>${r.is_baseline ? '<small>simple baseline</small>' : ''}</td><td>${r.N}</td>`
      + `<td>${r.rmse_m.toFixed(1)} [${r.rmse_lo.toFixed(1)}–${r.rmse_hi.toFixed(1)}]</td>`
      + `<td>${D.dates.map(d => r.rmse_by_date[d] === null ? '—' : r.rmse_by_date[d].toFixed(1)).join(' / ')}</td></tr>`).join('') + '</tbody>'
  : '<tbody><tr><td>Independent test not run yet.</td></tr></tbody>';
$('#rules').innerHTML = D.rules.map(r => `<li>${esc(r)}</li>`).join('');

// ---------------------------------------------------------------- timeline & sources
$('#timeline').innerHTML = '<thead><tr><th>UTC</th><th>Sensor</th><th>Campaign</th><th>Hours from lidar</th><th>Water level (m)</th><th>Product</th><th>Note</th></tr></thead><tbody>'
  + D.acquisitions.map(a => `<tr><td class="mono">${esc(a.utc)}</td><td><b>${esc(a.sensor)}</b></td><td>${DATE_LABEL[a.date_key]}</td>`
    + `<td>${a.hours_from_lidar > 0 ? '+' : ''}${a.hours_from_lidar}</td><td>${a.water_level_navd88_m ?? 'not fetched'}</td>`
    + `<td class="mono small">${esc(a.product_id)}</td><td>${esc(a.note)}</td></tr>`).join('') + '</tbody>';
$('#sources').innerHTML = $('#timeline').innerHTML;
$('#caveats').innerHTML = D.caveats.map(c => `<li>${esc(c)}</li>`).join('');

// ---------------------------------------------------------------- misc
function redraw() { drawMap(); drawProfile(); drawInspector(); }
$('#help').onclick = () => $('#helpDialog').showModal();
$('#closeHelp').onclick = () => $('#helpDialog').close();
new ResizeObserver(() => { drawMap(); drawProfile(); }).observe($('.central'));
go(location.hash.slice(1) || 'explore');
