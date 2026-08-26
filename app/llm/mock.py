import hashlib
import numpy as np

from app.config import SETTINGS


class MockLLM:
    """Deterministic, free LLM stand-in. Seeded embeddings; scriptable proposals."""

    def __init__(self, scripted: dict[str, dict] | None = None, dim: int | None = None):
        self.scripted = scripted or {}
        self.dim = dim or SETTINGS.EMBED_DIM

    @staticmethod
    def _extract_message(prompt: str) -> str:
        import re
        m = re.search(r'MESSAGE:\s*"(.*?)"', prompt, re.S)
        return m.group(1) if m else prompt

    def propose(self, prompt: str, schema: dict) -> dict:
        # Match scripts against the USER MESSAGE only, not the embedded task cards.
        msg = self._extract_message(prompt)
        for key, val in self.scripted.items():
            if key in msg:
                return val
        return {"task_id": None, "is_new_task": True, "confidence": 0.9,
                "referent": None, "rationale": "mock-default-new"}

    def generate(self, prompt: str) -> str:
        return "[mock answer] " + " ".join(prompt.split()[:12])

    def embed(self, texts: list[str]) -> list[np.ndarray]:
        out = []
        for t in texts:
            seed = int(hashlib.sha256(t.encode()).hexdigest(), 16) % (2 ** 32)
            v = np.random.default_rng(seed).standard_normal(self.dim).astype(np.float32)
            out.append(v / (np.linalg.norm(v) + 1e-9))
        return out
