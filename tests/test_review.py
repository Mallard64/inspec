import pytest

from inspec.review import load, record, set_switched_off, suggest_off, switched_off, tally

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


def test_suggest_off_needs_enough_mostly_passed_decisions():
    stats = {"a": {"passed": 3, "rejected": 0},   # suggested
             "b": {"passed": 2, "rejected": 0},   # too few
             "c": {"passed": 4, "rejected": 2},   # reviewers often agree with it
             "d": {"passed": 4, "rejected": 1}}   # exactly 80%
    assert suggest_off(stats) == ["a", "d"]


def test_switch_off_and_back_on(tmp_path):
    path = tmp_path / "off.json"
    assert switched_off(path, BB) == set()
    set_switched_off(path, BB, "banana_chips_damaged", True)
    set_switched_off(path, "screw_bag", "washers_damaged", True)
    assert switched_off(path, BB) == {"banana_chips_damaged"}
    set_switched_off(path, BB, "banana_chips_damaged", False)
    assert switched_off(path, BB) == set()
    assert switched_off(path, "screw_bag") == {"washers_damaged"}
