"""POLTERGEIST local data API using the checked-in verified and unified handoff bundles."""

from functools import lru_cache
import logging
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from .catalog import Catalog, read_json
from .environment import Environment
from .raster import render

ROOT = Path(__file__).resolve().parents[1]
CACHE = {"Cache-Control": "public, max-age=300"}


def create_app(root=None, unified_root=None):
    data = Path(root or os.getenv("POLTERGEIST_DATA_DIR", ROOT / "data/processed/verified"))
    if unified_root is not None:
        unified_data = Path(unified_root)
    elif root is not None:
        unified_data = Path(root) / "unified"
    else:
        unified_data = Path(os.getenv("POLTERGEIST_UNIFIED_DATA_DIR", data / "unified"))
    catalog = Catalog(data, unified_root=unified_data)
    env = Environment()
    app = FastAPI(title="POLTERGEIST", version="1.0")
    origins = os.getenv("POLTERGEIST_CORS_ORIGINS",
                        "http://localhost:5173,http://localhost:4173,http://127.0.0.1:5173,http://127.0.0.1:4173")
    app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in origins.split(",")],
                       allow_methods=["GET"], allow_headers=["Accept"])

    @app.exception_handler(StarletteHTTPException)
    async def problem(_request: Request, exc):
        return JSONResponse(status_code=exc.status_code, media_type="application/problem+json",
                            content={"title": "Request failed", "status": exc.status_code, "detail": exc.detail})

    @app.exception_handler(Exception)
    async def internal_error(_request: Request, exc):
        logging.getLogger(__name__).error("API failure (%s)", type(exc).__name__)
        return JSONResponse(status_code=500, media_type="application/problem+json",
                            content={"title": "Internal server error", "status": 500,
                                     "detail": "The product could not be served"})

    @app.get("/api/study-area")
    def study():
        return catalog.study()

    @app.get("/api/acquisitions")
    def acquisitions(group: str = None, sensor: str = None):
        items = sorted(catalog.acquisitions, key=lambda a: a["acquired_at"])
        if group:
            items = [a for a in items if a.get("group") == group]
        if sensor:
            items = [a for a in items if a.get("sensor") == sensor.upper()]
        return items

    @app.get("/api/layers")
    def layers():
        return JSONResponse([d for _, d in catalog.layers.values()], headers=CACHE)

    @app.get("/api/coastal/observations")
    def coastal_observations(include_samples: bool = False):
        return JSONResponse(catalog.coastal.summary(include_samples=include_samples), headers=CACHE)

    @app.get("/api/terrain/change")
    def terrain():
        return catalog.terrain()

    @app.get("/api/comparisons/pairs")
    def comparison_pairs():
        return JSONResponse(catalog.comparisons(), headers=CACHE)

    @app.get("/api/transects")
    def transects():
        return {"type": "FeatureCollection", "features": [f for f, *_ in catalog.transects.values()]}

    @app.get("/api/transects/observations.geojson")
    def observed_segments():
        return read_json(data / "lidar/transects.geojson") or {"type": "FeatureCollection", "features": []}

    @app.get("/api/transects/{id}")
    def transect(id: str):
        if id not in catalog.transects:
            raise HTTPException(404, "Unknown transect")
        feature, profiles, boundaries, result = catalog.transects[id]
        return {**feature, "profiles": profiles, "boundaries": boundaries,
                "measured_change": result["coastal_observations"]["terrain"]}

    @app.get("/api/analysis/{id}")
    def analysis(id: str):
        if id not in catalog.transects:
            raise HTTPException(404, "Unknown transect")
        _, _, _, result = catalog.transects[id]
        return result

    @app.get("/api/boundaries/{id}.geojson")
    def boundary_geojson(id: str):
        if id in catalog.coastal.layers:
            return JSONResponse(catalog.coastal.layers[id], headers=CACHE)
        if id not in catalog.reconstruction.boundary_geojson:
            raise HTTPException(404, "Unknown boundary layer")
        return JSONResponse(catalog.reconstruction.boundary_geojson[id], headers=CACHE)

    @app.get("/api/environment/latest")
    def environment():
        return JSONResponse(env.latest(), headers={"Cache-Control": "public, max-age=30"})

    @app.get("/api/environment/acquisitions")
    def acquisition_environments(group: str = None):
        if not catalog.acq_environment:
            return {"status": "unavailable", "reason": "Unified environmental dataset is unavailable"}
        records = [
            {
                "id": a["id"],
                "sensor": a["sensor"],
                "acquired_at": a["acquired_at"],
                "group": a.get("group"),
                "summary": catalog.acq_environment.get(a["id"], {}).get("summary"),
                "tide_stage": catalog.acq_environment.get(a["id"], {}).get("tide_stage"),
            }
            for a in sorted(catalog.acquisitions, key=lambda x: x["acquired_at"])
            if not group or a.get("group") == group
        ]
        return JSONResponse(
            {
                "acquisitions": records,
                "cross_date_contrasts": catalog.cross_date_environment,
                "qa": catalog.environment_qa,
            },
            headers=CACHE,
        )

    @app.get("/api/environment/acquisitions/{id:path}")
    def acquisition_environment_detail(id: str):
        target = id
        if target not in catalog.acq_environment:
            matches = [k for k in catalog.acq_environment if k.startswith(target + "#")]
            if len(matches) == 1:
                target = matches[0]
            else:
                raise HTTPException(404, "Unknown acquisition ID")
        return JSONResponse(catalog.acq_environment[target], headers=CACHE)

    @app.get("/api/tiles/{id}/{z}/{x}/{y}.png")
    def tiles(id: str, z: int, x: int, y: int):
        if id not in catalog.layers or not 0 <= z <= 22 or not (0 <= x < 1 << z and 0 <= y < 1 << z):
            raise HTTPException(404, "Unknown tile")
        path, info = catalog.layers[id]
        if path is None:
            raise HTTPException(404, "Unknown tile")
        band = catalog.layer_bands.get(id, 1)
        try:
            blob = cached_render(str(path), id, z, x, y, band)
        except Exception as exc:
            logging.getLogger(__name__).warning("Tile %s unavailable (%s)", id, type(exc).__name__)
            raise HTTPException(503, "Raster tile temporarily unavailable") from None
        return Response(blob, media_type="image/png", headers=CACHE)

    # Resolve tile parameters against the server-owned catalog before any file or network read.
    cached_render = lru_cache(maxsize=256)(
        lambda path, id, z, x, y, band=1: render(path, catalog.layers[id][1], z, x, y, band=band)
    )

    @app.get("/api/rasters/{id}.tif")
    def cog(id: str):
        if id not in catalog.layers:
            raise HTTPException(404, "Unknown raster")
        path, _ = catalog.layers[id]
        if path is None:
            raise HTTPException(404, "Unknown raster")
        return FileResponse(path, media_type="image/tiff", filename=path.name, headers=CACHE)

    return app


app = create_app()
