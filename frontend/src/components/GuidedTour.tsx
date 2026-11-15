import { useEffect, useState } from 'react';
import { getAnalysis, getCoastalEvidence, getNisarEvidence, getTransect, type Sourced } from '../api/client';
import type { Analysis, CoastalEvidence, NisarEvidence, TransectDetail } from '../api/schemas';
import { slotById } from '../config/slots';
import { resolveSlot } from '../lib/layers';
import { flyToStudyArea } from '../map/registry';
import { useApp } from '../state/store';
import { Legend } from './Legend';

const STEP_META = [
  {
    id: 'coastline',
    short: 'Coastline',
    title: 'Meet the Coastline',
    question: 'What happened at Duck, North Carolina?',
  },
  {
    id: 'nisar',
    short: 'NISAR SAR',
    title: 'What Does NISAR See?',
    question: 'Can radar detect changes invisible to ordinary photographs?',
  },
  {
    id: 'compare',
    short: 'Compare',
    title: 'Compare the Satellites',
    question: 'Why do two satellites disagree?',
  },
  {
    id: 'lidar',
    short: 'Ground Truth',
    title: 'Reveal the Ground Truth',
    question: 'What actually happened to the beach?',
  },
  {
    id: 'breakthrough',
    short: 'Breakthrough',
    title: 'The Breakthrough: Correcting the Waterline',
    question: 'What if the waterline moves because the tide changes?',
  },
] as const;

const TOTAL_STEPS = STEP_META.length;
const MHW_NAVD88_M = 0.359;

interface UnlabeledRange {
  unit: string;
  n: number;
  range: [number, number];
}

function fmtDbRange(r: UnlabeledRange | undefined): string {
  if (!r) return 'Not available';
  return `${r.range[0].toFixed(2)} to ${r.range[1].toFixed(2)} ${r.unit}`;
}

/** Linearly interpolate cross-shore FRF coordinate where October LiDAR profile crosses MHW (0.359 m NAVD88). */
function findOctoberMhwFrfX(points: { x_m: number; z_m: number }[] | undefined, xOriginFrf: number): number | null {
  if (!points || points.length < 2) return null;
  for (let i = 0; i < points.length - 1; i++) {
    const a = points[i]!;
    const b = points[i + 1]!;
    const da = a.z_m - MHW_NAVD88_M;
    const db = b.z_m - MHW_NAVD88_M;
    if ((da >= 0 && db <= 0) || (da <= 0 && db >= 0)) {
      const span = a.z_m - b.z_m;
      const frac = Math.abs(span) > 1e-6 ? (a.z_m - MHW_NAVD88_M) / span : 0;
      const xM = a.x_m + frac * (b.x_m - a.x_m);
      return xOriginFrf + xM;
    }
  }
  return null;
}

/** Exclusively activate one map overlay slot, or pass `'none'` to clear raster/vector overlays. */
function activateOnlySlot(slotId: string) {
  const { slots, setSlot } = useApp.getState();
  Object.keys(slots).forEach((key) => setSlot(key, { visible: key === slotId }));
  if (slotId !== 'none') {
    setSlot(slotId, { visible: true });
  }
}

export interface GuidedTourProps {
  onExplore: () => void;
  onNavigatePanel: (panel: 'overview' | 'layers' | 'compare' | 'findings' | 'about') => void;
}

