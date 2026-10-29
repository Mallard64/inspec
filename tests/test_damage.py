from types import SimpleNamespace

from inspec.damage import DamageChecker, DamageReport, calibrate_damage, damaged
from inspec.llm import Generation


def report(**flags) -> DamageReport:
    base = dict(bag_torn=False, part_broken=False, part_discoloured=False, foreign_object=False)
    return DamageReport(**{**base, **flags}, evidence="")


class FakeLLM:
    model = "fake"

    def __init__(self, value):
        self.value, self.calls = value, 0

    def generate(self, instructions, content, out_type):
        self.calls += 1
        assert "1 nut" in instructions and content[1]["type"] == "input_image"
        return Generation(self.value, 1)


def test_inspect_caches_by_image(tmp_path):
    image = tmp_path / "kit.png"
    image.write_bytes(b"\x89PNG fake")
    llm = FakeLLM(report(bag_torn=True))
    checker = DamageChecker("1 nut", llm=llm, cache_dir=tmp_path / "cache")
    assert checker.inspect(image).flags() == {"bag_torn"}
    assert checker.inspect_many([image])[str(image)].bag_torn
    assert llm.calls == 1


def test_calibration_switches_off_questions_that_fire_on_good_kits():
    good = {f"{i}.png": report() for i in range(60)}
    good["0.png"] = report(part_broken=True, bag_torn=True)
    good["1.png"] = report(part_broken=True)
    good["2.png"] = report(part_broken=True)
    cal = calibrate_damage(good)
    assert cal["false_alarms"]["part_broken"] == 3
    assert cal["enabled"] == ["bag_torn", "part_discoloured", "foreign_object"]
    assert damaged(report(part_broken=True, foreign_object=True), cal["enabled"]) == ["foreign_object"]
