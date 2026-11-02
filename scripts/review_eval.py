"""Does showing Muse Spark reviewed kits (inspec/review.py) improve the damage check?

No real reviewers here, so a simulated one uses the dataset's labels: the calibration train/good
kits that any damage question flagged are known good, so the "reviewer" passes them, and they
become the example photos (``review.pick_examples``, the same selection the app uses). Three
configurations are scored:

- ``without``: no examples (the frozen results),
- ``with``: examples, keeping the frozen list of enabled questions (what the app does),
- ``with_recal``: examples, with the questions re-calibrated on the other calibration kits.

Splits: validation/good and the even-numbered (dev) test anomalies; with ``--heldout`` (only after
freezing the code) also test/good and the odd-numbered half.

Usage:
    .venv/bin/python scripts/review_eval.py --kit breakfast_box
    .venv/bin/python scripts/review_eval.py --kit breakfast_box --heldout

Writes runs/<damage run>-examples/review_eval.json.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from inspec.damage import DamageChecker, calibrate_damage, damaged  # noqa: E402
from inspec.evaluate import images  # noqa: E402
from inspec.executor import fetch_segments, run_program  # noqa: E402
from inspec.review import pick_examples  # noqa: E402
from inspec.sam_client import SamClient  # noqa: E402
from inspec.schema import CheckProgram  # noqa: E402
from inspec.triage import triage  # noqa: E402

KITS = {  # program run, run holding the frozen damage calibration, kit name, packing list
    "screw_bag": ("run3", "sb-final2", "screw bag", "1 long screw, 1 short screw, 2 nuts, 2 washers"),
    "breakfast_box": ("bb4", "bb5-final", "breakfast box",
                      "2 tangerines, 1 nectarine, granola, banana chips, almonds"),
}
ANOMALIES = ("test/logical_anomalies", "test/structural_anomalies")


def half(paths: list[Path], heldout: bool) -> list[Path]:
    """Even-numbered images are the dev half, odd-numbered the held-out half."""
    return [p for p in paths if int(p.stem) % 2 == (1 if heldout else 0)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kit", choices=KITS, required=True)
    ap.add_argument("--heldout", action="store_true",
                    help="also score test/good and the odd-numbered anomalies (after freezing)")
    args = ap.parse_args()
    run, damage_run, name, plist = KITS[args.kit]
    data = ROOT / "data" / args.kit
    cache = ROOT / ".cache" / "damage"
    program = CheckProgram.model_validate_json((ROOT / "runs" / run / "final.json").read_text())
    frozen = json.loads((ROOT / "runs" / damage_run / "damage_calibration.json").read_text())
    calib_names = set(json.loads((ROOT / "runs" / run / "calibration.json").read_text())["images"])
    calib = [p for p in images(data, "train/good") if p.name in calib_names]
    sam = SamClient(ROOT / ".cache" / "sam")

    plain = DamageChecker(plist, kit_name=name, cache_dir=cache)
    reports = plain.inspect_many(calib)
    decisions = {}  # the simulated reviewer passes every flagged known-good calibration kit
    for i, path in enumerate(calib):
        flags = sorted(reports[str(path)].flags() & set(plain.questions))
        if flags:
            decisions[path.name] = dict(image=str(path), kit=args.kit, decision="PASS",
                                        flags=flags, note="", time=f"{i:04d}")
    examples = pick_examples(decisions, args.kit, plain.questions, Path)
    print(f"{len(decisions)} of {len(calib)} calibration kits flagged; examples: "
          + "; ".join(f"{Path(e.image).name} {','.join(e.flags)}" for e in examples))
    taught = DamageChecker(plist, kit_name=name, cache_dir=cache, examples=examples)
    rest = [p for p in calib if str(p) not in {e.image for e in examples}]
    recal = calibrate_damage(taught.inspect_many(rest))
    print(f"re-calibrated on {len(rest)} kits: false alarms {recal['false_alarms']}")
    print(f"  enabled without examples: {frozen['enabled']}")
    print(f"  enabled with examples:    {recal['enabled']}")

    splits = {"validation/good": images(data, "validation/good")}
    for split in ANOMALIES:
        splits[f"{split} (dev, even)"] = half(images(data, split), False)
    if args.heldout:
        splits["test/good"] = images(data, "test/good")
        for split in ANOMALIES:
            splits[f"{split} (held-out, odd)"] = half(images(data, split), True)

    report: dict = {"examples": [dict(image=Path(e.image).name, flags=list(e.flags))
                                 for e in examples],
                    "enabled": {"without": frozen["enabled"], "with": frozen["enabled"],
                                "with_recal": recal["enabled"]},
                    "recalibration": recal, "splits": {}}
    for split, paths in splits.items():
        results = {p: run_program(program, fetch_segments(program, p, sam)) for p in paths}
        row = {}
        for label, checker, enabled in (("without", plain, frozen["enabled"]),
                                        ("with", taught, frozen["enabled"]),
                                        ("with_recal", taught, recal["enabled"])):
            answers = checker.inspect_many(paths)
            row[label] = dict(Counter(triage(results[p].checks,
                                             damaged(answers[str(p)], enabled))[0] for p in paths))
        report["splits"][split] = {"images": len(paths), **row}
        print(f"{split:42} " + "  ".join(
            f"{k}: " + " ".join(f"{v} {row[k].get(v, 0):3}" for v in ("PASS", "REVIEW", "FAIL"))
            for k in ("without", "with", "with_recal")))
    out = ROOT / "runs" / f"{damage_run}-examples"
    out.mkdir(exist_ok=True)
    (out / "review_eval.json").write_text(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
