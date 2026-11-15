"""Build a conservative, feature-separated coastal state from satellite observations.

The waterline remains the validated Sentinel-2 NDWI estimate. The dune-toe
estimate uses robust generalized-Bayesian fusion of Sentinel-1 VV and VH.

Important scientific safeguards:
- LiDAR boundaries are validation-only and NEVER enter the estimates.
- VV and VH are correlated observations from the same Sentinel-1 acquisition.
  Their likelihood contributions are therefore tempered (power 0.5 each) rather
  than treated as two independent measurements. This is a conservative
  composite-likelihood approximation, not a fitted correlation model.
- Each radar observation uses a Student-t inlier likelihood plus a small
  uniform outlier component, reducing the influence of anomalous transitions.
- If VV and VH disagree beyond a threshold based on their CV error scales, the
  algorithm withholds a single fused point estimate and flags the location.
- CV RMSE is used as a likelihood scale, not claimed to be a calibrated
  Gaussian standard deviation.

Run from repository root:
    python src/reconstruct.py
"""
from pathlib import Path
from math import lgamma, log

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
SENSOR_FILE = OUT / "sensor_boundaries.csv"
METRICS_FILE = OUT / "metrics.csv"
LIDAR_FILE = OUT / "lidar_boundaries.csv"
OUTPUT_FILE = OUT / "reconstructed_state.csv"

WATER_PRODUCT = "S2_NDWI"
EXPERIMENTAL_WATER_PRODUCT = "EXP_tideaware_S2"
DUNE_PRODUCTS = ("S1_VV", "S1_VH")

# Cross-shore search domain used by the existing boundary-extraction analysis.
X_MIN_M = 20.0
X_MAX_M = 150.0
GRID_STEP_M = 0.1

# Robust observation model. The outlier component is uniform over the
# evaluated cross-shore domain; Student-t tails are heavier than Gaussian.
STUDENT_T_DF = 4.0
OUTLIER_FRACTION = 0.05

# A disagreement must exceed both a minimum practical separation and a
# two-error-scale criterion before a fused point estimate is withheld.
MIN_DISAGREEMENT_M = 15.0
DISAGREEMENT_ERROR_MULTIPLIER = 2.0


def rmse_lookup(metrics):
    """Return date-specific cross-validated RMSEs, excluding pooled rows."""
    required = {"product", "lidar_boundary", "date", "RMSE_m"}
    missing = required - set(metrics.columns)
    if missing:
        raise ValueError(f"metrics.csv missing columns: {sorted(missing)}")
    m = metrics[metrics.date != "pooled"]
    return {
        (r.product, r.lidar_boundary, r.date): float(r.RMSE_m)
        for r in m.itertuples()
        if np.isfinite(r.RMSE_m) and r.RMSE_m > 0
    }


def _student_t_logpdf(x, location, scale, degrees_of_freedom):
    """Student-t log probability density, evaluated without SciPy."""
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
    """Student-t inlier likelihood mixed with a uniform outlier likelihood."""
    inlier = _student_t_logpdf(
        grid, observed_x, cv_rmse, STUDENT_T_DF
    )
    outlier = -log(X_MAX_M - X_MIN_M)
    a = np.log1p(-OUTLIER_FRACTION) + inlier
    b = log(OUTLIER_FRACTION) + outlier
    return np.logaddexp(a, b)


def bayesian_dune_estimate(vv, vh, sv, sh):
    """Return robust posterior diagnostics and an accepted point estimate.

    With two valid polarizations, each log-likelihood is raised to power 0.5.
    This generalized-Bayes tempering is a conservative way to avoid counting
    same-acquisition VV/VH as independent evidence when their correlation has
    not been estimated from independent data.
    """
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
        log_posterior += power * _robust_observation_loglikelihood(
            grid, observed_x, scale
        )

    # Uniform prior over the stated cross-shore search domain.
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
    posterior_sd = float(np.sqrt(np.sum(
        np.square(grid - posterior_mean) * posterior
    )))

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

    # A boundary mode at the edge of the search domain is not accepted as a
    # reliable location because the posterior may be truncated by the domain.
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


