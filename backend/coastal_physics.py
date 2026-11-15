"""Geometry and quality checks for Duck optical waterline normalization."""

from datetime import datetime
import json
import re
from math import cos, hypot, isfinite, pi, radians, sin, sinh, sqrt, tanh

G = 9.81
NOAA_STATION = "NOAA CO-OPS 8651370"
DATUM_SOURCE = "https://tidesandcurrents.noaa.gov/benchmarks/8651370.html"
# Published FRF station datums, in metres above MLLW, tidal epoch 1983–2001.
DUCK_DATUMS = {"MLLW": 0.0, "NAVD88": 0.667, "NAVD88 (geoid12b)": 0.667}
MHW_MLLW_M = 1.026
MHW = {
    "value": MHW_MLLW_M - DUCK_DATUMS["NAVD88"], "unit": "m", "vertical_datum": "NAVD88",
    "station_id": NOAA_STATION, "source": DATUM_SOURCE, "description": "NOAA mean high water (1983–2001)",
}
WAVE_STATION = "USACE FRF Waverider 17m"
WAVE_DEPTH_M = 17.4
FRF_NORMAL_DEG = 71.8


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value)


def timestamp(value):
    try:
        result = datetime.fromisoformat(re.sub(r"(\.\d{6})\d+", r"\1", value.replace("Z", "+00:00")))
        return result if result.tzinfo is not None else None
    except (TypeError, ValueError, AttributeError):
        return None


def time_gap(left, right):
    a, b = timestamp(left), timestamp(right)
    return (a - b).total_seconds() if a is not None and b is not None else None


def qualified(row, unit, acquired_at):
    gap = time_gap(row.get("timestamp_utc"), acquired_at)
    limit = row.get("tolerance_minutes")
    return (row.get("unit") == unit and finite(row.get("value")) and finite(limit)
            and limit > 0 and gap is not None and abs(gap) <= limit * 60)


def quality_flags(row):
    try:
        value = json.loads(row.get("source_quality_json") or "{}")
        return value if isinstance(value, dict) else {}
    except (ValueError, TypeError):
        return {}


def water_level(rows, acquired_at):
    """Return qualified observed station level, retaining its measurement timestamp."""
    row = next((r for r in rows if r.get("station_id") == NOAA_STATION and r.get("variable") == "water_level"), {})
    flags = quality_flags(row)
    if (qualified(row, "m", acquired_at) and row.get("vertical_datum") in DUCK_DATUMS
            and flags.get("f") == "0,0,0,0" and flags.get("q") in ("v", "p")):
        return row
    return None


def setup_inputs(rows, acquired_at):
    fields = {"wave_significant_height": "m", "wave_peak_period": "s", "wave_peak_direction": "degree_true_from"}
    selected = {r["variable"]: r for r in rows if r["station_id"] == WAVE_STATION and r["variable"] in fields}
    if selected.keys() != fields.keys():
        return None
    for name, unit in fields.items():
        row = selected[name]
        flags = quality_flags(row)
        if not qualified(row, unit, acquired_at) or flags.get("qcFlagE") != 1 or flags.get("qcFlagD") != 1:
            return None
    if len({r["timestamp_utc"] for r in selected.values()}) != 1:
        return None
    return {"height_m": selected["wave_significant_height"]["value"],
            "period_s": selected["wave_peak_period"]["value"],
            "from_deg": selected["wave_peak_direction"]["value"],
            "observations": list(selected.values())}


def wave_geometry(height_m, period_s, from_deg):
    """Reverse shoal/refract the FRF buoy record using linear wave theory."""
    if not all(finite(v) for v in (height_m, period_s, from_deg)):
        return None
    if height_m <= 0 or period_s <= 0 or not 0 <= from_deg <= 360:
        return None
    omega = 2 * pi / period_s
    k0 = omega ** 2 / G
    angle = radians((from_deg - FRF_NORMAL_DEG + 180) % 360 - 180)
    if cos(angle) <= 0:
        return None
    # Solve omega²=gk tanh(kh) using bisection. At shallow-water kh, omega/sqrt(gh)
    # is a lower bound. Twice the sum of that and k0 is an upper bound.
    low, high = k0, 2 * (k0 + omega / sqrt(G * WAVE_DEPTH_M))
    for _ in range(50):
        k = (low + high) / 2
        if G * k * tanh(k * WAVE_DEPTH_M) < omega ** 2:
            low = k
        else:
            high = k
    kh = k * WAVE_DEPTH_M
    if height_m >= 0.78 * WAVE_DEPTH_M or height_m / (2 * pi / k) > 0.142 * tanh(kh):
        return None
    sin_deep_angle = k / k0 * sin(angle)
    if abs(sin_deep_angle) >= 1:
        return None
    group_ratio = (1 + (2 * kh / sinh(2 * kh) if kh < 300 else 0)) * k0 / k
    deep_height = height_m * sqrt(group_ratio * cos(angle) / sqrt(1 - sin_deep_angle ** 2))
    return {"deep_wave_height_m": deep_height, "deep_wavelength_m": 2 * pi / k0}


