from inspec.concepts import ConceptIdeas, expected_range, repair_concepts
from inspec.llm import Generation
from inspec.schema import CheckProgram

PROGRAM = CheckProgram.model_validate({
    "kit_name": "box",
    "parts": [{"id": "nectarine", "concept": "nectarine"}, {"id": "almond", "concept": "almond"},
              {"id": "long_screw", "concept": "screw"}, {"id": "short_screw", "concept": "screw"}],
    "checks": [
        {"id": "n", "type": "count", "part": "nectarine", "min": 1, "max": 1},
        {"id": "a", "type": "count", "part": "almond", "min": 1},
        {"id": "l", "type": "count", "part": "long_screw", "min": 1, "max": 1},
        {"id": "s", "type": "count", "part": "short_screw", "min": 1, "max": 1},
    ],
})



class FakeSam:
    """Number of instances SAM returns per concept, the same on every image except where noted."""
    counts = {"nectarine": [0, 1, 0, 1], "apple": [1, 1, 1, 1], "fruit": [5, 5, 5, 5],
              "almond": [7, 9, 6, 8], "screw": [2, 2, 2, 2]}

    def __init__(self):
        self.calls = []

    def segment_text(self, image, concept):
        self.calls.append(concept)
        return str(self.counts.get(concept, [0] * 4)[int(image.stem)])


class FakeLLM:
    def __init__(self):
        self.calls = 0

    def generate(self, instructions, content, out_type):
        self.calls += 1
        assert "nectarine" in content[0]["text"]
        return Generation(ConceptIdeas(alternatives=["fruit", "Apple", "peach"]), 1)


def test_expected_range_sums_shared_concepts_and_bulk_is_open():
    assert expected_range(PROGRAM, "screw") == (2, 2)
    assert expected_range(PROGRAM, "almond") == (1, float("inf"))


def test_weak_concept_is_replaced_by_the_best_fitting_alternative(tmp_path, monkeypatch):
    import inspec.concepts as concepts
    monkeypatch.setattr(concepts, "parse_sam_output", lambda text: [None] * int(text))
    monkeypatch.setattr(concepts, "_image_content", lambda p: {"type": "input_image"})
    images = [tmp_path / f"{i}.png" for i in range(4)]
    llm = FakeLLM()
    fixed, repairs = repair_concepts(PROGRAM, images, sam=FakeSam(), llm=llm, log=lambda _: None)
    assert [p.concept for p in fixed.parts] == ["apple", "almond", "screw", "screw"]
    assert llm.calls == 1  # almond and screw are always found, so only nectarine is repaired
    [r] = repairs
    assert r.original == "nectarine" and r.chosen == "apple"
    fits = {p.concept: p.fits for p in r.probes}
    assert fits == {"nectarine": 0.5, "fruit": 0.0, "apple": 1.0, "peach": 0.0}
