from inspec.baseline import BaselineVerdict, PartCount, VisionBaseline
from inspec.llm import Generation


def verdict(nuts_seen: int = 2, damage: bool = False) -> BaselineVerdict:
    return BaselineVerdict(counts=[PartCount(part="nut", expected=2, seen=nuts_seen)],
                           damage=damage, reason="")


class FakeLLM:
    model = "fake"

    def __init__(self, value):
        self.value, self.contents = value, []

    def generate(self, instructions, content, out_type):
        assert "2 nuts" in instructions
        self.contents.append(content)
        return Generation(self.value, 1)


def test_failures_split_counts_and_damage():
    assert verdict().failures() == []
    assert verdict(nuts_seen=3).failures() == ["counts"]
    assert verdict(nuts_seen=1, damage=True).failures() == ["counts", "damage"]


def test_references_go_first_and_are_part_of_the_cache_key(tmp_path):
    kit, ref = tmp_path / "kit.png", tmp_path / "ref.png"
    kit.write_bytes(b"\x89PNG kit")
    ref.write_bytes(b"\x89PNG ref")
    llm = FakeLLM(verdict())
    VisionBaseline("2 nuts", llm=llm, cache_dir=tmp_path / "c").inspect(kit)
    VisionBaseline("2 nuts", llm=llm, cache_dir=tmp_path / "c").inspect(kit)  # cached
    with_ref = VisionBaseline("2 nuts", llm=llm, references=[ref], cache_dir=tmp_path / "c")
    assert with_ref.inspect_many([kit])[str(kit)].failures() == []
    assert len(llm.contents) == 2
    types = [c["type"] for c in llm.contents[1]]
    assert types == ["input_text", "input_image", "input_text", "input_image"]
