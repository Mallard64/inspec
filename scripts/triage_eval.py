"""Score PASS / REVIEW / FAIL (inspec/triage.py) for a saved program plus its damage check.

Usage:
    .venv/bin/python scripts/triage_eval.py --kit screw_bag              # validation/good only
    .venv/bin/python scripts/triage_eval.py --kit screw_bag --test       # + test splits, once

Uses cached SAM and Muse Spark answers from the runs named below; writes runs/<out>/triage.json.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from inspec.damage import DamageChecker, damaged  # noqa: E402
from inspec.evaluate import defect_types, images  # noqa: E402
from inspec.executor import fetch_segments, run_program  # noqa: E402
from inspec.sam_client import SamClient  # noqa: E402
from inspec.schema import CheckProgram  # noqa: E402
from inspec.triage import overshoot, triage  # noqa: E402

KITS = {  # program run, run holding the frozen damage calibration, kit name, packing list
    "screw_bag": ("run3", "sb-final2", "screw bag", "1 long screw, 1 short screw, 2 nuts, 2 washers"),
    "breakfast_box": ("bb4", "bb5-final", "breakfast box",
                      "2 tangerines, 1 nectarine, granola, banana chips, almonds"),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kit", choices=KITS, required=True)
    ap.add_argument("--test", action="store_true", help="also score the test splits")
    args = ap.parse_args()
    run, damage_run, name, plist = KITS[args.kit]
    data = ROOT / "data" / args.kit
    program = CheckProgram.model_validate_json((ROOT / "runs" / run / "final.json").read_text())
    enabled = json.loads((ROOT / "runs" / damage_run / "damage_calibration.json").read_text())["enabled"]
    checker = DamageChecker(plist, kit_name=name, cache_dir=ROOT / ".cache" / "damage")
    sam = SamClient(ROOT / ".cache" / "sam")
    splits = ["validation/good"] + (["test/good", "test/logical_anomalies",
                                     "test/structural_anomalies"] if args.test else [])
    report: dict = {}
    for split in splits:
        types = defect_types(data, split) if "anomal" in split else {}
        tally, by_type = Counter(), defaultdict(Counter)
        for path in images(data, split):
            result = run_program(program, fetch_segments(program, path, sam))
            verdict, reasons = triage(result.checks, damaged(checker.inspect(path), enabled))
            tally[verdict] += 1
            for t in types.get(path.name, []):
                by_type[t][verdict] += 1
            near = [f"{c.check_id} {overshoot(c):.1%} over" for c in result.checks
                    if not c.passed and isinstance(c.value, list)]
            if split.endswith("good") and verdict != "PASS":
                print(f"  {split} {path.name}: {verdict} {reasons} {near}")
        report[split] = {"images": sum(tally.values()), **tally,
                         "by_defect": {t: dict(c) for t, c in sorted(by_type.items())}}
        print(f"{split:28} PASS {tally['PASS']:3}  REVIEW {tally['REVIEW']:3}  FAIL {tally['FAIL']:3}")
    out = ROOT / "runs" / f"{damage_run}-triage"
    out.mkdir(exist_ok=True)
    (out / "triage.json").write_text(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
