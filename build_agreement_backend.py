import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List

from parse_assist_agreement import parse_agreement_bundle

AGREEMENT_FILE_RE = re.compile(r"^A[MDP]\d+_\d+\.json$", re.IGNORECASE)


def find_agreement_files(root: Path) -> List[Path]:
    files: List[Path] = []
    for p in root.rglob("*.json"):
        if AGREEMENT_FILE_RE.match(p.name):
            files.append(p)
    return sorted(files)


def build_backend_payload(root: Path) -> Dict[str, Any]:
    agreements: List[Dict[str, Any]] = []
    for file_path in find_agreement_files(root):
        try:
            bundle = parse_agreement_bundle(file_path)
            bundle["folder"] = file_path.parent.name
            bundle["relative_path"] = str(file_path.relative_to(root))
            agreements.append(bundle)
        except Exception as exc:  # noqa: BLE001
            agreements.append(
                {
                    "file": file_path.name,
                    "folder": file_path.parent.name,
                    "relative_path": str(file_path.relative_to(root)),
                    "error": str(exc),
                    "row_count": 0,
                    "mappings": [],
                }
            )

    return {
        "root": str(root),
        "total_files": len(agreements),
        "agreements": agreements,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build one backend JSON payload from all ASSIST agreement files (AM/AD/AP) in folders."
    )
    parser.add_argument("root", nargs="?", default=".", help="Root folder containing agreement folders/files")
    parser.add_argument("--out", default="agreements_backend.json", help="Output backend JSON")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    payload = build_backend_payload(root)

    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = root / out_path

    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Wrote {payload['total_files']} agreement files to {out_path}")


if __name__ == "__main__":
    main()
