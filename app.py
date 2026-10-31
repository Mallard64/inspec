"""Inspec demo: packing list -> compiled program -> calibration -> inspect -> evaluation.

Run with:  .venv/bin/streamlit run app.py
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
# kit_name in a run's final.json -> (dataset folder under data/, packing list it was compiled from)
KITS = {
    "screw bag": ("screw_bag", "1 long screw, 1 short screw, 2 nuts, 2 washers"),
    "breakfast box": ("breakfast_box", "2 tangerines, 1 nectarine, granola, banana chips, almonds"),
}
SPLITS = [
    "validation/good",
    "test/good",
    "test/logical_anomalies",
    "test/structural_anomalies",
]
LIMIT_FIELDS = ("min_length", "max_length", "min_area", "max_area", "min_hole", "max_hole")

st.set_page_config(page_title="Inspec demo", layout="wide")
st.title("Inspec demo")


@st.cache_data
def read_json(path: str) -> dict | None:
    """Parsed JSON file, or None when it is missing or invalid."""
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None


@st.cache_data
def dataset_images(dataset: str, split: str) -> list[str]:
    directory = ROOT / "data" / dataset / split
    if not directory.is_dir():
        return []
    return [str(p) for p in sorted(directory.glob("*.png"))]


@st.cache_resource
def get_sam_client():
    from inspec.sam_client import SamClient

    return SamClient(ROOT / ".cache" / "sam")


@st.cache_resource
def get_damage_checker(packing_list: str, kit_name: str):
    from inspec.damage import DamageChecker

    return DamageChecker(packing_list, kit_name=kit_name, cache_dir=ROOT / ".cache" / "damage")


@st.cache_resource
def get_baseline(packing_list: str):
    from inspec.baseline import VisionBaseline

    return VisionBaseline(packing_list, cache_dir=ROOT / ".cache" / "baseline")


def available_runs() -> list[str]:
    runs_dir = ROOT / "runs"
    if not runs_dir.is_dir():
        return []
    return sorted(p for p in (d.name for d in runs_dir.iterdir() if d.is_dir())
                  if (runs_dir / p / "final.json").is_file())


def load_program(path: Path):
    from inspec.schema import CheckProgram

    return CheckProgram.model_validate_json(path.read_text())


# Sidebar.
run_names = available_runs()
default_index = run_names.index("run3") if "run3" in run_names else 0
run_name = st.sidebar.selectbox("Run", run_names, index=default_index) if run_names else None
damage_on = st.sidebar.checkbox("Muse Spark damage check", value=True)
baseline_on = st.sidebar.checkbox("Compare vision-only baseline", value=False)

if run_name is None:
    st.error("No runs found: no subdirectory of runs/ contains final.json.")
    st.stop()
run_dir = ROOT / "runs" / run_name
kit_name = (read_json(str(run_dir / "final.json")) or {}).get("kit_name", "screw bag")
dataset, default_list = KITS.get(kit_name.lower(), KITS["screw bag"])
packing_list = st.sidebar.text_input("Packing list", default_list, key=f"packing_list:{kit_name}")

# Section 1: Compile.
st.header("1. Compile")
compiled_path = run_dir / "compiled.json"
compiled_doc = read_json(str(compiled_path))
if compiled_doc is None:
    st.info(f"{compiled_path.name} is missing or invalid.")
else:
    st.json(compiled_doc, expanded=False)
if st.button("Recompile live"):
    try:
        from inspec.compiler import compile_program

        with st.spinner("Compiling..."):
            generation = compile_program(packing_list, kit_name=kit_name)
        st.json(json.loads(generation.value.model_dump_json(indent=2)), expanded=False)
        st.write(f"Attempts: {generation.attempts}")
        if generation.errors:
            st.write("Rejected attempts:")
            st.write(list(generation.errors))
    except Exception as exc:
        st.error(f"Recompile failed: {exc}")

# Section 2: Calibrate on good kits.
st.header("2. Calibrate on good kits")
calibration = read_json(str(run_dir / "calibration.json"))
if calibration is None:
    st.info("calibration.json is missing or invalid.")
else:
    rounds = calibration.get("rounds", [])
    st.table([{"round": r.get("round"), "passed": r.get("passed"), "total": r.get("total")}
              for r in rounds])
    for r in rounds:
        with st.expander(f"Round {r.get('round')}: {r.get('passed')}/{r.get('total')} pass"):
            repair = r.get("repair") or {}
            st.write("Repair notes:")
            st.write(repair.get("notes", "(no repair this round)"))
            st.write("Rejected attempts:")
            st.write(list(repair.get("rejected", [])))
            st.write("Failures (first 10 images):")
            failures = r.get("failures", {})
            if not failures:
                st.write("(none)")
            for name in sorted(failures)[:10]:
                st.write(f"{name}:")
                st.write(list(failures[name]))

    try:
        compiled_program = load_program(compiled_path)
        final_program = load_program(run_dir / "final.json")
        compiled_parts = {p.id: p for p in compiled_program.parts}
        final_parts = {p.id: p for p in final_program.parts}
        rows = [
            {"part": pid, "field": field,
             "compiled": getattr(compiled_parts[pid], field),
             "final": getattr(final_parts[pid], field)}
            for pid in compiled_parts
            if pid in final_parts
            for field in LIMIT_FIELDS
            if getattr(compiled_parts[pid], field) != getattr(final_parts[pid], field)
        ]
        st.subheader("Part limits: compiled vs final (differing fields only)")
        if rows:
            st.table(rows)
        else:
            st.write("(no limit changed during calibration)")
        compiled_check_ids = {c.id for c in compiled_program.checks}
        added = [c for c in final_program.checks
                 if c.type == "measure" and c.id not in compiled_check_ids]
        st.subheader("Measure checks added by calibration")
        if added:
            st.table([{"id": c.id, "part": c.part, "metric": c.metric,
                       "min": c.min, "max": c.max} for c in added])
        else:
            st.write("(none)")
    except Exception as exc:
        st.error(f"Could not compare compiled and final programs: {exc}")

# Section 3: Inspect a kit.
st.header("3. Inspect a kit")
image_path: str | None = None
options: list[str] = []
split = st.selectbox("Split", SPLITS)
paths = dataset_images(dataset, split)
if paths:
    options = [Path(p).name for p in paths]
    choice = st.selectbox("Image", options)
    image_path = paths[options.index(choice)] if choice else None
else:
    st.info("Dataset images are absent; upload a PNG/JPG instead.")
uploaded = st.file_uploader("Or upload a kit photo (PNG/JPG)", type=["png", "jpg", "jpeg"])
if uploaded is not None:
    data = uploaded.getvalue()
    ext = Path(uploaded.name).suffix.lower()
    if ext == ".jpeg":
        ext = ".jpg"
    digest = hashlib.sha256(data).hexdigest()
    saved = ROOT / ".cache" / "uploads" / f"{digest}{ext}"
    saved.parent.mkdir(parents=True, exist_ok=True)
    saved.write_bytes(data)
    image_path = str(saved)

if image_path is not None:
    from PIL import Image as PILImage

    from inspec.executor import fetch_segments, run_program
    from inspec.overlay import legend, render

    try:
        final_program = load_program(run_dir / "final.json")
    except Exception as exc:
        st.error(f"Could not load final program: {exc}")
        st.stop()
    try:
        sam = get_sam_client()
    except Exception as exc:
        st.error(f"SAM client failed: {exc}")
        st.stop()
    program_result = None
    try:
        with st.spinner("Running SAM and the final program..."):
            segments = fetch_segments(final_program, image_path, sam)
            program_result = run_program(final_program, segments)
            result = program_result
        image = PILImage.open(image_path).convert("RGB")
        overlay = render(image, result)
        left, right = st.columns(2)
        left.image(image, caption="Original", width="stretch")
        right.image(overlay, caption="Overlay", width="stretch")
        verdict_slot = st.empty()  # filled once the damage check (if on) has run
        st.write(f"Part checks: {'pass' if result.passed else 'FAIL'}")
        st.subheader("Legend")
        st.table([{"part": part, "colour": f"#{r:02x}{g:02x}{b:02x}", "objects": n}
                   for part, (r, g, b), n in legend(result)])
        st.subheader("Checks")
        st.table([{"id": c.check_id, "passed": c.passed, "message": c.message}
                  for c in result.checks])
    except Exception as exc:
        st.error(f"Inspection failed: {exc}")

    flags: list[str] = []
    if damage_on and image_path is not None:
        st.subheader("Damage check")
        damage_cal = read_json(str(run_dir / "damage_calibration.json")) or {}
        if not damage_cal:
            st.warning("This run has no damage_calibration.json, so every question is enabled.")
        try:
            from inspec.damage import damaged

            checker = get_damage_checker(packing_list, final_program.kit_name)
            enabled = list(damage_cal.get("enabled", checker.questions))
            with st.spinner("Running the damage check..."):
                report = checker.inspect(image_path)
            flags = damaged(report, enabled)
            st.write(f"Enabled questions: {enabled}")
            st.write(f"Flags: {flags or '(none)'}")
            st.write("Evidence:")
            st.write(report.evidence)
        except Exception as exc:
            st.error(f"Damage check failed: {exc}")
            flags = ["damage check failed"]

    if program_result is not None:
        reasons = ([] if program_result.passed else ["parts"]) + list(flags)
        if reasons:
            verdict_slot.error(f"# FAIL ({', '.join(reasons)})")
        else:
            verdict_slot.success("# PASS" + (" (parts + damage)" if damage_on else ""))

    if baseline_on and image_path is not None:
        st.subheader("Vision-only baseline")
        try:
            with st.spinner("Running the vision-only baseline..."):
                verdict = get_baseline(packing_list).inspect(image_path)
            st.table([{"part": c.part, "expected": c.expected, "seen": c.seen}
                      for c in verdict.counts])
            st.write(f"Failures: {verdict.failures() or '(none)'}")
            st.write(f"Reason: {verdict.reason}")
            if verdict.failures():
                st.error(f"Baseline verdict: FAIL ({', '.join(verdict.failures())})")
            else:
                st.success("Baseline verdict: PASS")
        except Exception as exc:
            st.error(f"Baseline failed: {exc}")

# Section 4: Evaluation.
st.header("4. Evaluation")
report = read_json(str(run_dir / "report.json"))
if report is None:
    st.info("report.json is missing or invalid.")
else:
    rows = []
    for split_name, entry in report.get("splits", {}).items():
        what = "false alarms" if entry.get("kind") == "good" else "recall"
        for program_name, pentry in entry.get("programs", {}).items():
            rows.append({"split": split_name, "program": program_name,
                         "kind": what, "flagged": pentry.get("flagged"),
                         "images": entry.get("images"), "rate": pentry.get("rate")})
    st.table(rows)
