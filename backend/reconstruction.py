"""Coastal boundary state reconstruction and sensor boundary extraction for FastAPI.

Loads the verified sensor boundary picks (outputs/sensor_boundaries.csv),
cross-validated error scales (outputs/metrics.csv), LiDAR validation boundaries
(outputs/lidar_boundaries.csv), and extracts NISAR L-band HH/HV gradient
transitions from the verified comparison GeoTIFF bundle
(data/processed/verified/comparison/nisar_{june,october}_{HHHH,HVHV}_db.tif)
using the exact 11 m running-mean max-gradient rule from src/frf.py.

Also runs the feature-separated coastal state reconstruction from src/reconstruct.py
(Sentinel-2 NDWI waterline + Sentinel-1 VV/VH generalized-Bayesian dune-toe fusion)
using only the Python standard library + NumPy + Rasterio so it works inside the
lightweight API environment without requiring pandas.
"""

import csv
from math import cos, lgamma, log, radians, sin
from pathlib import Path
import numpy as np
import rasterio
from rasterio.warp import transform

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "outputs"
DEFAULT_PROC = ROOT / "data" / "processed"

WATER_PRODUCT = "S2_NDWI"
EXPERIMENTAL_WATER_PRODUCT = "EXP_tideaware_S2"
DUNE_PRODUCTS = ("S1_VV", "S1_VH")

# Cross-shore search domain used by src/reconstruct.py and src/frf.py.
X_MIN_M = 20.0
X_MAX_M = 150.0
GRID_STEP_M = 0.1

# Robust Student-t + uniform outlier observation model (identical to src/reconstruct.py).
STUDENT_T_DF = 4.0
OUTLIER_FRACTION = 0.05
MIN_DISAGREEMENT_M = 15.0
DISAGREEMENT_ERROR_MULTIPLIER = 2.0

RADAR_SMOOTH_M = 11
FRF_ANGLE_RAD = radians(69.9747)
ROWS10 = np.arange(700, 1191, 10)
XGRID = np.arange(-50.0, 301.0, 1.0)

EPOCH_TO_DATE_KEY = {"june": "2026-06", "september": "2026-09", "october": "2026-10"}
DATE_KEY_TO_LABEL = {
    "2026-06": "June 2026",
    "2026-09": "September 2026",
    "2026-10": "October 2026",
}


def _fval(val):
    if val is None or val == "":
        return np.nan
    try:
        v = float(val)
        return v if np.isfinite(v) else np.nan
    except (ValueError, TypeError):
        return np.nan


def _clean(val, digits=2):
    if val is None:
        return None
    try:
        v = float(val)
        return round(v, digits) if np.isfinite(v) else None
    except (ValueError, TypeError):
        return None


def frf_to_ncsp(x, y):
    x_arr = np.asarray(x, dtype=float)
    y_arr = np.asarray(y, dtype=float)
    e = 901951.6805 + x_arr * sin(FRF_ANGLE_RAD) - y_arr * cos(FRF_ANGLE_RAD)
    n = 274093.1562 + x_arr * cos(FRF_ANGLE_RAD) + y_arr * sin(FRF_ANGLE_RAD)
    return e, n


def frf_to_utm(x, y):
    e, n = frf_to_ncsp(x, y)
    u_e, u_n = transform("EPSG:6542", "EPSG:32618", e.ravel().tolist(), n.ravel().tolist())
    return np.asarray(u_e, dtype=float).reshape(np.shape(e)), np.asarray(u_n, dtype=float).reshape(np.shape(n))


def frf_to_lonlat(x, y):
    e, n = frf_to_ncsp(x, y)
    lon, lat = transform("EPSG:6542", "EPSG:4326", e.ravel().tolist(), n.ravel().tolist())
    return list(zip(lon, lat))


def _bilinear_sample(arr, tr, east, north):
    col = (east - tr.c) / tr.a - 0.5
    row = (north - tr.f) / tr.e - 0.5
    h, w = arr.shape
    c0 = np.floor(col).astype(int)
    r0 = np.floor(row).astype(int)
    dc = col - c0
    dr = row - r0
    out = np.full(east.shape, np.nan, dtype=float)
    valid = (c0 >= 0) & (c0 + 1 < w) & (r0 >= 0) & (r0 + 1 < h)
    idx = np.where(valid)
    v00 = arr[r0[idx], c0[idx]]
    v01 = arr[r0[idx], c0[idx] + 1]
    v10 = arr[r0[idx] + 1, c0[idx]]
    v11 = arr[r0[idx] + 1, c0[idx] + 1]
    wdc = dc[idx]
    wdr = dr[idx]
    out[idx] = (1.0 - wdr) * ((1.0 - wdc) * v00 + wdc * v01) + wdr * ((1.0 - wdc) * v10 + wdc * v11)
    return out


