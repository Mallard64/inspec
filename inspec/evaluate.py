"""Score a check program on MVTec LOCO splits.

A kit is flagged when the program fails. Metrics:

- false-alarm rate: flagged good kits / good kits
- recall: flagged anomalous kits / anomalous kits, overall and per defect type

Defect types come from the ground-truth masks: each anomaly image has a folder of PNGs whose pixel
values map to defect names in ``defects_config.json``.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image

from inspec.calibrate import fetch_many, run_many
from inspec.schema import CheckProgram

SPLITS = {
    "validation/good": "good",
    "test/good": "good",
    "test/logical_anomalies": "logical",
    "test/structural_anomalies": "structural",
}


def images(category_dir: Path, split: str) -> list[Path]:
    return sorted((category_dir / split).glob("*.png"))


def defect_types(category_dir: Path, split: str) -> dict[str, list[str]]:
    """Image name -> defect names, read from the ground-truth masks."""
    config = json.loads((category_dir / "defects_config.json").read_text())
    names = {d["pixel_value"]: d["defect_name"] for d in config}
    out = {}
    kind = split.split("/")[-1]
    for image in images(category_dir, split):
        values: set[int] = set()
        for mask in sorted((category_dir / "ground_truth" / kind / image.stem).glob("*.png")):
            values |= {int(v) for v in np.unique(np.asarray(Image.open(mask))) if v}
        out[image.name] = sorted(names.get(v, f"pixel_{v}") for v in values)
    return out


def evaluate(programs: dict[str, CheckProgram], category_dir: str | Path, splits: list[str], *,
             sam, workers: int = 8) -> dict:
    """Run each named program on each split. Returns a JSON-safe report."""
    category_dir = Path(category_dir)
    concepts = sorted({c for p in programs.values() for c in p.concepts()})
    fetch_program = CheckProgram(  # one program covering every concept, so SAM is called once
        kit_name="fetch", parts=[{"id": f"p{i}", "concept": c} for i, c in enumerate(concepts)],
        checks=[{"id": "c", "type": "count", "part": "p0", "min": 0}])
    report: dict = {"splits": {}}
    for split in splits:
        paths = images(category_dir, split)
        segments = fetch_many(fetch_program, paths, sam, workers=workers)
        types = defect_types(category_dir, split) if SPLITS[split] != "good" else {}
        split_report = {"kind": SPLITS[split], "images": len(paths), "programs": {}}
        for name, program in programs.items():
            results = run_many(program, {p: {c: s[c] for c in program.concepts()}
                                         for p, s in segments.items()})
            flagged = {Path(p).name for p, r in results.items() if not r.passed}
            entry: dict = {"flagged": len(flagged), "rate": len(flagged) / max(len(paths), 1)}
            if types:
                per_type: dict[str, list[int]] = defaultdict(lambda: [0, 0])
                for image, names in types.items():
                    for defect in names or ["unknown"]:
                        per_type[defect][1] += 1
                        per_type[defect][0] += image in flagged
                entry["by_defect"] = {d: {"flagged": f, "images": n}
                                      for d, (f, n) in sorted(per_type.items())}
            fails: dict[str, int] = defaultdict(int)
            for r in results.values():
                for c in r.failed():
                    fails[c.check_id] += 1
            entry["failed_checks"] = dict(sorted(fails.items()))
            entry["flagged_images"] = sorted(flagged)
            split_report["programs"][name] = entry
        report["splits"][split] = split_report
    return report


def summary(report: dict) -> str:
    """Plain-text table: rate per split and program (false alarms for good, recall otherwise)."""
    lines = []
    for split, s in report["splits"].items():
        what = "false alarms" if s["kind"] == "good" else "recall"
        for name, entry in s["programs"].items():
            lines.append(f"{split:28} {name:12} {what:12} {entry['flagged']:3}/{s['images']:<3} "
                         f"= {entry['rate']:.1%}")
            for defect, d in entry.get("by_defect", {}).items():
                lines.append(f"{'':28} {'':12}   {defect:26} {d['flagged']:3}/{d['images']}")
    return "\n".join(lines)
