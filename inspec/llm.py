"""Language-model access for the compiler, calibration and baseline.

Two OpenAI-compatible providers, picked with ``INSPEC_LLM_PROVIDER`` (default ``meta``):

- ``meta``: Muse Spark on the Meta Model API, with native structured output.
- ``baseten``: a model hosted on Baseten (e.g. Muse Spark Open), set by ``BASETEN_MODEL``.
  Baseten documents no structured output for Muse Spark Open, so we ask for JSON in plain text.

Either way, output is validated against a pydantic model. Invalid output is sent back to the model
with the error, and every failed attempt is kept so the repair is visible in logs and the UI.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Generic, TypeVar

from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class Provider:
    name: str
    base_url: str
    key_env: str
    model_env: str
    default_model: str | None
    structured_output: bool


PROVIDERS = {
    "meta": Provider("meta", "https://api.meta.ai/v1", "META_API_KEY", "META_LLM_MODEL",
                     "muse-spark-1.3", structured_output=True),
    "baseten": Provider("baseten", "https://inference.baseten.co/v1", "BASETEN_API_KEY",
                        "BASETEN_MODEL", None, structured_output=False),
}


class GenerationError(RuntimeError):
    """The model never produced valid output within the allowed attempts."""

    def __init__(self, message: str, errors: list[str]) -> None:
        super().__init__(message)
        self.errors = errors


@dataclass
class Generation(Generic[T]):
    value: T
    attempts: int
    errors: list[str] = field(default_factory=list)  # one per rejected attempt


def extract_json(text: str) -> str:
    """Return the outermost {...} block, tolerating code fences and surrounding prose."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object in model output")
    return text[start : end + 1]


class LLM:
    def __init__(self, provider: str | None = None, *, client: Any | None = None,
                 model: str | None = None) -> None:
        load_dotenv()
        name = provider or os.environ.get("INSPEC_LLM_PROVIDER", "meta")
        if name not in PROVIDERS:
            raise ValueError(f"unknown provider {name!r}; choose from {sorted(PROVIDERS)}")
        self.provider = PROVIDERS[name]
        self.model = model or os.environ.get(self.provider.model_env) or self.provider.default_model
        if not self.model:
            raise RuntimeError(f"set {self.provider.model_env} in .env to use provider {name!r}")
        if client is None:
            key = os.environ.get(self.provider.key_env)
            if not key:
                raise RuntimeError(f"set {self.provider.key_env} in .env to use provider {name!r}")
            import openai

            client = openai.OpenAI(api_key=key, base_url=self.provider.base_url)
        self.client = client

    def generate(self, instructions: str, content: list[dict], out_type: type[T], *,
                 max_attempts: int = 3,
                 validate: Callable[[T], None] | None = None) -> Generation[T]:
        """Ask for an ``out_type`` object; retry with the validation error on bad output.

        ``validate`` adds task rules beyond the schema: it raises ValueError to reject a value,
        and the message goes back to the model like a schema error.
        """
        messages: list[dict] = [{"role": "user", "content": content}]
        errors: list[str] = []
        for attempt in range(1, max_attempts + 1):
            raw = ""
            try:
                if self.provider.structured_output:
                    response = self.client.responses.parse(
                        model=self.model, instructions=instructions, input=messages,
                        text_format=out_type)
                    raw = response.output_text or ""
                    value = response.output_parsed
                    if value is None:
                        raise ValueError("model returned no structured output")
                else:
                    response = self.client.responses.create(
                        model=self.model, input=messages,
                        instructions=instructions + _json_instructions(out_type))
                    raw = response.output_text or ""
                    value = out_type.model_validate_json(extract_json(raw))
                if validate is not None:
                    validate(value)
                return Generation(value, attempt, errors)
            except ValueError as exc:  # pydantic ValidationError is a ValueError
                error = _short_error(exc)
                errors.append(error)
                if raw:
                    messages.append({"role": "assistant", "content": raw})
                messages.append({"role": "user", "content": [{"type": "input_text", "text":
                    f"Your output was rejected: {error}\nReturn the corrected JSON only."}]})
        raise GenerationError(f"no valid {out_type.__name__} after {max_attempts} attempts", errors)


def _json_instructions(out_type: type[BaseModel]) -> str:
    schema = json.dumps(out_type.model_json_schema(), separators=(",", ":"))
    return ("\n\nRespond with a single JSON object and nothing else, matching this JSON schema:\n"
            + schema)


def _short_error(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        return "; ".join(f"{'.'.join(map(str, e['loc'])) or 'root'}: {e['msg']}"
                         for e in exc.errors())[:1500]
    return str(exc)[:1500]


def cached_generate(llm: "LLM", instructions: str, content: list[dict], out_type: type[T],
                    images: list[Path], cache_dir: str | Path) -> T:
    """``llm.generate`` with the answer cached on disk by (model, instructions, image bytes).

    Used for per-image vision calls (damage check, baseline), so re-running an evaluation doesn't
    re-call the model. ``images`` are the images in ``content``; change the instructions to bust
    the cache."""
    parts = [llm.model, instructions] + [hashlib.sha256(Path(p).read_bytes()).hexdigest()
                                         for p in images]
    path = Path(cache_dir) / f"{hashlib.sha256(chr(10).join(parts).encode()).hexdigest()}.json"
    if path.exists():
        return out_type.model_validate_json(path.read_text())
    value = llm.generate(instructions, content, out_type).value
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(value.model_dump_json())
    tmp.replace(path)
    return value
