from inspec.damage import (DamageChecker, calibrate_damage, damaged, packing_items, questions,
                           report_type)
from inspec.llm import Generation

ITEMS = ["tangerines", "almonds"]
Report = report_type(ITEMS)


def report(**flags):
    base = {q: False for q in questions(Report)}
    return Report(**{**base, **flags}, evidence="")


class FakeLLM:
    model = "fake"

    def __init__(self, value):
        self.value, self.calls = value, 0

    def generate(self, instructions, content, out_type):
        self.calls += 1
        assert "almonds_damaged: any of the almonds" in instructions
        assert content[1]["type"] == "input_image"
        return Generation(out_type(**self.value.model_dump()), 1)


def test_packing_items_drop_amounts():
    assert packing_items("2 tangerines, 1 nectarine, granola, banana chips, almonds") == [
        "tangerines", "nectarine", "granola", "banana chips", "almonds"]
    assert packing_items("1 long screw, 1 short screw, 2 nuts and 2 washers") == [
        "long screw", "short screw", "nuts", "washers"]


def test_one_damage_question_per_item():
    assert questions(Report) == ["container_damaged", "tangerines_damaged", "almonds_damaged",
                                 "item_discoloured", "foreign_object"]


def test_inspect_caches_by_image(tmp_path):
    image = tmp_path / "kit.png"
    image.write_bytes(b"\x89PNG fake")
    llm = FakeLLM(report(container_damaged=True))
    checker = DamageChecker("2 tangerines, almonds", llm=llm, cache_dir=tmp_path / "cache")
    assert checker.inspect(image).flags() == {"container_damaged"}
    assert checker.inspect_many([image])[str(image)].container_damaged
    assert llm.calls == 1


def test_calibration_switches_off_only_the_noisy_item():
    good = {f"{i}.png": report() for i in range(60)}
    for i in range(3):
        good[f"{i}.png"] = report(almonds_damaged=True)
    cal = calibrate_damage(good)
    assert cal["false_alarms"]["almonds_damaged"] == 3
    assert "almonds_damaged" not in cal["enabled"] and "tangerines_damaged" in cal["enabled"]
    assert damaged(report(almonds_damaged=True, tangerines_damaged=True),
                   cal["enabled"]) == ["tangerines_damaged"]


def test_examples_go_before_the_kit_and_key_the_cache(tmp_path):
    from inspec.damage import Example

    kit, fine = tmp_path / "kit.png", tmp_path / "fine.png"
    kit.write_bytes(b"\x89PNG kit")
    from PIL import Image

    Image.new("RGB", (2000, 1000), "white").save(fine)
    seen = []

    class Recorder(FakeLLM):
        def generate(self, instructions, content, out_type):
            seen.append((instructions, content))
            return super().generate(instructions, content, out_type)

    llm = Recorder(report())
    plain = DamageChecker("2 tangerines, almonds", llm=llm, cache_dir=tmp_path / "c")
    taught = DamageChecker("2 tangerines, almonds", llm=llm, cache_dir=tmp_path / "c", examples=[
        Example(str(fine), ("almonds_damaged",), "PASS", "broken almonds are normal")])
    plain.inspect(kit)
    taught.inspect(kit)
    assert llm.calls == 2  # examples change the request, so no stale cache hit
    instructions, content = seen[1]
    assert "reviewer judged it FINE" in instructions and "broken almonds are normal" in instructions
    assert [c["type"] for c in content] == ["input_text", "input_image", "input_text", "input_image"]
    assert content[-2]["text"] == "Inspect this kit."
    assert "Example" not in seen[0][0]
    assert content[1]["image_url"].startswith("data:image/jpeg")  # examples are shrunk