def withheld(reason):
    return {"status": "withheld", "reasons": [reason], "x_frf_m": None, "sigma_m": None,
            "slope_sensitivity_frf_m": None}


def correct_waterline(x, acquired_at, tide, reference, slope, *, wave=None, reference_wave=None, errors=None):
    """Normalize in seaward-positive FRF x. All vertical values must be metres."""
    if not finite(x):
        return withheld("No quality-screened optical crossing")
    if not tide or not water_level([tide], acquired_at):
        return withheld("No qualified observed Duck station water level at image acquisition")
    if (reference.get("unit") != "m" or not finite(reference.get("value"))
            or reference.get("station_id") != NOAA_STATION
            or reference.get("vertical_datum") not in DUCK_DATUMS or tide.get("vertical_datum") not in DUCK_DATUMS):
        return withheld("Reference and observed water level require verified Duck station datums and metre units")
    if slope is None or not finite(slope.get("slope_m_per_m")) or slope.get("slope_m_per_m") <= 0 or slope.get("units") != "m/m":
        return withheld("Independent positive foreshore slope in m/m is unavailable")
    gap = time_gap(acquired_at, slope.get("acquired_at"))
    if slope.get("coreg_qc_flag") != 1 or gap is None or not 0 < gap <= 7 * 86400:
        return withheld("Independent QC 1 slope survey must precede the image by no more than seven days")

    m = slope["slope_m_per_m"]
    # Express both elevations above station MLLW before taking the difference.
    eta = tide["value"] + DUCK_DATUMS[tide["vertical_datum"]]
    z_ref = reference["value"] + DUCK_DATUMS[reference["vertical_datum"]]
    tide_difference = eta - z_ref
    result = {"status": "conditional", "x_frf_m": x + tide_difference / m, "shift_m": tide_difference / m,
              "sigma_m": None, "slope_sensitivity_frf_m": None,
              "reasons": ["The Duck pier gauge represents water level along the beach and a planar slope is assumed"],
              "tide": tide, "reference": reference, "slope": slope}
    if errors is not None and wave is None and reference_wave is None:
        names = ("extract_m", "tide_m", "slope_m_per_m", "registration_m")
        if all(finite(errors.get(k)) and errors[k] >= 0 for k in names):
            result["sigma_m"] = hypot(errors["extract_m"], errors["tide_m"] / m,
                                      tide_difference * errors["slope_m_per_m"] / m**2,
                                      errors["registration_m"])
            result["uncertainty_method"] = "first-order propagation of independent one-sigma errors"
    adjustment = 0.0
    if wave is not None:
        adjustment = 0.35 * sqrt(wave["deep_wave_height_m"] * wave["deep_wavelength_m"])
        if reference_wave is not None:
            adjustment -= 0.35 * sqrt(reference_wave["deep_wave_height_m"] * reference_wave["deep_wavelength_m"])
        result.update({"x_frf_m": result["x_frf_m"] + adjustment, "shift_m": result["shift_m"] + adjustment,
                       "setup_m": adjustment * m, "wave": wave, "reference_wave": reference_wave})
        result["reasons"].append("Experimental difference in mean wave setup from reverse-transformed buoy observations")
    interval = slope.get("slope_p10_p90_m_per_m")
    if interval and len(interval) == 2 and all(finite(v) and v > 0 for v in interval) and interval[0] <= m <= interval[1]:
        result["slope_sensitivity_frf_m"] = sorted(x + tide_difference / v + adjustment for v in interval)
    if result["sigma_m"] is None:
        result["reasons"].append("Complete independent one-sigma errors unavailable")
    if quality_flags(tide).get("q") == "p":
        result["reasons"].append("NOAA station water level is preliminary")
    return result