def max_gradient_edge(x, v, xmin=X_MIN_M, xmax=X_MAX_M, sign=-1, smooth_m=RADAR_SMOOTH_M):
    """Exact port of src/frf.py max_gradient_edge without pandas."""
    half = smooth_m // 2
    min_periods = half + 1
    vs = np.full_like(v, np.nan, dtype=float)
    n = len(v)
    for i in range(n):
        window = v[max(0, i - half):min(n, i + half + 1)]
        ok = np.isfinite(window)
        if int(ok.sum()) >= min_periods:
            vs[i] = float(np.mean(window[ok]))
    sel = np.isfinite(vs) & (x >= xmin) & (x <= xmax)
    if int(sel.sum()) < 5:
        return np.nan
    xs, vv = x[sel], vs[sel]
    g = np.gradient(vv, xs) * sign
    k = int(np.argmax(g))
    if g[k] <= 0:
        return np.nan
    lo = hi = k
    while lo > 0 and g[lo - 1] >= 0.98 * g[k]:
        lo -= 1
    while hi < len(g) - 1 and g[hi + 1] >= 0.98 * g[k]:
        hi += 1
    return float((xs[lo] + xs[hi]) / 2.0)


def extract_nisar_boundaries(comparison_dir: Path, comparison_manifest: dict):
    """Extract NISAR HH and HV max-gradient transitions along FRF y = 700..1190 m."""
    radar_meta = comparison_manifest.get("source", {}).get("nisar", {})
    out = {}
    if not comparison_dir.is_dir():
        return out

    # Precompute UTM coordinates for the 10 one-metre lines per 10 m FRF row.
    utm_grids = []
    for dy in range(-5, 5):
        xg, yg = np.meshgrid(XGRID, ROWS10 + dy)
        utm_grids.append(frf_to_utm(xg, yg))

    for epoch, date_key in (("june", "2026-06"), ("october", "2026-10")):
        meta = radar_meta.get(epoch, {})
        acquired_at = meta.get("acquisition_start_utc")
        granule = meta.get("granule")
        for pol, band in (("HH", "HHHH"), ("HV", "HVHV")):
            tif = comparison_dir / f"nisar_{epoch}_{band}_db.tif"
            if not tif.is_file():
                continue
            with rasterio.open(tif) as ds:
                arr = ds.read(1).astype(float)
                if ds.nodata is not None:
                    arr[arr == ds.nodata] = np.nan
                tr = ds.transform
            stack = [_bilinear_sample(arr, tr, e, n) for e, n in utm_grids]
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                med = np.nanmedian(np.stack(stack), axis=0)
            for idx, y in enumerate(ROWS10):
                bx = max_gradient_edge(XGRID, med[idx], X_MIN_M, X_MAX_M, sign=-1)
                if np.isfinite(bx):
                    out[(date_key, int(y), f"NISAR_{pol}")] = {
                        "boundary_x": float(bx),
                        "acquired_at": acquired_at,
                        "granule_id": granule,
                        "pixel_spacing_m": 10.0,
                    }
    return out


def _student_t_logpdf(x, location, scale, degrees_of_freedom):
    nu = degrees_of_freedom
    z = (x - location) / scale
    constant = (
        lgamma((nu + 1.0) / 2.0)
        - lgamma(nu / 2.0)
        - 0.5 * log(nu * np.pi)
        - log(scale)
    )
    return constant - ((nu + 1.0) / 2.0) * np.log1p((z * z) / nu)


def _robust_observation_loglikelihood(grid, observed_x, cv_rmse):
    inlier = _student_t_logpdf(grid, observed_x, cv_rmse, STUDENT_T_DF)
    outlier = -log(X_MAX_M - X_MIN_M)
    a = np.log1p(-OUTLIER_FRACTION) + inlier
    b = log(OUTLIER_FRACTION) + outlier
    return np.logaddexp(a, b)


