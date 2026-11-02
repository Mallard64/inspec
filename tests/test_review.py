import pytest

from inspec.review import load, pick_examples, record, tally

BB = "breakfast_box"


def test_missing_log_is_empty(tmp_path):
    assert load(tmp_path / "none.jsonl") == {}


def test_latest_decision_wins(tmp_path):
    log = tmp_path / "r" / "reviews.jsonl"
    record(log, "breakfast_box/test/good/010.png", "FAIL", kit=BB, flags=["banana_chips_damaged"])
    record(log, "breakfast_box/test/good/010.png", "PASS", kit=BB, flags=["banana_chips_damaged"],
           note=" chips are fine ")
    record(log, "screw_bag/test/good/001.png", "PASS", kit="screw_bag", flags=["washers_damaged"])
    latest = load(log)
    assert len(latest) == 2
    assert latest["breakfast_box/test/good/010.png"]["decision"] == "PASS"
    assert latest["breakfast_box/test/good/010.png"]["note"] == "chips are fine"
    assert len(log.read_text().splitlines()) == 3  # history kept


def test_rejects_unknown_decision(tmp_path):
    with pytest.raises(ValueError):
        record(tmp_path / "r.jsonl", "x.png", "REVIEW", kit=BB, flags=[])


def test_tally_counts_only_this_kit_and_known_questions(tmp_path):
    log = tmp_path / "r.jsonl"
    for i in range(3):
        record(log, f"{BB}/{i}.png", "PASS", kit=BB, flags=["banana_chips_damaged", "granola_area"])
    record(log, f"{BB}/9.png", "FAIL", kit=BB, flags=["nectarine_damaged"])
    record(log, "screw_bag/1.png", "PASS", kit="screw_bag", flags=["banana_chips_damaged"])
    stats = tally(load(log), BB, ["banana_chips_damaged", "nectarine_damaged"])
    assert stats == {"banana_chips_damaged": {"passed": 3, "rejected": 0},
                     "nectarine_damaged": {"passed": 0, "rejected": 1}}


def test_pick_examples_newest_first_capped_per_question(tmp_path):
    decisions = {
        "a": dict(image="a", kit=BB, decision="PASS", flags=["almonds_damaged"], time="1", note=""),
        "b": dict(image="b", kit=BB, decision="PASS", flags=["almonds_damaged"], time="2", note=""),
        "c": dict(image="c", kit=BB, decision="PASS", flags=["almonds_damaged"], time="3", note="ok"),
        "d": dict(image="d", kit=BB, decision="FAIL", flags=["almonds_damaged"], time="0", note=""),
        "e": dict(image="e", kit=BB, decision="PASS", flags=["granola_area"], time="4", note=""),
        "f": dict(image="f", kit="screw_bag", decision="PASS", flags=["almonds_damaged"], time="5",
                  note=""),
        "g": dict(image="gone", kit=BB, decision="PASS", flags=["nectarine_damaged"], time="6",
                  note=""),
    }
    picked = pick_examples(decisions, BB, ["almonds_damaged", "nectarine_damaged"],
                           lambda key: None if key == "gone" else f"/data/{key}.png")
    # newest two passes for almonds (c, b), then the one rejection (d); e has no damage flag,
    # f is another kit, g's photo is gone
    assert [(e.image, e.decision, e.note) for e in picked] == [
        ("/data/c.png", "PASS", "ok"), ("/data/b.png", "PASS", ""), ("/data/d.png", "FAIL", "")]
    assert len(pick_examples(decisions, BB, ["almonds_damaged"], lambda k: k, max_total=1)) == 1
