"""POLTERGEIST local data API using the checked-in verified handoff bundles."""

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
from .science import Science
from .raster import render

ROOT = Path(__file__).resolve().parents[1]
CACHE = {"Cache-Control": "public, max-age=300"}


def create_app(root=None, science_root=None):
    data = Path(root or os.getenv("POLTERGEIST_DATA_DIR", ROOT / "data/processed/verified"))
    catalog = Catalog(data)
    env = Environment()
    science = Science(Path(science_root or ROOT))
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
    def acquisitions():
        return sorted({a["id"]: a for a in [*science.acquisitions(), *catalog.acquisitions]}.values(),
                      key=lambda a: a["acquired_at"])

    @app.get("/api/layers")
    def layers():
        return JSONResponse([d for _, d in catalog.layers.values()], headers=CACHE)

    @app.get("/api/terrain/change")
    def terrain():
        return catalog.terrain()

    @app.get("/api/transects")
    def transects():
        return {"type": "FeatureCollection", "features": [f for f, _ in catalog.transects.values()]}

    @app.get("/api/transects/observations.geojson")
    def observed_segments():
        return read_json(data / "lidar/transects.geojson") or {"type": "FeatureCollection", "features": []}

    @app.get("/api/transects/{id}")
    def transect(id: str):
        if id not in catalog.transects:
            raise HTTPException(404, "Unknown transect")
        feature, profiles = catalog.transects[id]
        return {**feature, "profiles": profiles, "boundaries": []}

    @app.get("/api/analysis/{id}")
    def analysis(id: str):
        if id not in catalog.transects:
            raise HTTPException(404, "Unknown transect")
        return {"status": "unavailable", "reason": "Physics-informed profiles are awaiting data"}

    @app.get("/api/boundary-analysis/{id}")
    def boundary_analysis(id: str):
        if id not in catalog.transects:
            raise HTTPException(404, "Unknown transect")
        return science.analysis(catalog.transects[id][0])

    @app.get("/api/environment/latest")
    def environment():
        return JSONResponse(env.latest(), headers={"Cache-Control": "public, max-age=30"})

    @app.get("/api/tiles/{id}/{z}/{x}/{y}.png")
    def tiles(id: str, z: int, x: int, y: int):
        if id not in catalog.layers or not 0 <= z <= 22 or not (0 <= x < 1 << z and 0 <= y < 1 << z):
            raise HTTPException(404, "Unknown tile")
        path, info = catalog.layers[id]
        try:
            blob = cached_render(str(path), id, z, x, y)
        except Exception as exc:
            logging.getLogger(__name__).warning("Tile %s unavailable (%s)", id, type(exc).__name__)
            raise HTTPException(503, "Raster tile temporarily unavailable") from None
        return Response(blob, media_type="image/png", headers=CACHE)

    # Resolve tile parameters against the server-owned catalog before any file or network read.
    cached_render = lru_cache(maxsize=256)(
        lambda path, id, z, x, y: render(path, catalog.layers[id][1], z, x, y)
    )

    @app.get("/api/rasters/{id}.tif")
    def cog(id: str):
        if id not in catalog.layers:
            raise HTTPException(404, "Unknown raster")
        path, _ = catalog.layers[id]
        return FileResponse(path, media_type="image/tiff", filename=path.name, headers=CACHE)

    return app


app = create_app()
