"""End to end: packing list -> compiled program -> calibration on good kits -> evaluation.

Usage:
    .venv/bin/python scripts/e2e.py                       # evaluate on validation/good only
    .venv/bin/python scripts/e2e.py --test                # also the held-out test splits
    .venv/bin/python scripts/e2e.py --program runs/x/final.json --test   # skip compile/calibrate

Writes compiled.json, calibration.json, final.json and report.json to runs/<name>/.
Calibration uses evenly spaced train/good images only; validation and test are never shown to the
model.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from inspec.calibrate import calibrate  # noqa: E402
from inspec.compiler import compile_program  # noqa: E402
from inspec.evaluate import evaluate, images, summary  # noqa: E402
from inspec.llm import LLM  # noqa: E402
from inspec.sam_client import SamClient  # noqa: E402
from inspec.schema import CheckProgram  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--packing-list", default="1 long screw, 1 short screw, 2 nuts, 2 washers")
    ap.add_argument("--kit-name", default="screw bag")
    ap.add_argument("--data", default=str(ROOT / "data" / "screw_bag"))
    ap.add_argument("--calib", type=int, default=30, help="number of train/good images")
    ap.add_argument("--rounds", type=int, default=4)
    ap.add_argument("--program", help="evaluate this program JSON instead of compiling")
    ap.add_argument("--test", action="store_true", help="also evaluate the test splits")
    ap.add_argument("--provider", help="LLM provider (default: INSPEC_LLM_PROVIDER or meta)")
    ap.add_argument("--name", default=time.strftime("%Y%m%d-%H%M%S"))
    args = ap.parse_args()

    out = ROOT / "runs" / args.name
    out.mkdir(parents=True, exist_ok=True)
    sam = SamClient(ROOT / ".cache" / "sam")
    data = Path(args.data)
    programs: dict[str, CheckProgram] = {}

    if args.program:
        programs["given"] = CheckProgram.model_validate_json(Path(args.program).read_text())
    else:
        llm = LLM(args.provider)
        print(f"compiling with {llm.provider.name}:{llm.model} ...")
        compiled = compile_program(args.packing_list, kit_name=args.kit_name, llm=llm)
        print(f"  {compiled.attempts} attempt(s), rejected: {compiled.errors}")
        (out / "compiled.json").write_text(compiled.value.model_dump_json(indent=2))

        train = images(data, "train/good")
        step = max(len(train) // args.calib, 1)
        calib_images = train[::step][: args.calib]
        print(f"calibrating on {len(calib_images)} train/good images ...")
        result = calibrate(compiled.value, calib_images, sam=sam, llm=llm,
                           max_rounds=args.rounds)
        (out / "calibration.json").write_text(json.dumps(
            {"images": [p.name for p in calib_images], **result.to_dict()}, indent=2))
        (out / "final.json").write_text(result.program.model_dump_json(indent=2))
        print(f"  converged: {result.converged}")
        programs = {"compiled": compiled.value, "calibrated": result.program}

    splits = ["validation/good"]
    if args.test:
        splits += ["test/good", "test/logical_anomalies", "test/structural_anomalies"]
    print(f"evaluating on {', '.join(splits)} ...")
    report = evaluate(programs, data, splits, sam=sam)
    (out / "report.json").write_text(json.dumps(report, indent=2))
    print(summary(report))
    print(f"\nwrote {out.relative_to(ROOT)}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
