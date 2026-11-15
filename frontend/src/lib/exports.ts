import type { CoastalEvidence, NisarEvidence, TransectDetail } from '../api/schemas';

export function saveDownload(name: string, content: string, type: string): void {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const link = document.createElement('a');
  link.href = url;
  link.download = name;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

const esc = (v: unknown) => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]!));
const metres = (v: number | null | undefined, digits = 2) => v == null ? 'Not available' : `${v.toFixed(digits)} m`;
const names: Record<string, string> = {zero_change:'Assume no change',training_mean:'Training mean',A:'NISAR only',B:'Sentinel-1 + Sentinel-2',C:'Sentinel-1 + Sentinel-2 + NISAR'};

/** A self-contained, printable study brief. Values come from validated API products. */
export function studyBrief(c: CoastalEvidence, n: NisarEvidence | null, generatedAt = new Date().toISOString()): string {
  const check = c.validation.targets.fixed_mhw_contour?.raw_vs_tide;
  const rows = Object.entries(check?.methods ?? {}).map(([method,m]) => `<tr><td>${esc(method)}</td><td>${m.n}</td><td>${metres(m.rmse_m)}</td></tr>`).join('');
  const models = Object.entries(n?.terrain_ablation?.metrics ?? {}).map(([method,m]) => `<tr><td>${esc(names[method] ?? method)}</td><td>${m.n}</td><td>${metres(m.rmse_m,4)}</td></tr>`).join('');
  const sources = c.terrain?.acquisitions?.map(a => `<tr><td>${esc(a.epoch)}</td><td>${esc(a.acquired_at)}</td><td>${esc(a.source_id)}</td></tr>`).join('') ?? '';
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Poltergeist · Duck coastal study brief</title><style>body{font:15px/1.65 system-ui,sans-serif;color:#222;max-width:850px;margin:48px auto;padding:0 24px}header{border-bottom:2px solid #222;padding-bottom:20px}h1{font-size:32px;letter-spacing:-1px;margin:12px 0}h2{font-size:20px;margin-top:32px}table{border-collapse:collapse;width:100%;font-size:13px}th,td{padding:10px;text-align:left;border-bottom:1px solid #ddd;overflow-wrap:anywhere}small{color:#666}.result{font-size:38px;font-weight:600;margin:20px 0 0}.note{border-left:3px solid #aaa;padding:12px 16px;background:#f5f5f3}button{padding:10px 18px;background:white;border:1px solid #aaa;cursor:pointer}@media print{button{display:none}body{margin:0}h2,table{break-inside:avoid}}</style></head><body><header><small>POLTERGEIST / COASTAL OBSERVATORY</small><h1>Duck coastline · study brief</h1><p>North Carolina, United States · June–October 2026 · approximately 500 m of coastline</p><small>Generated ${esc(generatedAt)} · Processing ${esc(c.processing_version)}</small></header><p class="result">${metres(c.terrain?.mean_m)}</p><p>Mean October-minus-June ground-level change over ${esc(c.terrain?.native_paired_cells?.toLocaleString() ?? 'unavailable')} paired valid native 1 m LiDAR cells. Negative values mean lower ground; positive values mean higher ground. This is an observed surface-height difference, not a satellite forecast or an uncertainty-qualified erosion classification.</p><h2>What the tool does</h2><p>Compare measured beach surfaces, inspect cross-shore profiles, and examine optical and radar observations on a shared map. Earth observation instruments include NASA–ISRO NISAR L-band radar, Copernicus Sentinel-1 C-band radar, Sentinel-2 multispectral optical imaging and USACE ground-based LiDAR. NOAA tide gauges and USACE environmental instruments provide context.</p><h2>Optical waterline comparison</h2><p>${esc(c.validation.scope)}. The table compares optical boundaries with ${check?.n ?? 'unavailable'} October LiDAR mean-high-water contour positions. RMSE is horizontal position error; lower values are better.</p><table><thead><tr><th>Method</th><th>Positions</th><th>Horizontal RMSE</th></tr></thead><tbody>${rows}</tbody></table><p>Water levels are translated along the beach slope to ${metres(c.target?.value,3)} ${esc(c.target?.vertical_datum ?? 'Not available')}, the NOAA mean-high-water reference. This local October result is not a general accuracy claim; correction worsens the June wet/dry-proxy comparison.</p><h2>NISAR terrain experiment</h2>${models ? `<p>One June–October interval, ${n?.terrain_ablation?.n ?? 'unavailable'} valid 10 m cells. Buffered held-out coastal strips test local spatial transfer. RMSE here is vertical height-change error and is not comparable to the horizontal errors above.</p><table><thead><tr><th>Model</th><th>Cells</th><th>Vertical RMSE</th></tr></thead><tbody>${models}</tbody></table>` : '<p>NISAR experiment results are not available in this export.</p>'}<p class="note">${n?.terrain_ablation?.ablation ? `Adding NISAR ${n.terrain_ablation.ablation.C_minus_B_rmse_m > 0 ? 'increased' : 'reduced'} error by ${metres(Math.abs(n.terrain_ablation.ablation.C_minus_B_rmse_m),5)} in this local test. ` : ''}Operational deployment, forecasts and calibrated prediction intervals remain withheld. The June Sentinel-1 repeat pass follows NISAR by about 12 days; timing and sensor differences are confounded.</p><h2>Survey provenance</h2><table><thead><tr><th>Survey</th><th>Acquired (UTC)</th><th>Source</th></tr></thead><tbody>${sources}</tbody></table><p>Ground heights: ${esc(c.terrain?.datum ?? 'Not available')}. Horizontal analysis: UTM zone 18N (EPSG:32618). FRF coordinates are local survey coordinates.</p><h2>Use and limitations</h2><p>Use these observations to identify locations for closer inspection, compare sensor behaviour, and prepare evidence for follow-up field work. This study covers one coastline and one seasonal interval. Background satellite imagery is geographic context and is not matched to survey dates. Radar brightness changes alone do not establish erosion. Spatially adjacent cells are not independent coastal sites. Full measurement and alignment uncertainty is not quantified.</p><p><a href="https://tidesandcurrents.noaa.gov/benchmarks/8651370.html">NOAA Duck station datum reference</a> · <a href="https://github.com/rishidanta-svg/NASA_Challenge">Project code and reproduction</a></p><button onclick="window.print()">Print / save as PDF</button></body></html>`;
}

/** Export the union of measured positions; preserve gaps as empty cells. */
export function profileCsv(t: TransectDetail): string {
  const first = t.profiles[0], second = t.profiles[1];
  const june = new Map(first?.points.map(p => [p.x_m,p.z_m]) ?? []);
  const october = new Map(second?.points.map(p => [p.x_m,p.z_m]) ?? []);
  const change = new Map(t.measured_change?.change_profile.map(p => [p.x_m,p.dz_m]) ?? []);
  const positions = [...new Set([...june.keys(),...october.keys()])].sort((a,b) => a-b);
  const cell = (v: unknown) => `"${String(v ?? '').replace(/"/g,'""')}"`;
  const header = ['transect_id','frf_y_m','distance_from_profile_start_m','cross_shore_frf_m','june_height_m','october_height_m','october_minus_june_m','june_acquired_utc','october_acquired_utc','vertical_datum'];
  const rows = positions.map(x => [t.properties.id,t.properties.frf_y_m,x,t.properties.x_origin_frf_m == null ? null : x+t.properties.x_origin_frf_m,june.get(x),october.get(x),change.get(x),first?.acquired_at,second?.acquired_at,first?.vertical_datum].map(cell).join(','));
  return [header.join(','),...rows].join('\r\n');
}
