"""Model client with record and replay (T1, T2, A3).

OpenAI-compatible chat completions with JSON-schema structured output, served here by a local llama-server
(llama.cpp, behind llama-swap) running gpt-oss. Any OpenAI-compatible server or hosted provider can replace it
through the LLM_* settings in shared.config. Every call is written to <run_dir>/llm/<call_id>.json: request, raw response, usage.
In replay mode the same request hash is looked up in a recorded run and no network call is made,
so tests and the eval are deterministic and need no server.
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TypeVar

import httpx
from pydantic import BaseModel

from shared.config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, LLM_REASONING_EFFORT, LLM_TIMEOUT_S, PROMPT_VERSION, PROMPTS_DIR

T = TypeVar("T", bound=BaseModel)


class ReplayMiss(RuntimeError):
    pass


def load_prompt(name: str, version: str = PROMPT_VERSION) -> str:
    return (PROMPTS_DIR / version / f"{name}.md").read_text()


class LLMClient:
    def __init__(self, run_dir: Path, model: str = LLM_MODEL, prompt_version: str = PROMPT_VERSION,
                 replay_dir: Path | None = None, base_url: str = LLM_BASE_URL, temperature: float = 0.0):
        self.run_dir = run_dir
        self.llm_dir = run_dir / "llm"
        self.llm_dir.mkdir(parents=True, exist_ok=True)
        self.model = model
        self.prompt_version = prompt_version
        self.temperature = temperature
        self.base_url = base_url.rstrip("/")
        self.replay: dict[str, dict] | None = None
        if replay_dir is not None:
            self.replay = {}
            for f in sorted((replay_dir / "llm").glob("*.json")):
                rec = json.loads(f.read_text())
                self.replay[rec["request_hash"]] = rec
        self.calls: list[str] = []

    # --- public ------------------------------------------------------------------------

    def complete(self, call_id: str, system: str, user: str, schema: type[T], sample: int = 0,
                 temperature: float | None = None, max_tokens: int = 2000) -> tuple[T, str]:
        """One structured-output call. Returns (parsed object, call_id). Recorded, or replayed."""
        temp = self.temperature if temperature is None else temperature
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        json_schema = schema.model_json_schema()
        body = {
            "model": self.model, "temperature": temp, "max_tokens": max_tokens, "messages": messages,
            "response_format": {"type": "json_schema", "json_schema": {"name": schema.__name__, "strict": True, "schema": _strictify(json_schema)}},
        }
        if LLM_REASONING_EFFORT:  # llama.cpp's chat-template argument for gpt-oss; other servers may reject the field
            body["chat_template_kwargs"] = {"reasoning_effort": LLM_REASONING_EFFORT}
        if sample:
            body["seed"] = 1000 + sample
        req_hash = hashlib.sha256(json.dumps({"model": self.model, "prompt_version": self.prompt_version, "sample": sample,
                                              "messages": messages, "schema": json_schema, "temperature": temp}, sort_keys=True).encode()).hexdigest()
        full_id = f"{call_id}{'-s' + str(sample) if sample else ''}-{req_hash[:8]}"
        if self.replay is not None:
            rec = self.replay.get(req_hash)
            if rec is None:
                raise ReplayMiss(f"no recorded response for {full_id}")
            content = rec["response_content"]
        else:
            content, raw, elapsed = self._post(body)
            rec = {"call_id": full_id, "model": self.model, "prompt_version": self.prompt_version, "sample": sample,
                   "temperature": temp, "request_hash": req_hash, "messages": messages, "schema": json_schema,
                   "response_content": content, "usage": raw.get("usage"), "served_model": raw.get("model"),
                   "elapsed_s": round(elapsed, 2), "created_at": datetime.now(timezone.utc).isoformat()}
        (self.llm_dir / f"{full_id}.json").write_text(json.dumps(rec, indent=2, ensure_ascii=False) + "\n")
        self.calls.append(full_id)
        parsed = schema.model_validate_json(content)
        return parsed, full_id

    # --- internals ---------------------------------------------------------------------

    def _post(self, body: dict) -> tuple[str, dict, float]:
        t0 = time.time()
        with httpx.Client(timeout=LLM_TIMEOUT_S) as client:
            r = client.post(f"{self.base_url}/chat/completions", json=body,
                            headers={"Authorization": f"Bearer {LLM_API_KEY}", "Content-Type": "application/json"})
        r.raise_for_status()
        raw = r.json()
        msg = raw["choices"][0]["message"]
        content = msg.get("content") or ""
        return content, raw, time.time() - t0


def _strictify(schema: dict) -> dict:
    """Make a Pydantic JSON schema acceptable to strict structured-output grammars: no extra keys anywhere."""
    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                node.setdefault("additionalProperties", False)
                if "properties" in node:
                    node["required"] = list(node["properties"].keys())
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    walk(schema)
    return schema
