"""Ollama adapter. Isolated: no other module imports this except wiring/experiments."""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request

import hashlib
import numpy as np

from app.config import SETTINGS


INVALID_RATIONALE_PREFIX = "invalid_provider_output"


def safe_proposal(reason: str) -> dict:
    """Do not guess a task. Low evidence so the gate can CLARIFY."""
    return {
        "task_id": None,
        "is_new_task": False,
        "confidence": 0.0,
        "referent": None,
        "rationale": f"{INVALID_RATIONALE_PREFIX}:{reason}",
    }


def parse_proposal_content(content: str) -> dict:
    if not content or not str(content).strip():
        return safe_proposal("empty_content")
    text = str(content).strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if fence:
        text = fence.group(1)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            return safe_proposal("malformed_json")
        try:
            parsed = json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            return safe_proposal("malformed_json")
    if not isinstance(parsed, dict):
        return safe_proposal("non_object_json")
    return sanitize_proposal(parsed)


def sanitize_proposal(parsed: dict) -> dict:
    task_id = parsed.get("task_id")
    if task_id is not None:
        task_id = str(task_id).strip() or None
        if task_id in ("null", "None", "none"):
            task_id = None
    try:
        confidence = float(parsed.get("confidence", 0.0))
    except (TypeError, ValueError):
        return safe_proposal("bad_confidence")
    confidence = min(1.0, max(0.0, confidence))
    is_new = parsed.get("is_new_task", False)
    if not isinstance(is_new, bool):
        is_new = str(is_new).lower() in ("1", "true", "yes")
    return {
        "task_id": task_id,
        "is_new_task": bool(is_new),
        "confidence": confidence,
        "referent": parsed.get("referent"),
        "rationale": str(parsed.get("rationale", "")),
    }


class OllamaLLM:
    """HTTP client for a local Ollama daemon. Embeddings stay hash-based (no extra model)."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        dim: int | None = None,
        timeout_s: float = 120.0,
    ) -> None:
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")).rstrip("/")
        self.model = model or os.getenv("OLLAMA_MODEL", "qwen2.5:1.5b")
        self.dim = dim or SETTINGS.EMBED_DIM
        self.timeout_s = timeout_s
        self.last_latency_s = 0.0
        self.last_prompt_eval_count = 0
        self.last_eval_count = 0
        self.last_proposal: dict | None = None
        self.last_propose_latency_s = 0.0

    def _post(self, path: str, payload: dict) -> dict:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.base_url + path,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                raw = resp.read()
        except urllib.error.URLError as exc:
            self.last_latency_s = time.perf_counter() - t0
            raise RuntimeError(f"ollama_unreachable:{exc}") from exc
        self.last_latency_s = time.perf_counter() - t0
        body = json.loads(raw.decode("utf-8"))
        self.last_prompt_eval_count = int(body.get("prompt_eval_count") or 0)
        self.last_eval_count = int(body.get("eval_count") or 0)
        return body

    def propose(self, prompt: str, schema: dict) -> dict:
        payload = {
            "model": self.model,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.0},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Return only a JSON object for task routing. "
                        "confidence is an uncalibrated self-report, not P(correct). "
                        "If you cannot identify a task, set task_id to null, "
                        "is_new_task to false, and confidence to 0. "
                        "Do not invent task ids that are not in OPEN TASKS."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt + "\nJSON schema:\n" + json.dumps(schema),
                },
            ],
        }
        try:
            body = self._post("/api/chat", payload)
        except Exception as exc:
            out = safe_proposal(type(exc).__name__)
            self.last_proposal = out
            self.last_propose_latency_s = self.last_latency_s
            return out
        content = (body.get("message") or {}).get("content", "")
        out = parse_proposal_content(content)
        self.last_proposal = out
        self.last_propose_latency_s = self.last_latency_s
        return out

    def generate(self, prompt: str) -> str:
        payload = {
            "model": self.model,
            "stream": False,
            "options": {"temperature": 0.2},
            "messages": [
                {"role": "system", "content": "Answer briefly using only the supplied task context."},
                {"role": "user", "content": prompt},
            ],
        }
        try:
            body = self._post("/api/chat", payload)
        except Exception as exc:
            return f"[ollama error] {type(exc).__name__}"
        return str((body.get("message") or {}).get("content") or "")

    def embed(self, texts: list[str]) -> list[np.ndarray]:
        out = []
        for t in texts:
            seed = int(hashlib.sha256(t.encode()).hexdigest(), 16) % (2 ** 32)
            v = np.random.default_rng(seed).standard_normal(self.dim).astype(np.float32)
            out.append(v / (np.linalg.norm(v) + 1e-9))
        return out
