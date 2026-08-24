"""Create immutable-ish dataset manifests for reproducible LLM experiments."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def build_manifest(paths: list[str], name: str, license_note: str) -> dict:
    files = []
    for raw in paths:
        p = Path(raw)
        files.append({
            "path": str(p),
            "bytes": p.stat().st_size,
            "sha256": sha256(p),
        })
    return {
        "schema_version": 1,
        "dataset_name": name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "license_provenance": license_note,
        "files": files,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("files", nargs="+")
    p.add_argument("--name", required=True)
    p.add_argument("--license-note", required=True,
                   help="Document source/license/usage constraints; do not use unlicensed corpora.")
    p.add_argument("--output", required=True)
    args = p.parse_args()
    manifest = build_manifest(args.files, args.name, args.license_note)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
