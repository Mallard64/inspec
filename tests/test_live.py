from inspec.live import CallLog, LoggedLLM, LoggedSam


class FakeSam:
    model = "sam-3.1"

    def segment_text(self, image_path, concept):
        return f"{concept}@{image_path}"


class FakeLLM:
    model = "muse-spark-1.3"

    def generate(self, instructions, content, out_type, **kwargs):
        return (instructions, kwargs)


def test_calls_are_forwarded_and_logged():
    log = CallLog()
    sam = LoggedSam(FakeSam(), log)
    assert sam.segment_text("data/x/029.png", "screw") == "screw@data/x/029.png"
    assert sam.model == "sam-3.1"
    llm = LoggedLLM(FakeLLM(), log, "compile")
    assert llm.generate("i", [], dict, validate=None) == ("i", {"validate": None})
    assert [(c.model, c.what) for c in log.calls] == [
        ("sam-3.1", '"screw" in 029.png'), ("muse-spark-1.3", "compile")]
    assert all(c.seconds >= 0 for c in log.calls)


def test_api_calls_count_only_since_wrapping():
    sam = FakeSam()
    sam.api_calls = 5
    logged = LoggedSam(sam, CallLog())
    sam.api_calls = 8
    assert logged.api_calls == 3
