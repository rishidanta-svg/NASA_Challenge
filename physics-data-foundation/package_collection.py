"""Write checksums and a standalone copy of the built Duck data collection."""
import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from build_geospatial import digest, write_json


def usable(path):
    return path.is_file() and path.stat().st_size > 0 and path.suffix != ".part" and "_test." not in path.name


def pack(root, output):
    unified = root / "data/unified"
    for name in ("duck_observations.nc", "cross_date.nc", "acquisition_manifest.json", "verification.json"):
        if not (unified / name).is_file():
            raise FileNotFoundError(unified / name)
    data_files = sorted(p for p in (root / "data").rglob("*")
                        if p.name != "source_checksums.json" and usable(p))
    records = [{"file": str(path.relative_to(root)), "bytes": path.stat().st_size, "sha256": digest(path)}
               for path in data_files]
    checksums = unified / "source_checksums.json"
    write_json(checksums, records)
    documents = sorted(root.glob("*.md"))
    scripts = sorted(root.glob("*.py"))
    paths = [*documents, *scripts, root / "requirements.txt", *data_files, checksums]
    partial = output.with_suffix(".zip.part")
    with ZipFile(partial, mode="w", compression=ZIP_DEFLATED, compresslevel=6) as archive:
        for file in paths:
            archive.write(file, Path("POLTERGEIST_Duck_Data_Foundation") / file.relative_to(root))
    with ZipFile(partial) as archive:
        if len(archive.infolist()) != len(paths) or archive.testzip() is not None:
            raise RuntimeError("Package integrity check failed")
    partial.replace(output)
    print(f"{len(paths)} packaged files, {output.stat().st_size:,} bytes")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", default=Path("."), type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    pack(args.workspace, args.output)
