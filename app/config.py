import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    # routing weights (defaults, not proven optimal)
    W_LLM: float = 0.5
    W_SIM: float = 0.35
    W_REC: float = 0.15
    W_LOOP: float = 0.15
    LAMBDA: float = 0.15
    BASE_NEW: float = 0.30
    # gate thresholds
    TAU: float = 0.20        # absolute normalized-score floor
    THETA: float = 0.08      # margin / p_correct floor
    HYST: float = 0.05       # incumbent hysteresis
    COLD: int = 3            # turns before a paused task counts as RETURN
    # infra
    EMBED_DIM: int = 64
    SEED: int = 7
    EPS: float = 1e-9

    @staticmethod
    def from_env() -> "Settings":
        def f(name, default):
            v = os.getenv(name)
            return type(default)(v) if v is not None else default
        return Settings(
            W_LLM=f("CF_W_LLM", 0.5), W_SIM=f("CF_W_SIM", 0.35),
            W_REC=f("CF_W_REC", 0.15), W_LOOP=f("CF_W_LOOP", 0.15),
            LAMBDA=f("CF_LAMBDA", 0.15), BASE_NEW=f("CF_BASE_NEW", 0.30),
            TAU=f("CF_TAU", 0.20), THETA=f("CF_THETA", 0.08),
            HYST=f("CF_HYST", 0.05), COLD=f("CF_COLD", 3),
            EMBED_DIM=f("CF_EMBED_DIM", 64), SEED=f("CF_SEED", 7),
        )


SETTINGS = Settings.from_env()
NEW_ID = "__NEW__"
