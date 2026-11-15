"""Presentation graphs (Plotly -> PNG + HTML). Every number plotted comes from
outputs/*.csv produced by score.py / lidar_boundaries.py."""
import os
from pathlib import Path
import time
try:  # one persistent renderer for all figures (reduces kaleido's startup race)
    import kaleido
    kaleido.start_sync_server(silence_warnings=True)
except Exception:
    pass
import numpy as np
import pandas as pd
import xarray as xr
import plotly.graph_objects as go
from plotly.subplots import make_subplots

ROOT = Path(__file__).resolve().parents[1]
OUT, PROC = ROOT / "outputs", ROOT / "data" / "processed"
FIG = OUT / "figures"
FIG.mkdir(parents=True, exist_ok=True)

C = {"S2_NDWI": "#0e7490", "S2_MNDWI": "#67e8f9", "EXP_tideaware_S2": "#155e75",
     "S1_VV": "#b45309", "S1_VH": "#fbbf24", "NISAR_HH": "#7c3aed", "NISAR_HV": "#c4b5fd",
     "EXP_radar_S1VV+NISARHH": "#4c1d95", "ABL_radar_S1VV_only": "#92400e"}
LABEL = {"S2_NDWI": "Sentinel-2 NDWI", "S2_MNDWI": "Sentinel-2 MNDWI",
         "EXP_tideaware_S2": "S2 NDWI + tide correction (experimental)",
         "S1_VV": "Sentinel-1 VV", "S1_VH": "Sentinel-1 VH", "NISAR_HH": "NISAR HH",
         "NISAR_HV": "NISAR HV", "EXP_radar_S1VV+NISARHH": "S1 VV + NISAR HH (experimental)",
         "ABL_radar_S1VV_only": "Ablation: without NISAR (S1 VV only)"}
BNAME = {"B1_wetdry": "lidar wet/dry edge", "B2_dunetoe": "lidar dune toe",
         "B3_contour": "lidar fixed contour"}  # replaced in main() with the value from the data
PAIRS = [  # (product, the lidar boundary it physically corresponds to)
    ("S2_NDWI", "B1_wetdry"), ("S2_MNDWI", "B1_wetdry"), ("EXP_tideaware_S2", "B1_wetdry"),
    ("NISAR_HH", "B2_dunetoe"), ("NISAR_HV", "B2_dunetoe"), ("S1_VV", "B2_dunetoe"),
    ("S1_VH", "B2_dunetoe"), ("EXP_radar_S1VV+NISARHH", "B2_dunetoe"), ("ABL_radar_S1VV_only", "B2_dunetoe")]
LAYOUT = dict(template="plotly_white", font=dict(size=16, family="Arial"),
              margin=dict(l=80, r=40, t=90, b=70))


def save(fig, name):
    fig.write_html(FIG / f"{name}.html", include_plotlyjs="cdn")
    if os.getenv("SARS_SKIP_PNG") == "1":
        return
    for attempt in range(8):
        try:
            fig.write_image(FIG / f"{name}.png", scale=2)
            break
        except Exception as e:  # kaleido has a known startup race ("kaleido_scopes is not defined"); retry
            err = e
            time.sleep(1 + attempt)
    else:
        raise err
    print("saved", name)


