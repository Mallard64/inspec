from types import SimpleNamespace

import pytest

from inspec.compiler import compile_program
from inspec.llm import LLM, GenerationError, extract_json
from inspec.schema import CheckProgram

GOOD = {
    "kit_name": "screw bag",
    "parts": [{"id": "nut", "concept": "nut"}],
    "checks": [{"id": "nut_count", "type": "count", "part": "nut", "min": 2, "max": 2}],
}
BAD = {**GOOD, "parts": [{"id": "nut", "concept": "nut and washer"}]}


class FakeResponses:
    """Plays back a script of outputs; each item is a dict (JSON) or an Exception."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def _next(self, kwargs):
        self.calls.append(kwargs)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def parse(self, **kwargs):
        item = self._next(kwargs)
        return SimpleNamespace(output_text="{}", output_parsed=kwargs["text_format"].model_validate(item))

    def create(self, **kwargs):
        return SimpleNamespace(output_text=self._next(kwargs))


def make_llm(provider, script, monkeypatch):
    monkeypatch.setenv("BASETEN_MODEL", "muse-spark-open")
    fake = FakeResponses(script)
    return LLM(provider, client=SimpleNamespace(responses=fake)), fake


def test_structured_success_first_try(monkeypatch):
    llm, fake = make_llm("meta", [GOOD], monkeypatch)
    result = llm.generate("x", [], CheckProgram)
    assert result.attempts == 1 and result.errors == []
    assert fake.calls[0]["model"] == "muse-spark-1.3"


def test_structured_retries_with_validation_error(monkeypatch):
    llm, fake = make_llm("meta", [BAD, GOOD], monkeypatch)
    result = llm.generate("x", [], CheckProgram)
    assert result.attempts == 2 and len(result.errors) == 1
    feedback = fake.calls[1]["input"][-1]["content"][0]["text"]
    assert "rejected" in feedback and "noun phrase" in feedback


def test_plain_json_path_for_baseten(monkeypatch):
    import json
    text = "Sure!\n```json\n" + json.dumps(GOOD) + "\n```"
    llm, fake = make_llm("baseten", [text], monkeypatch)
    result = llm.generate("x", [], CheckProgram)
    assert result.value.parts[0].concept == "nut"
    assert fake.calls[0]["model"] == "muse-spark-open"
    assert "JSON schema" in fake.calls[0]["instructions"]


def test_gives_up_after_max_attempts(monkeypatch):
    llm, _ = make_llm("baseten", ["no json here"] * 3, monkeypatch)
    with pytest.raises(GenerationError) as info:
        llm.generate("x", [], CheckProgram)
    assert len(info.value.errors) == 3


def test_provider_configuration_errors(monkeypatch):
    monkeypatch.setattr("inspec.llm.load_dotenv", lambda: None)
    monkeypatch.delenv("BASETEN_MODEL", raising=False)
    monkeypatch.delenv("BASETEN_API_KEY", raising=False)
    with pytest.raises(ValueError):
        LLM("openai")
    with pytest.raises(RuntimeError, match="BASETEN_MODEL"):
        LLM("baseten")
    monkeypatch.setenv("BASETEN_MODEL", "m")
    with pytest.raises(RuntimeError, match="BASETEN_API_KEY"):
        LLM("baseten")


def test_extract_json():
    assert extract_json('noise {"a": {"b": 1}} trailing') == '{"a": {"b": 1}}'
    with pytest.raises(ValueError):
        extract_json("nothing")


def test_compile_program_sends_list_and_images(monkeypatch):
    llm, fake = make_llm("meta", [GOOD], monkeypatch)
    result = compile_program("2 nuts", kit_name="screw bag",
                             example_images=["tests/fixtures/sam/circles.png"], llm=llm)
    content = fake.calls[0]["input"][0]["content"]
    assert "2 nuts" in content[0]["text"] and "screw bag" in content[0]["text"]
    assert content[1]["image_url"].startswith("data:image/png;base64,")
    assert "SAM ignores size" in fake.calls[0]["instructions"]
    assert result.value.checks[0].id == "nut_count"


def test_compile_rejects_empty_list(monkeypatch):
    llm, _ = make_llm("meta", [], monkeypatch)
    with pytest.raises(ValueError):
        compile_program("  ", llm=llm)


def test_validate_hook_rejects_and_feeds_back(monkeypatch):
    two_nuts = {**GOOD, "checks": [{**GOOD["checks"][0], "min": 1}]}
    llm, fake = make_llm("meta", [two_nuts, GOOD], monkeypatch)

    def keep_counts(program):
        if program.checks[0].min != 2:
            raise ValueError("count checks must not change")

    result = llm.generate("x", [], CheckProgram, validate=keep_counts)
    assert result.attempts == 2 and result.errors == ["count checks must not change"]
    assert "must not change" in fake.calls[1]["input"][-1]["content"][0]["text"]
