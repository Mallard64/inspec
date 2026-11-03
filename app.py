"""Inspec demo, one page in story order: packing list -> checks -> self-repair -> inspect -> results.

Run with:  .venv/bin/streamlit run app.py
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

import streamlit as st

from inspec.explain import describe_check, describe_question, describe_result, label, learned
from inspec.live import CallLog, LoggedLLM, LoggedSam
from inspec import review
from inspec.triage import triage

ROOT = Path(__file__).resolve().parent
REVIEW_LOG = ROOT / "runs" / "reviews.jsonl"  # gitignored: image names and decisions only
# Kit -> dataset folder, packing list, demo run (compiled/calibration/final.json), and the
# held-out reports behind the results table: Inspec with damage check, and the vision-only
# baseline (whose reference photos and hint the comparison toggle reuses).
KITS = {
    "Screw Bag": dict(dataset="screw_bag", run="run3", inspec_report="sb-final2",
                      baseline_report="baseline3h",
                      packing_list="1 long screw, 1 short screw, 2 nuts, 2 washers"),
    "Breakfast Box": dict(dataset="breakfast_box", run="bb4", inspec_report="bb5-final",
                          baseline_report="bb-baseline3",
                          packing_list="2 tangerines, 1 nectarine, granola, banana chips, almonds"),
}
KINDS = {
    "Good kit": "validation/good",
    "Wrong parts or amounts": "test/logical_anomalies",
    "Damaged or contaminated": "test/structural_anomalies",
}

st.set_page_config(page_title="Inspec", layout="wide")


@st.cache_data
def read_json(path: str) -> dict | list | None:
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None


@st.cache_data
def dataset_images(dataset: str, split: str) -> list[str]:
    directory = ROOT / "data" / dataset / split
    return [str(p) for p in sorted(directory.glob("*.png"))] if directory.is_dir() else []


@st.cache_data
def dataset_labels(dataset: str, split: str) -> dict[str, list[str]]:
    """Image name -> LOCO defect names (the dataset's answer key); {} for good splits."""
    if split.endswith("good"):
        return {}
    from inspec.evaluate import defect_types

    try:
        return defect_types(ROOT / "data" / dataset, split)
    except (OSError, ValueError):
        return {}


@st.cache_resource
def get_sam_client():
    from inspec.sam_client import SamClient

    return SamClient(ROOT / ".cache" / "sam")


@st.cache_resource
def get_damage_checker(packing_list: str, kit_name: str, examples: tuple = ()):
    from inspec.damage import DamageChecker

    return DamageChecker(packing_list, kit_name=kit_name, cache_dir=ROOT / ".cache" / "damage",
                         examples=examples)


def image_key(path: str | Path) -> str:
    """How the review log names a photo: its path under data/, or an upload's file name."""
    resolved = Path(path).resolve()
    data = ROOT / "data"
    return str(resolved.relative_to(data)) if resolved.is_relative_to(data) else resolved.name


def reviewer_examples(dataset: str, questions: list[str], inspecting: str | Path) -> tuple:
    """Reviewed kits to show Muse Spark, never the kit being inspected."""
    def resolve(key: str) -> Path | None:
        for path in (ROOT / "data" / key, ROOT / ".cache" / "uploads" / key):
            if path.exists() and key != image_key(inspecting):
                return path
        return None

    return tuple(review.pick_examples(review.load(REVIEW_LOG), dataset, questions, resolve))


@st.cache_resource
def get_baseline(packing_list: str, dataset: str, references: tuple[str, ...], hint: str):
    from inspec.baseline import VisionBaseline

    refs = [ROOT / "data" / dataset / "train" / "good" / r for r in references]
    return VisionBaseline(packing_list, references=refs, hint=hint,
                          cache_dir=ROOT / ".cache" / "baseline")


def load_program(path: Path):
    from inspec.schema import CheckProgram

    return CheckProgram.model_validate_json(path.read_text())


def show_calls(log: CallLog, sam: LoggedSam | None = None) -> None:
    """The model calls behind what's on screen: Muse Spark calls one by one, SAM summarised."""
    rows = [{"model": c.model, "call": c.what, "seconds": round(c.seconds, 1)}
            for c in log.calls if not c.model.startswith("sam")]
    seg = [c for c in log.calls if c.model.startswith("sam")]
    if seg:
        cached = len(seg) - sam.api_calls if sam else 0
        rows.append({"model": seg[0].model,
                     "call": f"{len(seg)} segmentations" + (
                         f" ({sam.api_calls} sent to the API, {cached} from the disk cache)"
                         if cached else " (all sent to the API)" if sam else ""),
                     "seconds": round(sum(c.seconds for c in seg), 1)})
    st.markdown("**Meta model calls**")
    st.dataframe(rows, hide_index=True, width="stretch")


def chip(text: str, color: str = "#e8eef7", fg: str = "#1d2b3a") -> str:
    return (f"<span style='background:{color};color:{fg};padding:6px 14px;border-radius:999px;"
            f"margin:0 8px 8px 0;display:inline-block;font-size:1.15rem'>{text}</span>")


st.title("Inspec")
st.caption("Type a packing list. Inspec turns it into checks, fixes them on known-good kits, "
           "and inspects each kit with a mask on every part it counted.")

# URL parameters preselect a view, e.g. ?kit=Breakfast Box&show=Damaged or contaminated&image=045
params = st.query_params
kit = st.radio("Kit", list(KITS), horizontal=True,
               index=list(KITS).index(params["kit"]) if params.get("kit") in KITS else 0)
cfg = KITS[kit]
run_dir = ROOT / "runs" / cfg["run"]
if not (run_dir / "final.json").is_file():
    st.error(f"Run `{cfg['run']}` not found. Run scripts/e2e.py first (see README).")
    st.stop()
final = load_program(run_dir / "final.json")
compiled = load_program(run_dir / "compiled.json")
packing_list = cfg["packing_list"]

# 1. Packing list -> checks.
st.header("1 · The packing list")
st.markdown("".join(chip(item.strip()) for item in packing_list.split(",")),
            unsafe_allow_html=True)
st.markdown("**Muse Spark turned it into these checks:**")
for check in compiled.checks:
    st.markdown(f"- {describe_check(check)}")
with st.expander("Show the check program (JSON) or recompile it live"):
    st.json(compiled.model_dump(exclude_none=True), expanded=False)
    if st.button("Recompile with Muse Spark"):
        from inspec.compiler import compile_program

        try:
            with st.spinner("Compiling..."):
                generation = compile_program(packing_list, kit_name=final.kit_name)
            for check in generation.value.checks:
                st.markdown(f"- {describe_check(check)}")
        except Exception as exc:
            st.error(f"Recompile failed: {exc}")

# 2. Self-repair on good kits.
st.header("2 · It fixes its own checks on good kits")
val = (read_json(str(run_dir / "report.json")) or {}).get("splits", {}).get("validation/good", {})
before = val.get("programs", {}).get("compiled")
after = val.get("programs", {}).get("calibrated")
if before and after:
    a, b, _ = st.columns([1, 1, 2])
    a.metric("Good kits rejected, as first written", f"{before['flagged']} / {val['images']}")
    b.metric("After self-repair", f"{after['flagged']} / {val['images']}",
             delta=after["flagged"] - before["flagged"], delta_color="inverse")
st.markdown("A check that fails on a kit known to be good is wrong. Inspec shows those failures "
            "to Muse Spark, which rewrites the check, and code validates every fix before it's "
            "kept. **What it learned from 60 good kits:**")
for line in learned(compiled, final, read_json(str(run_dir / "concepts.json"))):
    st.markdown(f"- {line}")
if st.button("▶ Run it live: compile the list, then self-repair on 60 good kits"):
    from inspec.calibrate import calibrate
    from inspec.compiler import compile_program
    from inspec.concepts import repair_concepts
    from inspec.llm import LLM

    calls = CallLog()
    good = [ROOT / "data" / cfg["dataset"] / "train" / "good" / name
            for name in (read_json(str(run_dir / "calibration.json")) or {}).get("images", [])]
    sam = LoggedSam(get_sam_client(), calls)
    with st.status("Muse Spark is compiling the packing list...", expanded=True) as status:
        try:
            program = compile_program(packing_list, kit_name=final.kit_name, llm=LoggedLLM(
                LLM(), calls, "compile packing list into checks")).value
            st.markdown("**Compiled:** " + " · ".join(describe_check(c) for c in program.checks))
            status.update(label="Checking SAM knows each item...")
            fixed, _ = repair_concepts(program, good[:20], sam=sam, log=st.caption, llm=LoggedLLM(
                LLM(), calls, "suggest other words for SAM"))
            status.update(label=f"Running the checks on {len(good)} good kits; "
                                "Muse Spark repairs what fails...")
            cal = calibrate(fixed, good, sam=sam, log=st.caption, llm=LoggedLLM(
                LLM(), calls, "repair checks that failed on good kits"))
            rounds = cal.to_dict()["rounds"]
            for line in learned(program, cal.program):
                st.markdown(f"- {line}")
            status.update(state="complete", label=(
                f"Done: {rounds[0]['passed']}/{rounds[0]['total']} → {rounds[-1]['passed']}/"
                f"{rounds[-1]['total']} good kits pass, in {len(rounds)} rounds"))
        except Exception as exc:
            status.update(state="error", label=f"Live run failed: {exc}")
    show_calls(calls, sam)
with st.expander("Muse Spark's repair notes"):
    for r in (read_json(str(run_dir / "calibration.json")) or {}).get("rounds", []):
        st.markdown(f"**Round {r['round']}:** {r['passed']}/{r['total']} good kits pass")
        notes = (r.get("repair") or {}).get("notes")
        if notes:
            st.caption(notes)

# 3. Inspect a kit.
st.header("3 · Inspect a kit")
left, right, opts = st.columns([2, 3, 2])
split = KINDS[left.selectbox("Show me", list(KINDS), index=list(KINDS).index(params["show"])
                             if params.get("show") in KINDS else 0)]
paths = dataset_images(cfg["dataset"], split)
labels = dataset_labels(cfg["dataset"], split)
image_path = None
if paths:
    names = [Path(p).name for p in paths]
    shown = [f"{n[:-4]} · {', '.join(labels[n]).replace('_', ' ')}" if labels.get(n) else n[:-4]
             for n in names]
    start = next((i for i, n in enumerate(names) if n[:-4] == params.get("image")), 0)
    image_path = paths[shown.index(right.selectbox("Image (dataset label)", shown, index=start))]
baseline_on = opts.toggle("Compare with Muse Spark alone", value=params.get("compare") == "1")
live = opts.toggle("Live model calls (skip cache)", value=params.get("live") == "1")
with st.expander("Or upload a photo"):
    uploaded = st.file_uploader("Kit photo", type=["png", "jpg", "jpeg"])
    if uploaded is not None:
        data = uploaded.getvalue()
        ext = ".jpg" if uploaded.name.lower().endswith(".jpeg") else Path(uploaded.name).suffix.lower()
        saved = ROOT / ".cache" / "uploads" / f"{hashlib.sha256(data).hexdigest()}{ext}"
        saved.parent.mkdir(parents=True, exist_ok=True)
        saved.write_bytes(data)
        image_path = str(saved)

if image_path is not None:
    from PIL import Image as PILImage

    from inspec.damage import damaged
    from inspec.executor import fetch_segments, run_program
    from inspec.overlay import legend, render

    calls = CallLog()
    examples = reviewer_examples(cfg["dataset"], get_damage_checker(packing_list,
                                                                    final.kit_name).questions,
                                 image_path)
    if live:  # fresh clients on an empty cache, so every answer below comes from the API now
        from inspec.damage import DamageChecker
        from inspec.llm import LLM
        from inspec.sam_client import SamClient

        scratch = tempfile.mkdtemp(prefix="inspec-live-")
        sam = LoggedSam(SamClient(Path(scratch) / "sam"), calls)
        checker = DamageChecker(packing_list, kit_name=final.kit_name, cache_dir=Path(scratch) / "d",
                                llm=LoggedLLM(LLM(), calls, "damage check (one question per item)"),
                                examples=examples)
    else:
        sam = get_sam_client()
        checker = get_damage_checker(packing_list, final.kit_name, examples)
    damage_cal = read_json(str(run_dir / "damage_calibration.json")) or {}
    enabled = list(damage_cal.get("enabled", checker.questions))
    # A live result is kept for the session, so clicking a review button doesn't re-call the API.
    memo_key = ("live", cfg["dataset"], image_path, examples)
    if live and memo_key in st.session_state:
        result, dmg, saved_calls, sam = st.session_state[memo_key]
        calls.calls.extend(saved_calls)
    else:
        try:
            with st.spinner("Finding parts with SAM 3.1..."):
                result = run_program(final, fetch_segments(final, image_path, sam))
            with st.spinner("Asking Muse Spark about damage..."):
                dmg = checker.inspect(image_path)
        except Exception as exc:
            st.error(f"Inspection failed: {exc}")
            st.stop()
        if live:
            st.session_state[memo_key] = (result, dmg, list(calls.calls), sam)
    flags = damaged(dmg, enabled)
    checks = {c.id: c for c in final.checks}
    verdict, _ = triage(result.checks, flags)
    failed = [describe_result(checks.get(c.check_id), c.value, c.message)
              for c in result.checks if not c.passed]
    failed += [describe_question(q, True) + " (Muse Spark)" for q in flags]
    if verdict == "FAIL":
        st.error("## ❌ Reject\n" + "  \n".join(failed))
    elif verdict == "REVIEW":
        st.warning("## 👀 Review: a person should look\n" + "  \n".join(failed) + "  \n*Only a "
                   "borderline measurement or the model's judgement flagged this kit.*")
    else:
        st.success("## ✅ Pass")

    image = PILImage.open(image_path).convert("RGB")
    a, b = st.columns(2)
    a.image(image, caption="Photo", width="stretch")
    b.image(render(image, result), caption="What SAM found", width="stretch")
    b.markdown("".join(chip(f"{part.replace('_', ' ')} × {n}", f"rgb{tuple(rgb)}", "#fff")
                       for part, rgb, n in legend(result)), unsafe_allow_html=True)

    a, b = st.columns(2)
    a.subheader("Measured (SAM 3.1 + code)")
    for c in result.checks:
        a.markdown(f"{'✅' if c.passed else '❌'} "
                   f"{describe_result(checks.get(c.check_id), c.value, c.message)}")
    b.subheader("Looked at (Muse Spark)")
    for q in checker.questions:
        if q in enabled:
            b.markdown(f"{'❌' if q in flags else '✅'} {describe_question(q, q in flags)}")
        else:
            b.markdown(f"<span style='color:#999'>➖ {label(q.removesuffix('_damaged'))} "
                       f"damage: not asked, it fired on good kits</span>", unsafe_allow_html=True)
    if flags:
        b.caption(f"Model's notes: {dmg.evidence}")

    if verdict == "REVIEW":
        key = image_key(image_path)
        prior = review.load(REVIEW_LOG).get(key)
        st.subheader("Your call")
        if prior:
            st.info(f"Decided {prior['time']}: **{prior['decision']}**"
                    + (f" by {prior['reviewer']}" if prior["reviewer"] else "")
                    + (f" · {prior['note']}" if prior["note"] else "") + ". You can change it.")
        with st.form(f"review-{key}", clear_on_submit=True):
            note = st.text_input("Note (optional)", placeholder="e.g. chips are just broken, fine")
            reviewer = st.text_input("Reviewer (optional)")
            ok, reject = st.columns(2)
            pass_clicked = ok.form_submit_button("✅ Pass this kit", width="stretch")
            fail_clicked = reject.form_submit_button("❌ Reject this kit", width="stretch")
        if pass_clicked or fail_clicked:
            entry = review.record(REVIEW_LOG, key, "PASS" if pass_clicked else "FAIL",
                                  kit=cfg["dataset"], flags=[*flags, *(c.check_id for c in result.checks
                                                   if not c.passed)],
                                  note=note, reviewer=reviewer)
            st.success(f"Saved: {entry['decision']}. Logged to `runs/reviews.jsonl`.")

    # Reviewer decisions feed back in as labelled example photos for the damage check.
    stats = review.tally(review.load(REVIEW_LOG), cfg["dataset"], checker.questions)
    reviewed = {q: s for q, s in stats.items() if s["passed"] + s["rejected"]}
    with st.expander(f"What reviewers taught it ({len(examples)} example photo"
                     f"{'' if len(examples) == 1 else 's'} in use)"):
        st.caption("Reviewed kits go to Muse Spark with every damage check, before the photo it "
                   "inspects, as labelled examples: a kit a reviewer passed shows what counts as "
                   f"fine here, a rejected kit shows real damage. Newest first, up to "
                   f"{review.PER_QUESTION} passed and 1 rejected kit per question, "
                   f"{review.MAX_EXAMPLES} in all; the kit being inspected is never its own example. "
                   "Nothing is retrained and no question is switched off.")
        if not reviewed:
            st.write("No reviewer decisions on this kit yet.")
        for q, s in reviewed.items():
            st.markdown(f"**{label(q.removesuffix('_damaged'))} damage**: flagged "
                        f"{s['passed'] + s['rejected']} reviewed kits; reviewers passed "
                        f"{s['passed']}, rejected {s['rejected']}")
        if examples:
            for col, e in zip(st.columns(len(examples)), examples):
                col.image(e.image, width="stretch", caption=(
                    f"{'✅ passed' if e.decision == 'PASS' else '❌ rejected'}: "
                    + ", ".join(label(f.removesuffix('_damaged')) for f in e.flags)
                    + (f" · “{e.note}”" if e.note else "")))

    if baseline_on:
        st.subheader("Muse Spark alone: photo + packing list, no measuring")
        meta = read_json(str(ROOT / "runs" / cfg["baseline_report"] / "report.json")) or {}
        baseline = get_baseline(packing_list, cfg["dataset"], tuple(meta.get("references", [])),
                                meta.get("hint", ""))
        if live:
            from inspec.baseline import VisionBaseline
            from inspec.llm import LLM

            baseline = VisionBaseline(packing_list, references=baseline.references,
                                      hint=meta.get("hint", ""), cache_dir=Path(scratch) / "b",
                                      llm=LoggedLLM(LLM(), calls, "vision-only baseline"))
        with st.spinner("Asking Muse Spark..."):
            alone = baseline.inspect(image_path)
        (st.error if alone.failures() else st.success)(
            f"**{'Reject' if alone.failures() else 'Pass'}.** {alone.reason}")
        if not live:
            st.caption("This is the answer recorded in the evaluation run. Asked again, the model "
                       "can answer differently; turn on live calls to ask it now.")
        st.caption(" · ".join(f"{c.part}: saw {c.seen}, expected {c.expected}"
                              for c in alone.counts))

    if live:
        show_calls(calls, sam)

# 4. Results: the same three tables as the README, read from the same run files.
st.header("4 · Results on held-out test kits")
ins = (read_json(str(ROOT / "runs" / cfg["inspec_report"] / "report.json")) or {}).get("splits")
base = (read_json(str(ROOT / "runs" / cfg["baseline_report"] / "report.json")) or {}).get("splits")
three_way = read_json(str(ROOT / "runs" / f"{cfg['inspec_report']}-triage" / "triage.json"))
taught = read_json(str(ROOT / "runs" / f"{cfg['inspec_report']}-examples" / "review_eval.json"))
ROWS = [("Wrong parts, sizes or amounts caught", "test/logical_anomalies"),
        ("Damaged or contaminated caught", "test/structural_anomalies"),
        ("Good kits flagged by mistake", "test/good")]
if ins and base:
    def cell(splits: dict, split: str, program: str) -> str:
        return f"{splits[split]['programs'][program]['flagged']} / {splits[split]['images']}"

    st.caption("Test photos from MVTec LOCO AD that weren't used while building Inspec. \"Muse "
               "Spark alone\" asks Muse Spark directly, with the photo, the packing list and 3 "
               "photos of good kits.")
    st.table({"": [r for r, _ in ROWS],
              "Inspec": [cell(ins, s, "given+damage") for _, s in ROWS],
              "Muse Spark alone": [cell(base, s, "vision_baseline") for _, s in ROWS]})
else:
    st.info("Result reports not found in runs/.")

if three_way:
    st.subheader("Pass, review or reject")
    st.caption("Rejected: a count is wrong or a measurement is clearly out of range. Review: only "
               "the model's damage judgement, or a measurement within 3% of its limit.")
    kinds = [("Good kits", "test/good"), ("Wrong parts, sizes or amounts", "test/logical_anomalies"),
             ("Damaged or contaminated", "test/structural_anomalies")]
    st.table({"": [k for k, _ in kinds],
              **{col: [three_way[s].get(v, 0) for _, s in kinds]
                 for col, v in (("Reject", "FAIL"), ("Review", "REVIEW"), ("Pass", "PASS"))}})

if taught:
    def caught(cfg_name: str, kind: str) -> str:
        splits = [v for k, v in taught["splits"].items() if k.startswith(kind)]
        n = sum(v["images"] for v in splits)
        hit = (sum(v[cfg_name].get("REVIEW", 0) + v[cfg_name].get("FAIL", 0) for v in splits))
        return f"{hit} / {n}"

    st.subheader("Learning from reviewers")
    st.caption("A simulated reviewer passed the good training kits that were wrongly flagged; "
               "those became example photos. Same test kits.")
    rows = [("Good kits flagged by mistake", "test/good"),
            ("Damaged or contaminated caught", "test/structural_anomalies")]
    st.table({"": [r for r, _ in rows],
              "Without examples": [caught("without", k) for _, k in rows],
              "With examples": [caught("with", k) for _, k in rows]})
st.caption("Significance tests and how the test set was used: docs/benchmarks.md.")

st.divider()
st.caption("Kit images: MVTec LOCO AD (Bergmann et al.), CC BY-NC-SA 4.0. Models: Muse Spark and "
           "SAM 3.1 via the Meta Model API. Code: github.com/Mallard64/inspec")
