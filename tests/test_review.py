import pytest

from inspec.review import load, record


def test_missing_log_is_empty(tmp_path):
    assert load(tmp_path / "none.jsonl") == {}


def test_latest_decision_wins(tmp_path):
    log = tmp_path / "r" / "reviews.jsonl"
    record(log, "breakfast_box/test/good/010.png", "FAIL", flags=["banana_chips_damaged"])
    record(log, "breakfast_box/test/good/010.png", "PASS", flags=["banana_chips_damaged"],
           note=" chips are fine ")
    record(log, "screw_bag/test/good/001.png", "PASS", flags=["washers_damaged"])
    latest = load(log)
    assert len(latest) == 2
    assert latest["breakfast_box/test/good/010.png"]["decision"] == "PASS"
    assert latest["breakfast_box/test/good/010.png"]["note"] == "chips are fine"
    assert len(log.read_text().splitlines()) == 3  # history kept


def test_rejects_unknown_decision(tmp_path):
    with pytest.raises(ValueError):
        record(tmp_path / "r.jsonl", "x.png", "REVIEW", flags=[])
