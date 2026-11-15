"""Buffered, nested alongshore validation of continuous LiDAR elevation change."""

import numpy as np
import rasterio

from .coastal_observations import error_metrics, unwrap
from .nisar_shoreline import frf_centers

STRIP_M = 100
STRIP_ORIGIN_M = 700
BUFFER_M = 30
ALPHAS = (0.01, 0.1, 1, 10, 100, 1000)
NISAR_FEATURES = ("june_hh_db", "june_hv_db", "delta_hh_db", "delta_hv_db")
NON_NISAR_BANDS = {
    "delta_b04_reflectance": "s2_B04_reflectance_change",
    "delta_b11_reflectance": "s2_B11_reflectance_change",
    "delta_mndwi": "s2_mndwi_change",
    "delta_s1_vv_db": "s1_VV_gamma0_db_change",
    "delta_s1_vh_db": "s1_VH_gamma0_db_change",
}
MODELS = {"A": NISAR_FEATURES, "B": tuple(NON_NISAR_BANDS), "C": (*NON_NISAR_BANDS, *NISAR_FEATURES)}
TARGET = "October minus June LiDAR elevation on matching native support aggregated to the verified 10 m grid"


def feature_maps(epoch_channels):
    june, october = [epoch_channels[epoch] for epoch in ("june", "october")]
    return {
        "june_hh_db": june["hh"], "june_hv_db": june["hv"],
        "october_hh_db": october["hh"], "october_hv_db": october["hv"],
        "delta_hh_db": october["hh"] - june["hh"], "delta_hv_db": october["hv"] - june["hv"],
        "june_hh_minus_hv_db": june["hh"] - june["hv"],
        "october_hh_minus_hv_db": october["hh"] - october["hv"],
        "delta_hh_minus_hv_db": (october["hh"] - october["hv"]) - (june["hh"] - june["hv"]),
    }


def strip_splits(y):
    groups = np.floor((y - STRIP_ORIGIN_M) / STRIP_M).astype(int)
    for group in np.unique(groups):
        lo = int(STRIP_ORIGIN_M + group * STRIP_M)
        hi = lo + STRIP_M
        holdout = groups == group
        train = (y <= lo - BUFFER_M) | (y >= hi + BUFFER_M)
        yield lo, hi, train, holdout


def ridge_predictions(x, z, xtest, alpha):
    # The held-out data participate only after training-only standardization and fit.
    mean, scale = x.mean(axis=0), x.std(axis=0)
    scale[scale == 0] = 1
    centered = (x - mean) / scale
    intercept = z.mean()
    coef = np.linalg.solve(centered.T @ centered + alpha * np.eye(x.shape[1]), centered.T @ (z - intercept))
    return intercept + ((xtest - mean) / scale) @ coef


def select_alpha(x, z, y):
    folds = [(train, test) for _, _, train, test in strip_splits(y) if train.sum() >= 2]
    if len(folds) < 2:
        raise ValueError("Fewer than two buffered inner spatial folds")
    losses = [sum(float(np.sum((ridge_predictions(x[train], z[train], x[test], alpha) - z[test]) ** 2))
                  for train, test in folds) for alpha in ALPHAS]
    return ALPHAS[int(np.argmin(losses))]


def heldout_predictions(x, z, y):
    names = ("zero_change", "training_mean", *MODELS)
    predictions = {k: np.full(z.shape, np.nan) for k in names}
    strips = []
    for lo, hi, train, test in strip_splits(y):
        if train.sum() < 2:
            raise ValueError("Insufficient training support after applying the spatial buffer")
        choices = {}
        count = int(test.sum())
        predictions["zero_change"][test] = 0
        predictions["training_mean"][test] = z[train].mean()
        for model in MODELS:
            values = x[model]
            alpha = select_alpha(values[train], z[train], y[train])
            predictions[model][test] = ridge_predictions(values[train], z[train], values[test], alpha)
            choices[model] = alpha
        delta = {name: error_metrics(v[test], z[test]) for name, v in predictions.items()}
        strips.append({
            "frf_y_start_m": lo, "frf_y_end_exclusive_m": hi, "n": count,
            "training_n": int(train.sum()), "buffer_excluded_n": int((~train & ~test).sum()),
            "selected_alpha": choices, "metrics": delta,
            "C_minus_B_rmse_m": delta["C"]["rmse_m"] - delta["B"]["rmse_m"],
        })
    if not all(np.all(np.isfinite(v)) for v in predictions.values()):
        raise ValueError("An observation is missing a spatially held-out prediction")
    return predictions, strips


