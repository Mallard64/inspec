"""Record model calls so the demo can show them: which model, what was asked, how long it took.

``LoggedSam`` and ``LoggedLLM`` wrap a SamClient / LLM and forward every call unchanged. Point the
wrapped client at an empty cache directory and every call goes to the Meta Model API.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Call:
    model: str
    what: str
    seconds: float


@dataclass
class CallLog:
    calls: list[Call] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def add(self, model: str, what: str, start: float) -> None:
        with self._lock:
            self.calls.append(Call(model, what, time.perf_counter() - start))


class LoggedSam:
    def __init__(self, sam, log: CallLog) -> None:
        self.sam, self.log = sam, log
        self._start = getattr(sam, "api_calls", 0)

    @property
    def api_calls(self) -> int:
        """Requests that went to the API since this wrapper was made (the rest were cached)."""
        return getattr(self.sam, "api_calls", 0) - self._start

    def segment_text(self, image_path, concept: str) -> str:
        start = time.perf_counter()
        out = self.sam.segment_text(image_path, concept)
        self.log.add(self.sam.model, f'"{concept}" in {Path(image_path).name}', start)
        return out

    def __getattr__(self, name):
        return getattr(self.sam, name)


class LoggedLLM:
    def __init__(self, llm, log: CallLog, task: str) -> None:
        self.llm, self.log, self.task = llm, log, task

    def generate(self, *args, **kwargs):
        start = time.perf_counter()
        out = self.llm.generate(*args, **kwargs)
        self.log.add(self.llm.model, self.task, start)
        return out

    def __getattr__(self, name):
        return getattr(self.llm, name)
