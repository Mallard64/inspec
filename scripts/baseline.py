"""Score the vision-only baseline (Muse Spark, photo + packing list, no SAM) on Screw Bag.

Usage:
    .venv/bin/python scripts/baseline.py --name baseline0               # zero-shot
    .venv/bin/python scripts/baseline.py --name baseline1 --references 1  # + 1 good kit shown
    .venv/bin/python scripts/baseline.py --name b3h --references 3 --hint "..."  # + size hint

Writes report.json (same format as scripts/e2e.py) and verdicts.json to runs/<name>/.
Reference images are evenly spaced train/good kits, never validation or test.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from inspec.baseline import VisionBaseline  # noqa: E402
from inspec.evaluate import SPLITS, _entry, defect_types, images, summary  # noqa: E402
from inspec.llm import LLM  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--packing-list", default="1 long screw, 1 short screw, 2 nuts, 2 washers")
    ap.add_argument("--data", default=str(ROOT / "data" / "screw_bag"))
    ap.add_argument("--references", type=int, default=0, help="good train kits shown first")
    ap.add_argument("--hint", default="", help="extra sentence added to the instructions")
    ap.add_argument("--provider")
    ap.add_argument("--name", required=True)
    args = ap.parse_args()

    data, out = Path(args.data), ROOT / "runs" / args.name
    out.mkdir(parents=True, exist_ok=True)
    train = images(data, "train/good")
    refs = train[:: max(len(train) // max(args.references, 1), 1)][: args.references]
    baseline = VisionBaseline(args.packing_list, llm=LLM(args.provider), references=refs,
                              hint=args.hint, cache_dir=ROOT / ".cache" / "baseline")
    report: dict = {"references": [p.name for p in refs], "hint": args.hint, "splits": {}}
    verdicts: dict = {}
    for split, kind in SPLITS.items():
        paths = images(data, split)
        print(f"{split}: {len(paths)} images ...", flush=True)
        results = baseline.inspect_many(paths)
        flagged = {Path(p).name for p, v in results.items() if v.failures()}
        fails: dict[str, int] = defaultdict(int)
        for v in results.values():
            for f in v.failures():
                fails[f"baseline:{f}"] += 1
        types = defect_types(data, split) if kind != "good" else {}
        report["splits"][split] = {"kind": kind, "images": len(paths), "programs": {
            "vision_baseline": _entry(flagged, len(paths), types, fails)}}
        verdicts[split] = {Path(p).name: v.model_dump() for p, v in results.items()}
    (out / "report.json").write_text(json.dumps(report, indent=2))
    (out / "verdicts.json").write_text(json.dumps(verdicts, indent=1))
    print(summary(report))
    print(f"\nwrote {out.relative_to(ROOT)}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