def main():
    for f in (SENSOR_FILE, METRICS_FILE, LIDAR_FILE):
        if not f.exists():
            raise FileNotFoundError(f"Required input not found: {f}")

    sensors = pd.read_csv(SENSOR_FILE)
    metrics = pd.read_csv(METRICS_FILE)
    lidar = pd.read_csv(LIDAR_FILE)
    rmse = rmse_lookup(metrics)

    keys = ["date", "y"]
    base = sensors[keys].drop_duplicates().sort_values(keys).reset_index(drop=True)
    wide = sensors.pivot_table(
        index=keys, columns="product", values="boundary_x", aggfunc="first"
    ).reset_index()
    state = base.merge(wide, on=keys, how="left")

    # Waterline: retain the established Sentinel-2 NDWI estimate unchanged.
    state["waterline_x_m"] = (
        state[WATER_PRODUCT] if WATER_PRODUCT in state else np.nan
    )
    state["waterline_cv_rmse_m"] = [
        rmse.get((WATER_PRODUCT, "B1_wetdry", d), np.nan)
        for d in state.date
    ]
    state["waterline_source"] = np.where(
        state.waterline_x_m.notna(), "Sentinel-2 NDWI", "missing"
    )

    # Keep tide-aware NDWI as a separately labelled experimental alternative.
    state["waterline_tideaware_experimental_x_m"] = (
        state[EXPERIMENTAL_WATER_PRODUCT]
        if EXPERIMENTAL_WATER_PRODUCT in state else np.nan
    )
    state["waterline_tideaware_cv_rmse_m"] = [
        rmse.get((EXPERIMENTAL_WATER_PRODUCT, "B1_wetdry", d), np.nan)
        for d in state.date
    ]

    # Robust generalized-Bayesian fusion for the dune-toe feature.
    results = []
    conservative_scales = []
    baseline_estimates = []
    for r in state.itertuples():
        vv = getattr(r, "S1_VV", np.nan)
        vh = getattr(r, "S1_VH", np.nan)
        sv = rmse.get(("S1_VV", "B2_dunetoe", r.date), np.nan)
        sh = rmse.get(("S1_VH", "B2_dunetoe", r.date), np.nan)
        results.append(bayesian_dune_estimate(vv, vh, sv, sh))
        # Retain v1's inverse-variance weighted estimate as a direct baseline.
        valid = [(x, s) for x, s in ((vv, sv), (vh, sh))
                 if np.isfinite(x) and np.isfinite(s) and s > 0]
        if valid:
            weights = np.array([1.0 / (s * s) for _, s in valid])
            positions = np.array([x for x, _ in valid])
            baseline_estimates.append(float(np.sum(weights * positions) / weights.sum()))
        else:
            baseline_estimates.append(np.nan)
        valid_scales = [
            scale for value, scale in ((vv, sv), (vh, sh))
            if np.isfinite(value) and np.isfinite(scale) and scale > 0
        ]
        conservative_scales.append(
            max(valid_scales) if valid_scales else np.nan
        )

    # Only accepted estimates populate dunetoe_x_m. Ambiguous rows retain
    # their posterior diagnostics but do not receive a misleading midpoint.
    state["dunetoe_x_m"] = [r["accepted_x"] for r in results]
    state["dunetoe_baseline_weighted_x_m"] = baseline_estimates
    state["dunetoe_bayes_map_x_m"] = [r["map_x"] for r in results]
    state["dunetoe_bayes_median_x_m"] = [r["median_x"] for r in results]
    state["dunetoe_bayes_ci90_low_m"] = [r["ci90_low"] for r in results]
    state["dunetoe_bayes_ci90_high_m"] = [r["ci90_high"] for r in results]
    state["dunetoe_bayes_posterior_sd_m"] = [
        r["posterior_sd"] for r in results
    ]
    state["dunetoe_vv_vh_disagreement_m"] = [
        r["disagreement"] for r in results
    ]
    state["dunetoe_vv_vh_disagreement_limit_m"] = [
        r["disagreement_limit"] for r in results
    ]
    state["dunetoe_likelihood_power_vv"] = [
        r["power_vv"] for r in results
    ]
    state["dunetoe_likelihood_power_vh"] = [
        r["power_vh"] for r in results
    ]
    state["dunetoe_cv_rmse_conservative_m"] = conservative_scales
    state["dunetoe_source"] = [
        "Sentinel-1 robust Bayesian fusion"
        if "VV/VH fusion" in r["status"]
        else ("Sentinel-1 Bayesian single-polarization"
              if "single-polarization" in r["status"]
              else "Sentinel-1 observations; estimate withheld")
        for r in results
    ]
    state["dunetoe_status"] = [r["status"] for r in results]

    # Preserve raw radar transitions for audit and diagnosis.
    state["radar_transition_vv_x_m"] = (
        state["S1_VV"] if "S1_VV" in state else np.nan
    )
    state["radar_transition_vh_x_m"] = (
        state["S1_VH"] if "S1_VH" in state else np.nan
    )

    # LiDAR is appended only as an independent validation reference.
    refs = lidar[keys + ["B1_wetdry", "B2_dunetoe", "B3_contour"]].copy()
    refs = refs.rename(columns={
        "B1_wetdry": "validation_lidar_wetdry_x_m",
        "B2_dunetoe": "validation_lidar_dunetoe_x_m",
        "B3_contour": "validation_lidar_1p5m_contour_x_m",
    })
    state = state.merge(refs, on=keys, how="left")

    # Final independent comparison against LiDAR. These references are used
    # only after predictions have been generated, to score rather than fit.
    truth = state["validation_lidar_dunetoe_x_m"]
    bayes_valid = state["dunetoe_x_m"].notna() & truth.notna()
    baseline_valid = state["dunetoe_baseline_weighted_x_m"].notna() & truth.notna()

    def error_metrics(label, prediction, valid_mask):
        errors = prediction[valid_mask] - truth[valid_mask]
        if len(errors) == 0:
            return {"method": label, "N": 0, "bias_m": np.nan,
                    "MAE_m": np.nan, "RMSE_m": np.nan}
        return {
            "method": label,
            "N": int(len(errors)),
            "bias_m": float(errors.mean()),
            "MAE_m": float(errors.abs().mean()),
            "RMSE_m": float(np.sqrt(np.mean(np.square(errors)))),
        }

    reconstruction_metrics = pd.DataFrame([
        error_metrics("v1_inverse_variance_baseline_all_matched",
                      state["dunetoe_baseline_weighted_x_m"], baseline_valid),
        error_metrics("v1_baseline_on_bayesian_accepted_rows",
                      state["dunetoe_baseline_weighted_x_m"], bayes_valid),
        error_metrics("robust_generalized_bayesian_accepted_rows",
                      state["dunetoe_x_m"], bayes_valid),
    ])
    reconstruction_metrics.to_csv(
        OUT / "reconstruction_metrics.csv", index=False, float_format="%.3f"
    )

    state["state_scope"] = (
        "observed boundary features; not full terrain or bathymetry"
    )
    state["waterline_status"] = np.where(
        state.waterline_x_m.notna(),
        "plausible; date-specific spatial-CV error scale",
        "not estimated",
    )

    state.to_csv(OUTPUT_FILE, index=False, float_format="%.3f")
    print(f"Wrote {OUTPUT_FILE}")
    print(f"Rows: {len(state)}")
    print("Waterline estimates:", int(state.waterline_x_m.notna().sum()))
    print("Accepted Bayesian dune-toe estimates:",
          int(state.dunetoe_x_m.notna().sum()))
    print("Ambiguous radar disagreements:",
          int(state.dunetoe_status.str.startswith("ambiguous").sum()))
    print("Independent dune-toe validation (LiDAR used for scoring only):")
    print(reconstruction_metrics.to_string(index=False))
    print("Saved outputs/reconstruction_metrics.csv")
    print("LiDAR references are validation-only; not used in estimates.")


if __name__ == "__main__":
    main()
