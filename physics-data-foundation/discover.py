"""Archive catalogue search responses and source products as received."""
import argparse
from datetime import datetime, timezone
import hashlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
import subprocess
from urllib.parse import urlencode

BBOX = (-75.753384, 36.183704, -75.750335, 36.188260)
BBOX_TEXT = ",".join(map(str, BBOX))
EARTH = "https://earth-search.aws.element84.com/v1"
PC = "https://planetarycomputer.microsoft.com/api/stac/v1"
CMR = "https://cmr.earthdata.nasa.gov/stac/ASF"
COOPS = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
NDBC = "https://www.ndbc.noaa.gov"
FRF = "https://chldata.erdc.dren.mil/thredds"

def url(base, **query):
    return base + "?" + urlencode(query, safe=",:/[]")

def search(base, collection, start, end):
    return url(base + "/search", collections=collection, bbox=BBOX_TEXT,
               datetime=f"{start}T00:00:00Z/{end}T23:59:59Z", limit=100)

def download(task):
    path, source = task
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".part")
    run = subprocess.run(["curl", "--silent", "--show-error", "--location", "--retry", "1",
                          "--connect-timeout", "8", "--max-time", "30",
                          "--write-out", "%{http_code}", "--output", str(partial), source],
                         capture_output=True, text=True)
    if run.returncode == 0 and run.stdout.startswith("2") and partial.exists() and partial.stat().st_size > 0:
        partial.replace(path)
    else:
        partial.unlink(missing_ok=True)
        path.unlink(missing_ok=True)
    return {
        "file": path.name, "url": source, "http_status": run.stdout,
        "size_bytes": path.stat().st_size if path.exists() else 0,
        "error": run.stderr.strip() or ("Empty response" if run.stdout.startswith("2") and not path.exists() else None),
        "retrieved_utc": datetime.now(timezone.utc).isoformat(),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None,
    }

def initial_queries(root):
    dates = {
        "june": ("2026-06-11", "2026-06-30"),
        "september": ("2026-09-25", "2026-10-02"),
        "october": ("2026-10-12", "2026-10-20"),
    }
    for group, (start, end) in dates.items():
        for name, base, collection in [
            ("s2_earth", EARTH, "sentinel-2-l2a"),
            ("s2_pc", PC, "sentinel-2-l2a"),
            ("s1_earth_grd", EARTH, "sentinel-1-grd"),
            ("s1_pc_rtc", PC, "sentinel-1-rtc"),
            ("s1_pc_grd", PC, "sentinel-1-grd"),
            ("s1_opera", CMR, "OPERA_L2_RTC-S1_V1"),
        ]:
            yield root / f"{name}_{group}.json", search(base, collection, start, end)
        wkt = f"POINT({(BBOX[0]+BBOX[2])/2} {(BBOX[1]+BBOX[3])/2})"
        yield root / f"s1_asf_grd_{group}.json", url(
            "https://api.daac.asf.alaska.edu/services/search/param",
            platform="Sentinel-1", processingLevel="GRD_HD", intersectsWith=wkt,
            start=f"{start}T00:00:00Z", end=f"{end}T23:59:59Z", output="geojson")
        yield root / f"s1_asf_opera_{group}.json", url(
            "https://api.daac.asf.alaska.edu/services/search/param",
            dataset="OPERA-S1", processingLevel="RTC", bbox=BBOX_TEXT,
            start=f"{start}T00:00:00Z", end=f"{end}T23:59:59Z", output="geojson")

    for name, start, end in [
        ("june", "20260607", "20260701"), ("september", "20260921", "20261003"),
        ("october", "20261008", "20261021"),
    ]:
        for product in ("water_level", "predictions", "wind"):
            params = dict(station="8651370", begin_date=start, end_date=end, product=product,
                          time_zone="gmt", units="metric", format="json", application="Poltergeist")
            if product in {"water_level", "predictions"}:
                params["datum"] = "MLLW"
            if product == "predictions":
                params["interval"] = "6"
            yield root / f"coops_{product}_{name}.json", url(COOPS, **params)
    for station in ("44056", "DUKN7"):
        yield root / f"ndbc_{station}_realtime.txt", f"{NDBC}/data/realtime2/{station}.txt"
        yield root / f"ndbc_{station}_2026.nc", (
            f"https://dods.ndbc.noaa.gov/thredds/fileServer/data/stdmet/{station.lower()}/{station.lower()}h2026.nc"
        )
    for name, host, subdir in [
        ("frf_root", FRF, ""), ("frf_waves", FRF, "oceanography/waves/"),
        ("frf_met", FRF, "meteorology/"), ("frf_hydro", FRF, "oceanography/"),
        ("frf_geomorph", FRF, "geomorphology/"),
        ("frf_root_legacy", "https://chlthredds.erdc.dren.mil/thredds", ""),
    ]:
        yield root / f"{name}.xml", f"{host}/catalog/frf/{subdir}catalog.xml"
    yield root / "pc_rtc_collection.json", PC + "/collections/sentinel-1-rtc"
    for name, subdir in [
        ("rain", "meteorology/metGauges/rain"), ("wave17", "oceanography/waves/waverider-17m"),
        ("wave26", "oceanography/waves/waverider-26m"), ("runup", "oceanography/waves/lidarWaveRunup"),
        ("hydro", "oceanography/waves/lidarHydrodynamics"), ("nearshore_awac", "oceanography/waves/awac-jpier-11m"),
    ]:
        for year in ("", "2026/"):
            suffix = "_2026" if year else ""
            yield root / f"frf_catalog_{name}{suffix}.xml", f"{FRF}/catalog/frf/{subdir}/{year}catalog.xml"
    for station in ("8651370",):
        yield root / f"coops_station_{station}.json", (
            f"https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations/{station}.json?expand=details,sensors,datums"
        )

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/raw/discovery"))
    args = parser.parse_args()
    with ThreadPoolExecutor(max_workers=10) as pool:
        result = list(pool.map(download, initial_queries(args.output)))
    (args.output / "requests.json").write_text(json.dumps(result, indent=2) + "\n")
    for item in result:
        print(item["http_status"], item["size_bytes"], item["file"], item["error"] or "")

if __name__ == "__main__":
    main()