def bayesian_dune_estimate(vv, vh, sv, sh):
    """Exact port of src/reconstruct.py bayesian_dune_estimate."""
    observations = []
    if np.isfinite(vv) and np.isfinite(sv) and sv > 0:
        observations.append(("VV", float(vv), float(sv), 0.5 if (
            np.isfinite(vh) and np.isfinite(sh) and sh > 0
        ) else 1.0))
    if np.isfinite(vh) and np.isfinite(sh) and sh > 0:
        observations.append(("VH", float(vh), float(sh), 0.5 if (
            np.isfinite(vv) and np.isfinite(sv) and sv > 0
        ) else 1.0))

    empty = {
        "accepted_x": np.nan,
        "map_x": np.nan,
        "median_x": np.nan,
        "ci90_low": np.nan,
        "ci90_high": np.nan,
        "posterior_sd": np.nan,
        "disagreement": np.nan,
        "disagreement_limit": np.nan,
        "power_vv": np.nan,
        "power_vh": np.nan,
        "status": "not estimated: no valid radar observation",
    }
    if not observations:
        return empty

    grid = np.arange(X_MIN_M, X_MAX_M + GRID_STEP_M / 2.0, GRID_STEP_M)
    log_posterior = np.zeros_like(grid)
    for _, observed_x, scale, power in observations:
        log_posterior += power * _robust_observation_loglikelihood(grid, observed_x, scale)

    log_posterior -= np.max(log_posterior)
    posterior = np.exp(log_posterior)
    total = posterior.sum()
    if not np.isfinite(total) or total <= 0:
        return empty
    posterior /= total

    cdf = np.cumsum(posterior)
    cdf[-1] = 1.0
    map_x = float(grid[int(np.argmax(posterior))])
    median_x = float(np.interp(0.50, cdf, grid))
    ci90_low = float(np.interp(0.05, cdf, grid))
    ci90_high = float(np.interp(0.95, cdf, grid))
    posterior_mean = float(np.sum(grid * posterior))
    posterior_sd = float(np.sqrt(np.sum(np.square(grid - posterior_mean) * posterior)))

    vv_valid = any(name == "VV" for name, *_ in observations)
    vh_valid = any(name == "VH" for name, *_ in observations)
    power_vv = 0.5 if vv_valid and vh_valid else (1.0 if vv_valid else 0.0)
    power_vh = 0.5 if vv_valid and vh_valid else (1.0 if vh_valid else 0.0)

    disagreement = np.nan
    disagreement_limit = np.nan
    conflict = False
    if vv_valid and vh_valid:
        disagreement = abs(float(vv) - float(vh))
        disagreement_limit = max(
            MIN_DISAGREEMENT_M,
            DISAGREEMENT_ERROR_MULTIPLIER * float(np.hypot(sv, sh)),
        )
        conflict = disagreement > disagreement_limit

    boundary_limited = (
        map_x <= X_MIN_M + GRID_STEP_M
        or map_x >= X_MAX_M - GRID_STEP_M
    )

    if conflict:
        accepted_x = np.nan
        status = "ambiguous: VV/VH disagreement; fused point withheld"
    elif boundary_limited:
        accepted_x = np.nan
        status = "uncertain: posterior reaches search-domain boundary"
    else:
        accepted_x = map_x
        if vv_valid and vh_valid:
            status = "accepted: robust generalized-Bayesian VV/VH fusion"
        else:
            status = "provisional: single-polarization Bayesian estimate"

    return {
        "accepted_x": accepted_x,
        "map_x": map_x,
        "median_x": median_x,
        "ci90_low": ci90_low,
        "ci90_high": ci90_high,
        "posterior_sd": posterior_sd,
        "disagreement": disagreement,
        "disagreement_limit": disagreement_limit,
        "power_vv": power_vv,
        "power_vh": power_vh,
        "status": status,
    }