def fig_offset_alongshore(sb, lidar):
    fig = make_subplots(rows=1, cols=2, shared_yaxes=True, horizontal_spacing=0.06,
                        subplot_titles=["Water sensors vs lidar wet/dry edge",
                                        "Radar sensors vs lidar dune toe"])
    for col, (prods, tgt) in enumerate([(["S2_NDWI", "EXP_tideaware_S2"], "B1_wetdry"),
                                        (["S1_VV", "S1_VH", "NISAR_HH", "NISAR_HV"], "B2_dunetoe")], 1):
        pix = sb[sb["product"].isin(prods)].pixel_spacing_m.max()  # from product metadata
        fig.add_hrect(y0=-pix, y1=pix, fillcolor="#9ca3af", opacity=0.25, line_width=0, layer="below",
                      row=1, col=col, exclude_empty_subplots=False)
        fig.add_annotation(x=1185, y=pix, text=f"±1 pixel ({pix:.0f} m)", showarrow=False, yanchor="bottom",
                           xanchor="right", font=dict(size=12, color="#6b7280"), row=1, col=col)
        for p in prods:
            s = sb[sb["product"] == p]
            if s.empty:
                continue
            j = s.merge(lidar[["date", "y", tgt]], on=["date", "y"])
            j["err"] = j.boundary_x - j[tgt]
            g = j.groupby("y").err.median()
            fig.add_scatter(x=g.index, y=g.values, mode="lines+markers", name=LABEL[p],
                            line=dict(color=C[p], width=3), row=1, col=col)
    fig.update_xaxes(title="alongshore position y (m, FRF)")
    fig.update_yaxes(title="sensor − lidar (m)<br>+ = sensor further seaward", row=1, col=1)
    fig.update_layout(**LAYOUT, height=560, width=1300,
                      title="Where along the beach does each sensor miss? (median over dates; grey band = ±1 pixel)")
    save(fig, "fig_offset_alongshore")


def fig_scorecard(M):
    P = M[M.date == "pooled"]
    rows = []
    for p, tgt in PAIRS:
        r = P[(P["product"] == p) & (P.lidar_boundary == tgt)]
        if r.empty or not np.isfinite(r.RMSE_m.item()):
            continue
        if p == "ABL_radar_S1VV_only" and "NISAR_HH" not in set(P["product"]):
            continue  # ablation is only meaningful once NISAR is in the comparison
        rows.append(r.iloc[0])
    D = pd.DataFrame(rows)
    D["label"] = [f"{LABEL[p]}<br><sub>vs {BNAME[t]} · N={n}</sub>" for p, t, n in zip(D["product"], D.lidar_boundary, D.N)]
    fig = go.Figure(go.Bar(
        y=D.label, x=D.RMSE_m, orientation="h", marker_color=[C[p] for p in D["product"]], showlegend=False,
        error_x=dict(type="data", symmetric=False, array=D.RMSE_hi - D.RMSE_m,
                     arrayminus=D.RMSE_m - D.RMSE_lo, color="#111827", thickness=2),
        text=[f"<b>{v:.1f} m</b>" for v in D.RMSE_m], textposition="inside", insidetextanchor="start",
        textfont=dict(color="white")))
    fig.add_scatter(y=D.label, x=D.pixel_m, mode="markers", name="1 pixel of that sensor",
                    marker=dict(symbol="line-ns", size=34, line=dict(width=3, color="#6b7280")))
    fig.update_layout(**LAYOUT, height=160 + 70 * len(D), width=1250, showlegend=True,
                      legend=dict(orientation="h", y=-0.12, x=0),
                      title="Scorecard: typical boundary error (RMSE, 95% block-bootstrap interval)",
                      xaxis_title="RMSE (m) — lower is better", yaxis=dict(autorange="reversed"))
    save(fig, "fig_scorecard")


