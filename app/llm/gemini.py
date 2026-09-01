import os
import json
import numpy as np

from app.config import SETTINGS


class GeminiClient:
    """Only file that imports google-genai. Raises on missing key (no silent mock)."""

    GEN_MODEL = os.getenv("CF_GEN_MODEL", "gemini-2.0-flash")
    LITE_MODEL = os.getenv("CF_LITE_MODEL", "gemini-2.0-flash-lite")
    EMBED_MODEL = os.getenv("CF_EMBED_MODEL", "text-embedding-004")

    def __init__(self, api_key: str | None = None, use_vertex: bool | None = None):
        from google import genai  # local import keeps the dep isolated
        self._types_mod = __import__("google.genai", fromlist=["types"]).types
        key = api_key or os.getenv("GEMINI_API_KEY")
        use_vertex = use_vertex if use_vertex is not None else os.getenv("CF_USE_VERTEX") == "1"
        if use_vertex:
            # Vertex model region may differ from Cloud Run / Firestore region.
            loc = (
                os.getenv("CF_VERTEX_LOCATION")
                or os.getenv("GCP_REGION")
                or "us-central1"
            )
            self._client = genai.Client(
                vertexai=True,
                project=os.getenv("GCP_PROJECT"),
                location=loc,
            )
        else:
            if not key:
                raise RuntimeError("GEMINI_API_KEY not set and Vertex not enabled.")
            self._client = genai.Client(api_key=key)

    def propose(self, prompt: str, schema: dict) -> dict:
        r = self._client.models.generate_content(
            model=self.LITE_MODEL, contents=prompt,
            config=self._types_mod.GenerateContentConfig(
                temperature=0.2, response_mime_type="application/json",
                response_schema=schema))
        return json.loads(r.text)

    def generate(self, prompt: str) -> str:
        r = self._client.models.generate_content(
            model=self.GEN_MODEL, contents=prompt,
            config=self._types_mod.GenerateContentConfig(temperature=0.2))
        return r.text

    def embed(self, texts: list[str]) -> list[np.ndarray]:
        # Opt out of Vertex embeddings API for tiny smokes / cost control.
        if os.getenv("CF_EMBED_LOCAL") == "1":
            from app.llm.mock import MockLLM
            return MockLLM(dim=SETTINGS.EMBED_DIM).embed(texts)
        r = self._client.models.embed_content(model=self.EMBED_MODEL, contents=texts)
        return [np.array(e.values, dtype=np.float32) for e in r.embeddings]