export function GuidedTour({ onExplore, onNavigatePanel }: GuidedTourProps) {
  const {
    date,
    compareDate,
    swipe,
    mode,
    slots,
    layers,
    transects,
    acquisitions,
    studyArea,
    selectedTransectId,
    bottomOpen,
    set,
  } = useApp();

  const [step, setStep] = useState(0);
  const [coastal, setCoastal] = useState<Sourced<CoastalEvidence> | null>(null);
  const [nisar, setNisar] = useState<Sourced<NisarEvidence> | null>(null);
  const [analysis, setAnalysis] = useState<Sourced<Analysis> | null>(null);
  const [transectDetail, setTransectDetail] = useState<Sourced<TransectDetail> | null>(null);

  useEffect(() => {
    let active = true;
    void getCoastalEvidence().then((res) => {
      if (active) setCoastal(res);
    });
    void getNisarEvidence().then((res) => {
      if (active) setNisar(res);
    });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    const tid = selectedTransectId ?? transects?.data?.[4]?.properties.id ?? transects?.data?.[0]?.properties.id ?? null;
    if (!tid) return;
    if (!selectedTransectId) set({ selectedTransectId: tid });
    let active = true;
    void getAnalysis(tid).then((res) => {
      if (active) setAnalysis(res);
    });
    void getTransect(tid).then((res) => {
      if (active) setTransectDetail(res);
    });
    return () => {
      active = false;
    };
  }, [selectedTransectId, transects, set]);

  // Synchronize the live map, overlays, comparison swipe, and profile viewer with the active tour step.
  useEffect(() => {
    flyToStudyArea();
    if (step === 0) {
      activateOnlySlot('none');
      set({ compare: false, showStudyArea: true, showTransects: true, bottomOpen: false });
      return;
    }
    if (step === 1) {
      activateOnlySlot('nisar-hh');
      set({ compare: false, showStudyArea: true, bottomOpen: false });
      return;
    }
    if (step === 2) {
      activateOnlySlot('radar-disagreement');
      set({
        compare: true,
        date: '2026-06-18',
        compareDate: '2026-10-16',
        swipe: 0.5,
        showStudyArea: true,
        bottomOpen: false,
      });
      return;
    }
    if (step === 3) {
      activateOnlySlot('lidar-dz');
      const currentTid = useApp.getState().selectedTransectId;
      const fallbackTid = useApp.getState().transects?.data?.[4]?.properties.id ?? useApp.getState().transects?.data?.[0]?.properties.id ?? null;
      set({
        compare: false,
        showStudyArea: true,
        showTransects: true,
        bottomOpen: true,
        selectedTransectId: currentTid ?? fallbackTid,
      });
      return;
    }
    if (step === 4) {
      activateOnlySlot('physics-s2-tide');
      set({
        compare: false,
        date: '2026-10-16',
        showStudyArea: true,
        showTransects: true,
        bottomOpen: false,
      });
    }
  }, [step, set]);

  const activeSlotId = Object.keys(slots).find((id) => slots[id]?.visible) ?? 'none';
  const activeDesc = activeSlotId !== 'none' ? resolveSlot(layers?.data, activeSlotId, date) : null;
  const activeDef = activeSlotId !== 'none' ? slotById(activeSlotId) : undefined;

  const c = coastal?.data;
  const n = nisar?.data;
  const a = analysis?.data;
  const unlabeled = (n?.input_qa as { unlabeled_features?: Record<string, UnlabeledRange> } | undefined)?.unlabeled_features;

  const octWaterline = a?.coastal_observations?.waterlines.find((w) => w.date === '2026-10');
  const mhwCheck = c?.validation.targets.fixed_mhw_contour;
  const rawRmse = mhwCheck?.raw_vs_tide.methods?.raw?.rmse_m;
  const tideRmse = mhwCheck?.raw_vs_tide.methods?.tide?.rmse_m;
  const tideReduction =
    mhwCheck?.raw_vs_tide.rmse_reduction_percent?.tide ??
    (rawRmse != null && tideRmse != null && rawRmse > 0 ? ((rawRmse - tideRmse) / rawRmse) * 100 : undefined);
  const mhwN = mhwCheck?.raw_vs_tide.n;

  const td = transectDetail?.data;
  const octProfileMhwX = findOctoberMhwFrfX(td?.profiles?.[1]?.points, td?.properties.x_origin_frf_m ?? 0);
  const rawX = octWaterline?.ndwi.x_frf_m ?? null;
  const tideX = octWaterline?.tide.x_frf_m ?? null;
  const axisCandidates = [rawX, tideX, octProfileMhwX].filter((v): v is number => v != null);
  const axisMin = axisCandidates.length ? Math.min(...axisCandidates) - 4 : 0;
  const axisMax = axisCandidates.length ? Math.max(...axisCandidates) + 4 : 100;
  const toAxisPct = (val: number) => `${(((val - axisMin) / (axisMax - axisMin || 1)) * 100).toFixed(1)}%`;

  const currentMeta = STEP_META[step]!;

  function selectDate(nextDate: string) {
    set({
      date: nextDate,
      terrainSource: nextDate.startsWith('2026-06') ? 'lidar-dem-june' : 'lidar-dem-october',
    });
  }

  return (
    <section className="panel-content tour-panel" aria-label="Guided scientific tour">
      <div className="tour-progress-bar">
        <div className="tour-progress-top">
          <span className="eyebrow num">Step {step + 1} of {TOTAL_STEPS}</span>
          <button type="button" className="inline-link" onClick={onExplore}>
            Exit tour
          </button>
        </div>
        <div className="tour-step-pills" role="tablist" aria-label="Guided tour steps">
          {STEP_META.map((item, idx) => (
            <button
              key={item.id}
              type="button"
              role="tab"
              aria-selected={step === idx}
              className={`tour-step-pill ${step === idx ? 'active' : idx < step ? 'done' : ''}`}
              onClick={() => setStep(idx)}
              title={`Step ${idx + 1}: ${item.title}`}
            >
              <span className="num">{idx + 1}</span>
              <span>{item.short}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="tour-step-body">
        <span className="eyebrow">{currentMeta.title}</span>
        <h1 className="tour-question">{currentMeta.question}</h1>

        {step === 0 && (
          <div className="tour-section">
            <p className="intro">
              Between <strong>June and October 2026</strong>, POLTERGEIST tracks a 500 m coastal reach at the USACE Field Research Facility in Duck, North Carolina by combining four independent observing systems.
            </p>
            <div className="tour-callout">
              <strong>Highlighted on map:</strong> {studyArea?.data?.properties.name ?? 'Duck FRF Study Area'} (FRF y = 700–1190 m, UTM 18N 10 m analysis grid) and survey transects.
            </div>
            <div className="study-facts" style={{ marginBottom: 12 }}>
              <span>
                <strong className="num">500 m</strong>Reach (y 700–1190)
              </span>
              <span>
                <strong className="num">Jun & Oct</strong>2026 epochs
              </span>
              <span>
                <strong className="num">{acquisitions?.data?.length ?? 28}</strong>Cataloged products
              </span>
            </div>
            <div className="sensor-pills-grid">
              <div className="sensor-pill">
                <strong>NISAR L-band</strong>
                <small>HH / HV backscatter (dB)</small>
              </div>
              <div className="sensor-pill">
                <strong>Sentinel-1 C-band</strong>
                <small>VV / VH backscatter (dB)</small>
              </div>
              <div className="sensor-pill">
                <strong>Sentinel-2 Optical</strong>
                <small>NDWI / MNDWI & NOAA tide</small>
              </div>
              <div className="sensor-pill">
                <strong>USACE LiDAR</strong>
                <small>1 m elevation truth (NAVD88)</small>
              </div>
            </div>
            <div className="tour-inline-actions">
              <button type="button" className="tour-chip-btn" onClick={() => flyToStudyArea()}>
                Refocus Duck boundary on map
              </button>
              <button type="button" className="tour-chip-btn" onClick={() => set({ showTransects: !useApp.getState().showTransects })}>
                Toggle survey transects
              </button>
            </div>
          </div>
        )}

        {step === 1 && (
          <div className="tour-section">
            <p className="intro">
              NASA–ISRO <strong>NISAR</strong> measures L-band (~24 cm) radar backscatter in decibels (dB), penetrating clouds and darkness to sense surface moisture and geometry.
            </p>
            <div className="tour-controls-card">
              <span className="eyebrow">Live map controls · Epoch & NISAR layer</span>
              <div className="tour-chip-row" role="group" aria-label="NISAR observation epoch">
                <button
                  type="button"
                  aria-pressed={date === '2026-06-18'}
                  className={`tour-chip-btn ${date === '2026-06-18' ? 'active' : ''}`}
                  onClick={() => selectDate('2026-06-18')}
                >
                  June 2026 (2026-06-21 UTC)
                </button>
                <button
                  type="button"
                  aria-pressed={date === '2026-10-16'}
                  className={`tour-chip-btn ${date === '2026-10-16' ? 'active' : ''}`}
                  onClick={() => selectDate('2026-10-16')}
                >
                  October 2026 (2026-10-15 UTC)
                </button>
              </div>
              <div className="tour-chip-row" role="group" aria-label="NISAR active map layer">
                {(
                  [
                    ['nisar-hh', 'HH (dB)'],
                    ['nisar-hv', 'HV (dB)'],
                    ['nisar-hh-change', 'ΔHH change'],
                    ['nisar-hv-change', 'ΔHV change'],
                    ['nisar-hh-land-water-candidate', 'HH transition (Exploratory)'],
                  ] as const
                ).map(([slotId, label]) => (
                  <button
                    key={slotId}
                    type="button"
                    aria-pressed={activeSlotId === slotId}
                    className={`tour-chip-btn ${activeSlotId === slotId ? 'active' : ''}`}
                    onClick={() => activateOnlySlot(slotId)}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>

            {activeDesc && (
              <div className="tour-legend-card">
                <div className="panel-heading" style={{ marginBottom: 4 }}>
                  <strong style={{ fontSize: 12 }}>{activeDesc.title}</strong>
                  <span className={`badge badge-${activeSlotId === 'nisar-hh-land-water-candidate' ? 'exploratory' : 'observed'}`}>
                    {activeSlotId === 'nisar-hh-land-water-candidate' ? 'Exploratory' : 'Observed'}
                  </span>
                </div>
                <Legend colormap={activeDesc.colormap} units={activeDesc.units} inferred={activeDesc.inferred} meaning={activeDef?.meaning} />
              </div>
            )}

            <div className="tour-telemetry-mini">
              <div>
                <small>June HH / Oct HH range</small>
                <strong className="num">
                  {fmtDbRange(unlabeled?.june_hh_db)} / {fmtDbRange(unlabeled?.october_hh_db)}
                </strong>
              </div>
              <div>
                <small>ΔHH / ΔHV change (Oct − Jun)</small>
                <strong className="num">
                  {fmtDbRange(unlabeled?.delta_hh_db)} · {fmtDbRange(unlabeled?.delta_hv_db)}
                </strong>
              </div>
            </div>

            <div className="warning-banner" style={{ margin: '10px 0 0' }}>
              <strong>Caution:</strong> Radar-scattering change (dB) responds to moisture, waves, roughness, and incidence geometry — it is <strong>not automatically physical beach erosion</strong>.{' '}
              <button type="button" className="inline-link" onClick={() => onNavigatePanel('layers')}>
                Open all Layers →
              </button>
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="tour-section">
            <p className="intro">
              Drag the vertical divider directly on the map to swipe between <strong>June ({date})</strong> and <strong>October ({compareDate})</strong>, or switch sensors below.
            </p>
            <div className="tour-highlight-stat">
              <div className="panel-heading">
                <span className="eyebrow">Measured Sensor Divergence</span>
                <span className="badge badge-observed">Observed</span>
              </div>
              <p className="tour-stat-number num">
                {c?.radar_disagreement.opposite_strict_cells ?? 76} of {c?.radar_disagreement.strict_overlap_cells ?? 168} matched cells
              </p>
              <p className="slot-meta" style={{ margin: 0 }}>
                showed <strong>opposite signs</strong> of NISAR L-band ΔHH vs Sentinel-1 C-band ΔVV scattering change ({c?.radar_disagreement.opposite_radar_cells ?? 671} of {c?.radar_disagreement.matched_radar_cells ?? 1310} across wider radar overlap).
              </p>
            </div>

            <div className="tour-controls-card">
              <span className="eyebrow">Compare interface active · Overlay & Swipe ({Math.round(swipe * 100)}%)</span>
              <div className="tour-chip-row">
                {(
                  [
                    ['radar-disagreement', 'Opposite-sign cells'],
                    ['nisar-hh', 'NISAR HH (dB)'],
                    ['s1-vv', 'Sentinel-1 VV (dB)'],
                    ['s2-index', 'Sentinel-2 NDWI'],
                  ] as const
                ).map(([slotId, label]) => (
                  <button
                    key={slotId}
                    type="button"
                    aria-pressed={activeSlotId === slotId}
                    className={`tour-chip-btn ${activeSlotId === slotId ? 'active' : ''}`}
                    onClick={() => activateOnlySlot(slotId)}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <label className="tour-slider-label">
                <span className="num">Swipe divider ({date.slice(0, 7)} vs {compareDate.slice(0, 7)})</span>
                <input
                  type="range"
                  min={0.05}
                  max={0.95}
                  step={0.01}
                  value={swipe}
                  aria-label="Guided tour comparison swipe"
                  onChange={(e) => set({ swipe: Number(e.target.value) })}
                />
              </label>
            </div>

            <div className="quiet-note" style={{ marginTop: 10 }}>
              <strong>Why might they disagree?</strong> Radar wavelength (L-band ~24 cm vs C-band ~5.6 cm), observation geometry, overpass timing (June offset:{' '}
              <span className="num">
                {c?.radar_disagreement.s1_minus_nisar_seconds
                  ? `${(c.radar_disagreement.s1_minus_nisar_seconds.june / 86400).toFixed(2)} days`
                  : '4.42 days'}
              </span>
              ; October:{' '}
              <span className="num">
                {c?.radar_disagreement.s1_minus_nisar_seconds
                  ? `${(c.radar_disagreement.s1_minus_nisar_seconds.october / 60).toFixed(1)} min`
                  : '45.2 min'}
              </span>
              ), and moisture/wave state may all contribute. This observational record does <strong>not</strong> establish which single factor dominates.{' '}
              <button type="button" className="inline-link" onClick={() => onNavigatePanel('compare')}>
                Full Compare controls →
              </button>
            </div>
          </div>
        )}

        {step === 3 && (
          <div className="tour-section">
            <p className="intro">
              Independent airborne <strong>USACE LiDAR</strong> directly surveys bare-earth elevation (m NAVD88), separating true vertical beach change from ambiguous radar scattering.
            </p>

            <article className="result-spotlight result-spotlight-b" aria-label="Headline Result B — Physical coastal change">
              <div className="panel-heading">
                <span className="eyebrow">Result B · Physical Coastal Change</span>
                <span className="badge badge-observed">Measured LiDAR</span>
              </div>
              <div className="spotlight-kpi-row">
                <strong className="spotlight-kpi num">−0.268 m</strong>
                <span>median beach lowering</span>
              </div>
              <p className="slot-meta" style={{ margin: '4px 0 6px' }}>
                Measured across <strong className="num">17,654</strong> matched <span className="num">1 m</span> USACE LiDAR cells (<span className="num">y = 700–1199 m</span>); approximately{' '}
                <strong className="num">11,684 m²</strong> exhibited lowering exceeding <span className="num">0.1 m</span>.
                {c?.terrain?.mean_m != null && (
                  <>
                    {' '}Paired <span className="num">y = 700–1190 m</span> reach mean:{' '}
                    <span className="num">{c.terrain.mean_m.toFixed(3)} m</span> (<span className="num">{c.terrain.native_paired_cells?.toLocaleString() ?? '17,466'}</span> cells).
                  </>
                )}
              </p>
              <small className="muted">Measured elevation lowering between June and October surveys — not confirmed net sediment loss across the nearshore profile.</small>
            </article>

            <div className="tour-controls-card">
              <span className="eyebrow">Inspect LiDAR terrain & transects</span>
              <div className="tour-chip-row">
                <button
                  type="button"
                  aria-pressed={activeSlotId === 'lidar-dz'}
                  className={`tour-chip-btn ${activeSlotId === 'lidar-dz' ? 'active' : ''}`}
                  onClick={() => activateOnlySlot('lidar-dz')}
                >
                  LiDAR Δz (Oct − Jun)
                </button>
                <button
                  type="button"
                  aria-pressed={activeSlotId === 'lidar-elevation'}
                  className={`tour-chip-btn ${activeSlotId === 'lidar-elevation' ? 'active' : ''}`}
                  onClick={() => activateOnlySlot('lidar-elevation')}
                >
                  Elevation ({date.startsWith('2026-06') ? 'Jun' : 'Oct'})
                </button>
                <button
                  type="button"
                  aria-pressed={mode === '3d'}
                  className={`tour-chip-btn ${mode === '3d' ? 'active' : ''}`}
                  onClick={() => set({ mode: mode === '3d' ? '2d' : '3d' })}
                >
                  {mode === '3d' ? 'Switch to 2D map' : 'Inspect 3D relief'}
                </button>
              </div>
              {transects?.data?.length ? (
                <label className="tour-select-label">
                  <span>Active cross-section profile (shown below map)</span>
                  <select
                    aria-label="Guided tour transect profile"
                    value={selectedTransectId ?? ''}
                    onChange={(e) => set({ selectedTransectId: e.target.value, showTransects: true, bottomOpen: true })}
                  >
                    {transects.data.map((tr, i) => (
                      <option key={tr.properties.id} value={tr.properties.id}>
                        {tr.properties.id} · Section {i + 1} (y = {tr.properties.frf_y_m} m)
                      </option>
                    ))}
                  </select>
                </label>
              ) : null}
              <div className="tour-inline-actions" style={{ marginTop: 6 }}>
                <button type="button" className="inline-link" onClick={() => set({ bottomOpen: !bottomOpen })}>
                  {bottomOpen ? 'Hide June vs October profile dock' : 'Open June vs October profile dock'}
                </button>
              </div>
            </div>
          </div>
        )}

        {step === 4 && (
          <div className="tour-section">
            <p className="intro">
              Optical satellites snap the instantaneous wet/dry edge at overpass time. Normalizing Sentinel-2 NDWI to <strong>NOAA tide height</strong> and surveyed LiDAR foreshore slope removes tidal illusion.
            </p>

            <div className="tour-controls-card">
              <span className="eyebrow">Before / After Map Toggle · October 2026 (2026-10-16)</span>
              <div className="tour-chip-row" role="group" aria-label="Before and after tide correction map layer">
                <button
                  type="button"
                  aria-pressed={activeSlotId === 'physics-s2-ndwi'}
                  className={`tour-chip-btn ${activeSlotId === 'physics-s2-ndwi' ? 'active' : ''}`}
                  onClick={() => {
                    activateOnlySlot('physics-s2-ndwi');
                    set({ date: '2026-10-16' });
                  }}
                >
                  Before · Raw NDWI waterline
                </button>
                <button
                  type="button"
                  aria-pressed={activeSlotId === 'physics-s2-tide'}
                  className={`tour-chip-btn ${activeSlotId === 'physics-s2-tide' ? 'active' : ''}`}
                  onClick={() => {
                    activateOnlySlot('physics-s2-tide');
                    set({ date: '2026-10-16' });
                  }}
                >
                  After · Tide-corrected waterline
                </button>
              </div>
            </div>

            <article className="result-spotlight result-spotlight-a" aria-label="Headline Result A — Shoreline accuracy">
              <div className="panel-heading">
                <span className="eyebrow">Result A · Shoreline Accuracy (Sentinel-2)</span>
                <span className="badge badge-observed num">−{tideReduction?.toFixed(1) ?? '49.7'}%</span>
              </div>
              <div className="spotlight-kpi-row">
                <strong className="spotlight-kpi num">{tideReduction?.toFixed(1) ?? '49.7'}% LOWER RMSE</strong>
                <span className="num">
                  {rawRmse?.toFixed(2) ?? '7.42'} m → {tideRmse?.toFixed(2) ?? '3.73'} m
                </span>
              </div>

              <div className="rmse-compare-bars" style={{ marginTop: 8 }}>
                <div className="rmse-bar-row">
                  <div className="rmse-bar-label">
                    <span>Raw optical NDWI (Before)</span>
                    <strong className="num">{rawRmse?.toFixed(2) ?? '7.42'} m RMSE</strong>
                  </div>
                  <div className="rmse-track">
                    <div className="rmse-fill rmse-before" style={{ width: '100%' }} />
                  </div>
                </div>
                <div className="rmse-bar-row">
                  <div className="rmse-bar-label">
                    <span>Tide-corrected (After)</span>
                    <strong className="num">{tideRmse?.toFixed(2) ?? '3.73'} m RMSE</strong>
                  </div>
                  <div className="rmse-track">
                    <div
                      className="rmse-fill rmse-after"
                      style={{
                        width: `${rawRmse && tideRmse ? Math.min(100, (tideRmse / rawRmse) * 100).toFixed(1) : '50.3'}%`,
                      }}
                    />
                  </div>
                </div>
              </div>

              <p className="slot-meta" style={{ margin: '6px 0 0' }}>
                Retrospective validation across <strong className="num">{mhwN ?? 36}</strong> matched October LiDAR mean-high-water (<span className="num">0.359 m NAVD88</span>) positions. Not claimed as universal; attributed strictly to Sentinel-2 optical physics — <strong>never NISAR</strong>.
              </p>
            </article>

            {octWaterline && axisCandidates.length >= 2 && (
              <div className="waterline-axis-viz" aria-label="Cross-shore waterline comparison for selected transect">
                <div className="panel-heading" style={{ marginBottom: 6 }}>
                  <span className="eyebrow">Transect Check · {a?.transect_id ?? selectedTransectId} (Oct 2026)</span>
                  <span className="num muted">
                    NOAA Tide {octWaterline.environment?.water_level_m_mllw?.toFixed(3) ?? '—'} m MLLW
                  </span>
                </div>
                <div className="waterline-track">
                  {rawX != null && (
                    <div className="waterline-marker marker-raw" style={{ left: toAxisPct(rawX) }} title={`Raw NDWI: ${rawX.toFixed(2)} m`}>
                      <span className="marker-dot" />
                      <small className="num">Raw {rawX.toFixed(1)} m</small>
                    </div>
                  )}
                  {tideX != null && (
                    <div className="waterline-marker marker-tide" style={{ left: toAxisPct(tideX) }} title={`Tide-corrected: ${tideX.toFixed(2)} m`}>
                      <span className="marker-dot" />
                      <small className="num">Tide {tideX.toFixed(1)} m</small>
                    </div>
                  )}
                  {octProfileMhwX != null && (
                    <div className="waterline-marker marker-lidar" style={{ left: toAxisPct(octProfileMhwX) }} title={`LiDAR MHW 0.359 m: ${octProfileMhwX.toFixed(2)} m`}>
                      <span className="marker-dot" />
                      <small className="num">LiDAR {octProfileMhwX.toFixed(1)} m</small>
                    </div>
                  )}
                </div>
                <div className="waterline-axis-labels num muted">
                  <span>← Landward (FRF x, m)</span>
                  <span>Seaward →</span>
                </div>
              </div>
            )}

            <div className="tour-conclusion">
              <strong>Don&apos;t just detect change. Verify it.</strong>
              <p className="slot-meta" style={{ margin: '4px 0 0' }}>
                Raw satellite detections can disagree across frequencies or reflect tidal stage alone. Pairing optical physics with independent NOAA tide and USACE LiDAR ground truth separates real coastal change from apparent shifts.
              </p>
            </div>
          </div>
        )}
      </div>

      <footer className="tour-footer">
        <div className="tour-footer-row">
          <button type="button" className="tour-btn-secondary" disabled={step === 0} onClick={() => setStep((s) => Math.max(0, s - 1))}>
            ← Back
          </button>
          {step < TOTAL_STEPS - 1 ? (
            <button type="button" className="tour-btn-primary" onClick={() => setStep((s) => Math.min(TOTAL_STEPS - 1, s + 1))}>
              Next →
            </button>
          ) : (
            <div className="tour-footer-end">
              <button type="button" className="tour-btn-secondary" onClick={() => setStep(0)}>
                Restart Tour
              </button>
              <button type="button" className="tour-btn-primary" onClick={onExplore}>
                Explore Freely
              </button>
            </div>
          )}
        </div>
        <button type="button" className="inline-link" style={{ alignSelf: 'flex-start' }} onClick={() => onNavigatePanel('findings')}>
          Open full Findings & validation tables →
        </button>
      </footer>
    </section>
  );
}