def fig_cross_section(sb, lidar, y_pref=950):
    # use the row nearest y_pref where the dune toe and wet/dry edge exist on both dates
    w = lidar[lidar.date.isin(["2026-06", "2026-10"])].groupby("y")[["B1_wetdry", "B2_dunetoe"]].count()
    ok = w[(w >= 2).all(axis=1)].index.to_numpy()
    y0 = int(ok[np.argmin(np.abs(ok - y_pref))]) if len(ok) else y_pref
    ds = xr.open_dataset(PROC / "lidar_scans.nc")
    x = ds.xFRF.values
    fig = go.Figure()
    zj = ds.elevation.sel(date="2026-06").sel(yFRF=slice(y0 - 5, y0 + 4)).median("yFRF").values
    zo = ds.elevation.sel(date="2026-10").sel(yFRF=slice(y0 - 5, y0 + 4)).median("yFRF").values
    fig.add_scatter(x=x, y=zj, name="Lidar June 19", line=dict(color="#2563eb", width=4))
    fig.add_scatter(x=x, y=zo, name="Lidar Oct 16", line=dict(color="#dc2626", width=4),
                    fill="tonexty", fillcolor="rgba(220,38,38,0.12)")
    L = lidar[lidar.y == y0].set_index("date")
    ymax = np.nanmax([np.nanmax(zj), np.nanmax(zo)])
    for d, dash in [("2026-06", "dot"), ("2026-10", "solid")]:
        for b, sym in [("B1_wetdry", "triangle-down"), ("B2_dunetoe", "circle")]:
            v = L.loc[d, b] if d in L.index else np.nan
            if np.isfinite(v):
                fig.add_scatter(x=[v], y=[np.interp(v, x[np.isfinite(zo if d == '2026-10' else zj)],
                                                    (zo if d == '2026-10' else zj)[np.isfinite(zo if d == '2026-10' else zj)])],
                                mode="markers", marker=dict(size=14, symbol=sym, color="#111827"),
                                name=f"{BNAME[b]} ({d})", showlegend=True)
    for p in ["S2_NDWI", "S1_VV", "NISAR_HH"]:
        for d, dash in [("2026-06", "dot"), ("2026-10", "solid")]:
            s = sb[(sb["product"] == p) & (sb.date == d) & (sb.y == y0)]
            if s.empty or not np.isfinite(s.boundary_x.item()):
                continue
            fig.add_vline(x=s.boundary_x.item(), line=dict(color=C[p], dash=dash, width=3))
            fig.add_scatter(x=[None], y=[None], mode="lines", line=dict(color=C[p], dash=dash, width=3),
                            name=f"{LABEL[p]} edge ({d})")
    fig.update_layout(**LAYOUT, height=620, width=1300,
                      title=f"One cross-section (y = {y0} m): each sensor marks a different feature",
                      xaxis=dict(title="cross-shore distance x (m, FRF) → toward the ocean", range=[40, 130]),
                      yaxis_title="elevation (m, NAVD88)")
    fig.add_annotation(x=0.99, y=0.97, xref="paper", yref="paper", showarrow=False, align="right",
                       text="shaded = beach lowering June → Oct", font=dict(color="#dc2626"))
    save(fig, "fig_cross_section")


def fig_matrix(M):
    P = M[M.date == "pooled"]
    prods = [p for p in ["S2_NDWI", "S2_MNDWI", "S1_VV", "S1_VH", "NISAR_HH", "NISAR_HV"] if p in set(P["product"])]
    Z = P.pivot(index="product", columns="lidar_boundary", values="RMSE_m").loc[prods, list(BNAME)]
    fig = go.Figure(go.Heatmap(z=Z.values, x=[BNAME[c] for c in Z.columns], y=[LABEL[p] for p in Z.index],
                               colorscale="Blues_r", text=np.round(Z.values, 1), texttemplate="%{text} m",
                               colorbar=dict(title="RMSE (m)")))
    fig.update_layout(**LAYOUT, height=150 + 70 * len(prods), width=1000,
                      title="Which lidar feature does each sensor match? (pooled RMSE, all available rows; lower = closer)")
    save(fig, "fig_matrix")


def main():
    sb = pd.read_csv(OUT / "sensor_boundaries.csv")
    lidar = pd.read_csv(OUT / "lidar_boundaries.csv")
    BNAME["B3_contour"] = f"lidar {lidar.B3_contour_z.iloc[0]:.1f} m contour"  # from data, not typed
    M = pd.read_csv(OUT / "metrics.csv")
    fig_offset_alongshore(sb, lidar)
    fig_scorecard(M)
    fig_cross_section(sb, lidar)
    fig_matrix(M)


if __name__ == "__main__":
    main()
