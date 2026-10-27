"""Model backends. Ollama for real runs; a scripted fake for tests and offline demos."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Callable


class LLMError(RuntimeError):
    pass


class LLM:
    model_id = "none"

    def chat(self, messages: list[dict], schema: dict) -> dict:  # pragma: no cover - interface
        raise NotImplementedError

    def config(self) -> dict:
        return {}


class Ollama(LLM):
    """Ollama /api/chat with a JSON schema in `format` (structured outputs)."""

    def __init__(self, model: str | None = None, host: str | None = None, num_ctx: int | None = None,
                 temperature: float = 0.0, seed: int = 7, timeout: float = 600):
        self.model_id = model or os.environ.get("LW_MODEL", "gemma4:e4b")
        self.host = (host or os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")).rstrip("/")
        if not self.host.startswith("http"):
            self.host = "http://" + self.host
        self.num_ctx = num_ctx or int(os.environ.get("LW_NUM_CTX", "32768"))
        self.temperature = temperature
        self.seed = seed
        self.timeout = timeout

    def config(self) -> dict:
        return {"num_ctx": self.num_ctx, "temperature": self.temperature, "seed": self.seed}

    def chat(self, messages: list[dict], schema: dict) -> dict:
        body = {
            "model": self.model_id,
            "messages": messages,
            "format": schema,
            "stream": False,
            "options": {"temperature": self.temperature, "seed": self.seed, "num_ctx": self.num_ctx},
        }
        req = urllib.request.Request(f"{self.host}/api/chat", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                data = json.loads(r.read())
        except urllib.error.URLError as e:
            raise LLMError(f"cannot reach Ollama at {self.host}: {e}") from e
        content = data.get("message", {}).get("content", "")
        try:
            out = json.loads(content)
        except json.JSONDecodeError as e:
            raise LLMError(f"model returned invalid JSON: {content[:200]!r}") from e
        if data.get("prompt_eval_count") and data["prompt_eval_count"] >= self.num_ctx - 64:
            raise LLMError(f"prompt filled the whole context ({self.num_ctx}); raise LW_NUM_CTX")
        return out


class Scripted(LLM):
    """Returns canned responses; used by tests and the offline demo."""

    model_id = "scripted"

    def __init__(self, respond: Callable[[list[dict], dict], dict]):
        self.respond = respond
        self.calls: list[list[dict]] = []

    def chat(self, messages: list[dict], schema: dict) -> dict:
        self.calls.append(messages)
        return self.respond(messages, schema)
