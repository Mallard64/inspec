from inspec.executor import CheckResult
from inspec.triage import overshoot, triage


def count(passed=True, found=2):
    return CheckResult("nut_count", passed, found, (2, 2), [], f"nut_count: found {found}")


def length(values, passed=False):
    return CheckResult("short_screw_length", passed, values, (276, 308), [], "short_screw_length")


def test_overshoot_is_relative_to_the_crossed_limit():
    assert round(overshoot(length([313.4])), 4) == round(5.4 / 308, 4)
    assert round(overshoot(length([200.0, 300.0])), 4) == round(76 / 276, 4)
    assert overshoot(count(passed=False, found=3)) == 0.0


def test_three_way_verdict():
    assert triage([count()], []) == ("PASS", [])
    assert triage([count(), length([313.4])], [])[0] == "REVIEW"  # 1.75% over: borderline
    assert triage([count()], ["washers_damaged"]) == ("REVIEW", ["washers_damaged"])
    assert triage([count(), length([217.0])], [])[0] == "FAIL"  # 21% short
    verdict, reasons = triage([count(passed=False, found=1), length([313.4])], ["x"])
    assert verdict == "FAIL" and reasons == ["nut_count: found 1"]