def ablate(path, grid, nisar_maps, expected_n):
    """Only this evaluation reads the LiDAR target; it never enters features."""
    with rasterio.open(path) as ds:
        if (ds.crs, ds.transform, ds.shape) != grid:
            raise ValueError("LiDAR and radar comparison grids differ")
        selected = unwrap(ds, "all_sensor_valid_overlap") == 1
        n = int(selected.sum())
        if not n or n != expected_n:
            raise ValueError("Strict overlap count disagrees with the verified comparison manifest")
        z = unwrap(ds, "lidar_change_m")[selected]
        if not np.all(unwrap(ds, "lidar_change_m_valid")[selected] == 1) or not np.all(np.isfinite(z)):
            raise ValueError("Strict overlap includes invalid LiDAR target support")
        maps = dict(nisar_maps)
        for name, band in NON_NISAR_BANDS.items():
            maps[name] = np.where(unwrap(ds, band + "_valid") == 1, unwrap(ds, band), np.nan)
        for pol in ("hh", "hv"):
            source_band = f"nisar_{pol.upper() * 2}_db_change"
            stored = np.where(unwrap(ds, source_band + "_valid") == 1, unwrap(ds, source_band), np.nan)
            if not np.allclose(maps[f"delta_{pol}_db"], stored, atol=1e-5, rtol=0, equal_nan=True):
                raise ValueError("Calibrated NISAR feature deltas do not match the verified cross-date bundle")
    _, y = frf_centers(grid)
    y = y[selected]
    fit = {model: np.column_stack([maps[name][selected] for name in features]) for model, features in MODELS.items()}
    if not all(np.all(np.isfinite(v)) for v in fit.values()):
        raise ValueError("A feature is missing on the published strict overlap mask")
    predictions, strips = heldout_predictions(fit, z, y)
    scores = {name: error_metrics(v, z) for name, v in predictions.items()}
    change = scores["C"]["rmse_m"] - scores["B"]["rmse_m"]
    examples = [
        {"row": int(r), "column": int(c), "frf_y_m": float(y[i]), "measured_change_m": float(z[i]),
         "predictions_m": {k: float(v[i]) for k, v in predictions.items()}}
        for i, (r, c) in enumerate(np.argwhere(selected))
    ]
    return {
        "status": "exploratory", "n": n, "units": "m", "vertical_datum": "NAVD88 (geoid12b)",
        "scientific_target": TARGET, "method": "training-standardized ridge regression with an unpenalized intercept",
        "validation": {
            "scope": "One June–October change interval, alongshore-held-out predictions",
            "outer": "leave one complete FRF alongshore strip out",
            "inner": "buffered leave-one-strip-out within the outer training set; lowest pooled squared error",
            "strip_width_m": STRIP_M, "strip_origin_frf_m": STRIP_ORIGIN_M, "strip_count": len(strips),
            "guard_m": BUFFER_M, "candidate_alphas": ALPHAS,
            "feature_filtering": "No spatial feature smoothing or texture; 30 m guard exceeds 20 m SWIR posting and Sentinel-1 nominal resolution",
        },
        "features": MODELS, "metrics": scores, "per_strip": strips,
        "ablation": {
            "C_minus_B_rmse_m": change,
            "C_minus_B_rmse_percent": 100 * change / scores["B"]["rmse_m"] if scores["B"]["rmse_m"] > 0 else None,
            "C_minus_B_mae_m": scores["C"]["mae_m"] - scores["B"]["mae_m"],
            "strips_with_lower_rmse_for_C": sum(s["C_minus_B_rmse_m"] < 0 for s in strips),
        },
        "terrain_model_deployment": {
            "status": "withheld",
            "reason": "Full model increased blocked error" if change > 0 else "An independent temporal evaluation is needed",
        },
        "classification": {
            "status": "withheld", "lod95_m": None,
            "reason": "Verified pixel-level paired and registration uncertainty is unavailable",
            "negative_observed_cells": int((z < 0).sum()), "positive_observed_cells": int((z > 0).sum()),
        },
        "samples": examples,
    }