def _read_csv_rows(path: Path):
    if not path.is_file():
        return []
    with open(path, encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


class CoastalReconstructionStore:
    """In-memory store of sensor boundaries, LiDAR references, and Bayesian coastal state."""

    def __init__(self, verified_root: Path, outputs_dir: Path = DEFAULT_OUT, processed_dir: Path = DEFAULT_PROC):
        self.verified_root = verified_root
        self.outputs_dir = outputs_dir
        self.processed_dir = processed_dir
        self.sensor_picks = {}
        self.lidar_refs = {}
        self.rmse = {}
        self.metrics_rows = []
        self.reconstructed = {}
        self.skill_summary = {}
        self.boundary_geojson = {}
        self.extra_acquisitions = []

        # Only load repo-level outputs if verified_root points at the real verified bundle
        # (so isolated unit tests passing an empty tmp_path stay empty).
        if (verified_root / "lidar/manifest.json").is_file() and outputs_dir.is_dir():
            self._load()

    def _load(self):
        comparison_manifest = {}
        comp_path = self.verified_root / "comparison/manifest.json"
        if comp_path.is_file():
            import json
            comparison_manifest = json.loads(comp_path.read_text(encoding="utf-8"))

        # 1. Load cross-validated RMSE metrics
        for row in _read_csv_rows(self.outputs_dir / "metrics.csv"):
            self.metrics_rows.append(row)
            d = row.get("date", "")
            r_val = _fval(row.get("RMSE_m"))
            if d and d != "pooled" and np.isfinite(r_val) and r_val > 0:
                self.rmse[(row["product"], row["lidar_boundary"], d)] = float(r_val)

        # 2. Load sensor boundary picks (S2_NDWI, S2_MNDWI, EXP_tideaware_S2, S1_VV, S1_VH)
        for row in _read_csv_rows(self.outputs_dir / "sensor_boundaries.csv"):
            d = row.get("date", "")
            y = int(round(float(row["y"])))
            prod = row["product"]
            bx = _fval(row.get("boundary_x"))
            if np.isfinite(bx):
                self.sensor_picks[(d, y, prod)] = {
                    "boundary_x": float(bx),
                    "acquired_at": row.get("acquisition_utc") or None,
                    "granule_id": row.get("granule_id") or None,
                    "pixel_spacing_m": _fval(row.get("pixel_spacing_m")) or 10.0,
                }

        # 3. Extract NISAR HH and HV max-gradient transitions from verified GeoTIFFs
        nisar_picks = extract_nisar_boundaries(self.verified_root / "comparison", comparison_manifest)
        self.sensor_picks.update(nisar_picks)

        # 4. Load LiDAR validation boundaries (B1_wetdry, B2_dunetoe, B3_contour, MHW)
        for row in _read_csv_rows(self.outputs_dir / "lidar_boundaries.csv"):
            d = row.get("date", "")
            y = int(round(float(row["y"])))
            self.lidar_refs[(d, y)] = {
                "B1_wetdry": _fval(row.get("B1_wetdry")),
                "B2_dunetoe": _fval(row.get("B2_dunetoe")),
                "B3_contour": _fval(row.get("B3_contour")),
                "MHW": _fval(row.get("MHW")),
                "B3_contour_z": _fval(row.get("B3_contour_z")) or 1.5,
                "MHW_z": _fval(row.get("MHW_z")) or 0.36,
            }

        # 5. Load S1 and S2 acquisition metadata for /api/acquisitions
        for row in _read_csv_rows(self.processed_dir / "s1_meta.csv"):
            self.extra_acquisitions.append({
                "id": row["item_id"],
                "sensor": "SENTINEL-1",
                "product": "IW_GRDH_1SDV_RTC",
                "acquired_at": row["acquisition_utc"],
                "polarizations": ["VV", "VH"],
                "orbit_direction": row.get("orbit_state") or "ascending",
                "source_url": row.get("url") or None,
                "qa": {"relative_orbit": int(float(row.get("relative_orbit", 106))), "pixel_m": float(row.get("pixel_m", 10.0))},
            })
        for row in _read_csv_rows(self.processed_dir / "s2_meta.csv"):
            clear_frac = _fval(row.get("site_clear_fraction"))
            cloud_pct = round(max(0.0, (1.0 - clear_frac) * 100.0), 2) if np.isfinite(clear_frac) else None
            self.extra_acquisitions.append({
                "id": row["item_id"],
                "sensor": "SENTINEL-2",
                "product": "L2A_MSI",
                "acquired_at": row["acquisition_utc"],
                "cloud_cover_pct": cloud_pct,
                "source_url": row.get("self_href") or None,
                "qa": {
                    "boa_offset_applied": row.get("boa_offset_applied") == "True",
                    "site_clear_fraction": _clean(clear_frac, 4),
                    "pixel_m_green_nir": float(row.get("pixel_m_green_nir", 10.0)),
                },
            })

        # 6. Run Bayesian coastal state reconstruction across all (date, y) rows
        self._build_reconstruction()
        self._build_boundary_geojson(comparison_manifest)

    def _build_reconstruction(self):
        dates = ("2026-06", "2026-09", "2026-10")
        bayes_errors = []
        baseline_errors = []
        waterline_errors = []

        for d in dates:
            for y in ROWS10:
                y_int = int(y)
                s2_ndwi = self.sensor_picks.get((d, y_int, "S2_NDWI"), {})
                s2_mndwi = self.sensor_picks.get((d, y_int, "S2_MNDWI"), {})
                s2_tide = self.sensor_picks.get((d, y_int, "EXP_tideaware_S2"), {})
                s1_vv = self.sensor_picks.get((d, y_int, "S1_VV"), {})
                s1_vh = self.sensor_picks.get((d, y_int, "S1_VH"), {})
                nisar_hh = self.sensor_picks.get((d, y_int, "NISAR_HH"), {})
                nisar_hv = self.sensor_picks.get((d, y_int, "NISAR_HV"), {})
                lref = self.lidar_refs.get((d, y_int), {})

                wl_x = _fval(s2_ndwi.get("boundary_x"))
                wl_rmse = self.rmse.get(("S2_NDWI", "B1_wetdry", d), np.nan)
                wl_tide_x = _fval(s2_tide.get("boundary_x"))
                wl_tide_rmse = self.rmse.get(("EXP_tideaware_S2", "B1_wetdry", d), np.nan)

                vv = _fval(s1_vv.get("boundary_x"))
                vh = _fval(s1_vh.get("boundary_x"))
                sv = self.rmse.get(("S1_VV", "B2_dunetoe", d), np.nan)
                sh = self.rmse.get(("S1_VH", "B2_dunetoe", d), np.nan)
                bayes = bayesian_dune_estimate(vv, vh, sv, sh)

                valid_pairs = [(x, s) for x, s in ((vv, sv), (vh, sh)) if np.isfinite(x) and np.isfinite(s) and s > 0]
                if valid_pairs:
                    w = np.array([1.0 / (s * s) for _, s in valid_pairs])
                    pos = np.array([x for x, _ in valid_pairs])
                    baseline_x = float(np.sum(w * pos) / w.sum())
                    cons_rmse = float(max(s for _, s in valid_pairs))
                else:
                    baseline_x = np.nan
                    cons_rmse = np.nan

                b1 = _fval(lref.get("B1_wetdry"))
                b2 = _fval(lref.get("B2_dunetoe"))
                b3 = _fval(lref.get("B3_contour"))

                if np.isfinite(wl_x) and np.isfinite(b1):
                    waterline_errors.append(wl_x - b1)
                if np.isfinite(bayes["accepted_x"]) and np.isfinite(b2):
                    bayes_errors.append(bayes["accepted_x"] - b2)
                if np.isfinite(baseline_x) and np.isfinite(b2):
                    baseline_errors.append(baseline_x - b2)

                self.reconstructed[(d, y_int)] = {
                    "date": d,
                    "epoch_label": DATE_KEY_TO_LABEL.get(d, d),
                    "y_m": y_int,
                    "waterline": {
                        "x_frf_m": _clean(wl_x, 2),
                        "cv_rmse_m": _clean(wl_rmse, 2),
                        "source": "Sentinel-2 NDWI" if np.isfinite(wl_x) else "missing",
                        "status": "plausible; date-specific spatial-CV error scale" if np.isfinite(wl_x) else "not estimated",
                        "acquired_at": s2_ndwi.get("acquired_at"),
                        "granule_id": s2_ndwi.get("granule_id"),
                        "tide_aware_experimental_x_frf_m": _clean(wl_tide_x, 2),
                        "tide_aware_cv_rmse_m": _clean(wl_tide_rmse, 2),
                        "mndwi_x_frf_m": _clean(_fval(s2_mndwi.get("boundary_x")), 2),
                    },
                    "dunetoe": {
                        "accepted_x_frf_m": _clean(bayes["accepted_x"], 2),
                        "bayes_map_x_frf_m": _clean(bayes["map_x"], 2),
                        "bayes_median_x_frf_m": _clean(bayes["median_x"], 2),
                        "ci90_low_frf_m": _clean(bayes["ci90_low"], 2),
                        "ci90_high_frf_m": _clean(bayes["ci90_high"], 2),
                        "posterior_sd_m": _clean(bayes["posterior_sd"], 2),
                        "vv_vh_disagreement_m": _clean(bayes["disagreement"], 2),
                        "vv_vh_disagreement_limit_m": _clean(bayes["disagreement_limit"], 2),
                        "cv_rmse_conservative_m": _clean(cons_rmse, 2),
                        "baseline_weighted_x_frf_m": _clean(baseline_x, 2),
                        "radar_vv_x_frf_m": _clean(vv, 2),
                        "radar_vh_x_frf_m": _clean(vh, 2),
                        "nisar_hh_x_frf_m": _clean(_fval(nisar_hh.get("boundary_x")), 2),
                        "nisar_hv_x_frf_m": _clean(_fval(nisar_hv.get("boundary_x")), 2),
                        "source": (
                            "Sentinel-1 robust Bayesian fusion"
                            if "VV/VH fusion" in bayes["status"]
                            else ("Sentinel-1 Bayesian single-polarization"
                                  if "single-polarization" in bayes["status"]
                                  else "Sentinel-1 observations; estimate withheld")
                        ),
                        "status": bayes["status"],
                        "acquired_at": s1_vv.get("acquired_at") or s1_vh.get("acquired_at"),
                        "granule_id": s1_vv.get("granule_id") or s1_vh.get("granule_id"),
                    },
                    "validation_lidar": {
                        "wetdry_x_frf_m": _clean(b1, 2),
                        "dunetoe_x_frf_m": _clean(b2, 2),
                        "contour_1p5m_x_frf_m": _clean(b3, 2),
                        "usage": "validation-only; never used in satellite boundary estimation",
                    },
                }

        def _rmse(errs):
            if not errs:
                return None
            arr = np.asarray(errs, dtype=float)
            return round(float(np.sqrt(np.mean(np.square(arr)))), 3)

        def _mae(errs):
            if not errs:
                return None
            arr = np.asarray(errs, dtype=float)
            return round(float(np.mean(np.abs(arr))), 3)

        self.skill_summary = {
            "waterline_s2_ndwi_rmse_m": _rmse(waterline_errors),
            "waterline_s2_ndwi_mae_m": _mae(waterline_errors),
            "waterline_s2_ndwi_n": len(waterline_errors),
            "dunetoe_bayesian_accepted_rmse_m": _rmse(bayes_errors),
            "dunetoe_bayesian_accepted_mae_m": _mae(bayes_errors),
            "dunetoe_bayesian_accepted_n": len(bayes_errors),
            "dunetoe_baseline_all_rmse_m": _rmse(baseline_errors),
        }

    def export_csvs(self, out_dir: Path = DEFAULT_OUT):
        """Write outputs/reconstructed_state.csv and outputs/reconstruction_metrics.csv."""
        out_dir.mkdir(parents=True, exist_ok=True)
        rows_out = []
        dates = ("2026-06", "2026-09", "2026-10")
        for d in dates:
            for y in ROWS10:
                y_int = int(y)
                rec = self.reconstructed.get((d, y_int))
                if not rec:
                    continue
                wl = rec["waterline"]
                dt = rec["dunetoe"]
                vl = rec["validation_lidar"]
                rows_out.append({
                    "date": d,
                    "y": y_int,
                    "EXP_tideaware_S2": wl["tide_aware_experimental_x_frf_m"],
                    "S1_VH": dt["radar_vh_x_frf_m"],
                    "S1_VV": dt["radar_vv_x_frf_m"],
                    "S2_MNDWI": wl["mndwi_x_frf_m"],
                    "S2_NDWI": wl["x_frf_m"],
                    "NISAR_HH": dt["nisar_hh_x_frf_m"],
                    "NISAR_HV": dt["nisar_hv_x_frf_m"],
                    "waterline_x_m": wl["x_frf_m"],
                    "waterline_cv_rmse_m": wl["cv_rmse_m"],
                    "waterline_source": wl["source"],
                    "waterline_tideaware_experimental_x_m": wl["tide_aware_experimental_x_frf_m"],
                    "waterline_tideaware_cv_rmse_m": wl["tide_aware_cv_rmse_m"],
                    "dunetoe_x_m": dt["accepted_x_frf_m"],
                    "dunetoe_baseline_weighted_x_m": dt["baseline_weighted_x_frf_m"],
                    "dunetoe_bayes_map_x_m": dt["bayes_map_x_frf_m"],
                    "dunetoe_bayes_median_x_m": dt["bayes_median_x_frf_m"],
                    "dunetoe_bayes_ci90_low_m": dt["ci90_low_frf_m"],
                    "dunetoe_bayes_ci90_high_m": dt["ci90_high_frf_m"],
                    "dunetoe_bayes_posterior_sd_m": dt["posterior_sd_m"],
                    "dunetoe_vv_vh_disagreement_m": dt["vv_vh_disagreement_m"],
                    "dunetoe_vv_vh_disagreement_limit_m": dt["vv_vh_disagreement_limit_m"],
                    "dunetoe_cv_rmse_conservative_m": dt["cv_rmse_conservative_m"],
                    "dunetoe_source": dt["source"],
                    "dunetoe_status": dt["status"],
                    "radar_transition_vv_x_m": dt["radar_vv_x_frf_m"],
                    "radar_transition_vh_x_m": dt["radar_vh_x_frf_m"],
                    "validation_lidar_wetdry_x_m": vl["wetdry_x_frf_m"],
                    "validation_lidar_dunetoe_x_m": vl["dunetoe_x_frf_m"],
                    "validation_lidar_1p5m_contour_x_m": vl["contour_1p5m_x_frf_m"],
                    "state_scope": "observed boundary features; not full terrain or bathymetry",
                    "waterline_status": wl["status"],
                })
        if rows_out:
            fieldnames = list(rows_out[0].keys())
            with open(out_dir / "reconstructed_state.csv", "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for r in rows_out:
                    writer.writerow({k: ("" if v is None else v) for k, v in r.items()})


    def _build_boundary_geojson(self, comparison_manifest: dict):
        """Build EPSG:4326 GeoJSON FeatureCollections for s2-boundary and nisar-boundary."""
        for epoch, date_key in (("june", "2026-06"), ("october", "2026-10")):
            epoch_label = DATE_KEY_TO_LABEL[date_key]
            # 1. Sentinel-2 optical waterline (S2_NDWI + EXP_tideaware_S2)
            s2_features = []
            for prod, name, role in (
                ("S2_NDWI", "Sentinel-2 NDWI waterline (threshold 0.0)", "primary"),
                ("EXP_tideaware_S2", "Sentinel-2 tide-adjusted NDWI waterline (experimental)", "experimental"),
            ):
                xs, ys = [], []
                acquired_at = None
                granule_id = None
                for y in ROWS10:
                    pick = self.sensor_picks.get((date_key, int(y), prod))
                    if pick and np.isfinite(pick["boundary_x"]):
                        xs.append(pick["boundary_x"])
                        ys.append(float(y))
                        acquired_at = acquired_at or pick.get("acquired_at")
                        granule_id = granule_id or pick.get("granule_id")
                if len(xs) >= 2:
                    coords = frf_to_lonlat(xs, ys)
                    s2_features.append({
                        "type": "Feature",
                        "properties": {
                            "id": f"s2-boundary-{epoch}-{prod.lower()}",
                            "slot": "s2-boundary",
                            "sensor": "SENTINEL-2",
                            "product": prod,
                            "definition": name,
                            "role": role,
                            "epoch_label": epoch_label,
                            "acquired_at": acquired_at,
                            "granule_id": granule_id,
                            "cv_rmse_m": _clean(self.rmse.get((prod, "B1_wetdry", date_key)), 2),
                        },
                        "geometry": {"type": "LineString", "coordinates": coords},
                    })
            if s2_features:
                self.boundary_geojson[f"s2-boundary-{epoch}"] = {
                    "type": "FeatureCollection",
                    "features": s2_features,
                }

            # 2. NISAR radar backscatter transition (NISAR_HH + NISAR_HV)
            nisar_features = []
            for prod, pol in (("NISAR_HH", "HH"), ("NISAR_HV", "HV")):
                xs, ys = [], []
                acquired_at = None
                granule_id = None
                for y in ROWS10:
                    pick = self.sensor_picks.get((date_key, int(y), prod))
                    if pick and np.isfinite(pick["boundary_x"]):
                        xs.append(pick["boundary_x"])
                        ys.append(float(y))
                        acquired_at = acquired_at or pick.get("acquired_at")
                        granule_id = granule_id or pick.get("granule_id")
                if len(xs) >= 2:
                    coords = frf_to_lonlat(xs, ys)
                    nisar_features.append({
                        "type": "Feature",
                        "properties": {
                            "id": f"nisar-boundary-{epoch}-{pol.lower()}",
                            "slot": "nisar-boundary",
                            "sensor": "NISAR",
                            "product": prod,
                            "polarization": pol,
                            "definition": f"NISAR L-band {pol} max-gradient backscatter transition (11 m smoothed)",
                            "epoch_label": epoch_label,
                            "acquired_at": acquired_at,
                            "granule_id": granule_id,
                            "note": "Radar roughness/moisture transition; never equated with physical shoreline erosion",
                        },
                        "geometry": {"type": "LineString", "coordinates": coords},
                    })
            if nisar_features:
                self.boundary_geojson[f"nisar-boundary-{epoch}"] = {
                    "type": "FeatureCollection",
                    "features": nisar_features,
                }

    def transect_boundaries(self, y_frf_m: int, x_origin_frf_m: float, lidar_epoch_utc: dict):
        """Return BoundaryPick list for a transect at FRF y = y_frf_m.

        `x_m` is relative to the transect line start (`x_origin_frf_m`) so it aligns
        directly with `profiles[].points[].x_m` on the CrossSection chart, while
        `x_frf_m` gives the absolute FRF cross-shore coordinate in metres.
        """
        picks = []
        y = int(round(y_frf_m))
        for epoch, date_key in (("june", "2026-06"), ("october", "2026-10")):
            epoch_label = DATE_KEY_TO_LABEL[date_key]
            # 1. Optical waterline (Sentinel-2 NDWI)
            s2 = self.sensor_picks.get((date_key, y, "S2_NDWI"))
            if s2 and np.isfinite(s2["boundary_x"]):
                x_frf = float(s2["boundary_x"])
                picks.append({
                    "type": "optical",
                    "sensor": "SENTINEL-2",
                    "definition": "NDWI = 0.0 optical waterline",
                    "epoch_label": epoch_label,
                    "acquired_at": s2.get("acquired_at"),
                    "x_m": round(x_frf - x_origin_frf_m, 2),
                    "x_frf_m": round(x_frf, 2),
                    "uncertainty_m": _clean(self.rmse.get(("S2_NDWI", "B1_wetdry", date_key)), 2),
                })

            # 2. NISAR L-band HH radar transition
            nhh = self.sensor_picks.get((date_key, y, "NISAR_HH"))
            if nhh and np.isfinite(nhh["boundary_x"]):
                x_frf = float(nhh["boundary_x"])
                picks.append({
                    "type": "radar",
                    "sensor": "NISAR",
                    "definition": "L-band HH backscatter transition",
                    "epoch_label": epoch_label,
                    "acquired_at": nhh.get("acquired_at"),
                    "x_m": round(x_frf - x_origin_frf_m, 2),
                    "x_frf_m": round(x_frf, 2),
                    "uncertainty_m": 10.0,
                })

            # 3. Sentinel-1 C-band VV/VH radar transitions
            for prod, pol in (("S1_VV", "VV"), ("S1_VH", "VH")):
                s1 = self.sensor_picks.get((date_key, y, prod))
                if s1 and np.isfinite(s1["boundary_x"]):
                    x_frf = float(s1["boundary_x"])
                    picks.append({
                        "type": "radar",
                        "sensor": "SENTINEL-1",
                        "definition": f"C-band {pol} backscatter transition",
                        "epoch_label": epoch_label,
                        "acquired_at": s1.get("acquired_at"),
                        "x_m": round(x_frf - x_origin_frf_m, 2),
                        "x_frf_m": round(x_frf, 2),
                        "uncertainty_m": _clean(self.rmse.get((prod, "B2_dunetoe", date_key)), 2),
                    })

            # 4. LiDAR morphological boundaries (B1 wet/dry, B2 dune toe, B3 1.50 m contour)
            lref = self.lidar_refs.get((date_key, y), {})
            lidar_time = lidar_epoch_utc.get(epoch)
            for key, label, unc in (
                ("B1_wetdry", "Foreshore max-steepness wet/dry proxy (B1)", 1.0),
                ("B2_dunetoe", "Dune-toe curvature maximum (B2)", 1.0),
                ("B3_contour", "z = 1.50 m NAVD88 elevation contour (B3)", 0.5),
            ):
                val = _fval(lref.get(key))
                if np.isfinite(val):
                    picks.append({
                        "type": "terrain",
                        "sensor": "LIDAR",
                        "definition": label,
                        "epoch_label": epoch_label,
                        "acquired_at": lidar_time,
                        "x_m": round(float(val) - x_origin_frf_m, 2),
                        "x_frf_m": round(float(val), 2),
                        "uncertainty_m": unc,
                    })
        return picks

    def transect_analysis(self, transect_id: str, y_frf_m: int, x_origin_frf_m: float):
        """Return the feature-separated coastal boundary reconstruction for `transect_id`."""
        y = int(round(y_frf_m))
        epochs_out = []
        for date_key in ("2026-06", "2026-09", "2026-10"):
            rec = self.reconstructed.get((date_key, y))
            if not rec:
                continue
            wl = rec["waterline"]
            dt = rec["dunetoe"]
            vl = rec["validation_lidar"]

            def _rel(x_frf):
                return round(x_frf - x_origin_frf_m, 2) if x_frf is not None else None

            epochs_out.append({
                "date": date_key,
                "epoch_label": rec["epoch_label"],
                "waterline": {
                    **wl,
                    "x_m": _rel(wl["x_frf_m"]),
                    "tide_aware_experimental_x_m": _rel(wl["tide_aware_experimental_x_frf_m"]),
                },
                "dunetoe": {
                    **dt,
                    "accepted_x_m": _rel(dt["accepted_x_frf_m"]),
                    "bayes_map_x_m": _rel(dt["bayes_map_x_frf_m"]),
                    "bayes_median_x_m": _rel(dt["bayes_median_x_frf_m"]),
                    "ci90_low_m": _rel(dt["ci90_low_frf_m"]),
                    "ci90_high_m": _rel(dt["ci90_high_frf_m"]),
                    "radar_vv_x_m": _rel(dt["radar_vv_x_frf_m"]),
                    "radar_vh_x_m": _rel(dt["radar_vh_x_frf_m"]),
                    "nisar_hh_x_m": _rel(dt["nisar_hh_x_frf_m"]),
                    "nisar_hv_x_m": _rel(dt["nisar_hv_x_frf_m"]),
                },
                "validation_lidar": {
                    **vl,
                    "wetdry_x_m": _rel(vl["wetdry_x_frf_m"]),
                    "dunetoe_x_m": _rel(vl["dunetoe_x_frf_m"]),
                    "contour_1p5m_x_m": _rel(vl["contour_1p5m_x_frf_m"]),
                },
            })

        if not epochs_out:
            return {"status": "unavailable", "reason": "No reconstructed boundary state available for transect"}

        jun = next((e for e in epochs_out if e["date"] == "2026-06"), None)
        octo = next((e for e in epochs_out if e["date"] == "2026-10"), None)
        waterline_shift_m = None
        if jun and octo and jun["waterline"]["x_frf_m"] is not None and octo["waterline"]["x_frf_m"] is not None:
            waterline_shift_m = round(octo["waterline"]["x_frf_m"] - jun["waterline"]["x_frf_m"], 2)

        dunetoe_shift_m = None
        if jun and octo and jun["dunetoe"]["accepted_x_frf_m"] is not None and octo["dunetoe"]["accepted_x_frf_m"] is not None:
            dunetoe_shift_m = round(octo["dunetoe"]["accepted_x_frf_m"] - jun["dunetoe"]["accepted_x_frf_m"], 2)

        return {
            "transect_id": transect_id,
            "frf_y_m": y,
            "x_origin_frf_m": round(float(x_origin_frf_m), 2),
            "x_reference": f"x_frf_m is USACE FRF cross-shore distance (m); x_m = x_frf_m - {x_origin_frf_m:g} m (distance along transect from line start)",
            "analysis_crs": "EPSG:32618",
            "model_name": "Feature-Separated Coastal Boundary Reconstruction",
            "model_version": "reconstruct-v1-bayesian",
            "state_scope": "observed boundary features; not full terrain or bathymetry",
            "inferred": True,
            "units": "m",
            "uncertainty_method": (
                "Sentinel-2 NDWI waterline with spatial block-CV RMSE; "
                "Sentinel-1 VV/VH generalized-Bayesian Student-t (df=4) + 5% uniform outlier fusion "
                "with 0.5 power tempering and VV/VH disagreement withholding"
            ),
            "inputs": [
                "Sentinel-2 L2A NDWI (10 m)",
                "Sentinel-1 RTC VV/VH (10 m)",
                "NISAR L2 GCOV HH/HV (10 m)",
                "USACE FRF Dune LiDAR (1 m, validation-only)",
            ],
            "epochs": epochs_out,
            "october_minus_june": {
                "waterline_shift_m": waterline_shift_m,
                "dunetoe_shift_m": dunetoe_shift_m,
            },
            "skill": self.skill_summary,
            "physics_model": {
                "status": "unavailable",
                "reason": "Physics-informed elevation profile model V1 integration is pending independent validation",
                "points": [],
            },
        }

