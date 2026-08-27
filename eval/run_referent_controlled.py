"""Run the isolated referent probe. Does not modify production code."""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from eval.referent_controlled import (  # noqa: E402
    falsifiers,
    mock_wrong_llm,
    print_summary,
    run_suite,
    write_results,
)


def main() -> None:
    out_dir = os.path.join(ROOT, "eval", "out")
    mock = mock_wrong_llm()
    mock_rows = run_suite(mock, "mock")
    write_results(
        mock_rows,
        os.path.join(out_dir, "referent_controlled_mock.json"),
        os.path.join(out_dir, "referent_controlled_mock.csv"),
    )
    print("=== MOCK (deterministic; primary evidence) ===")
    print_summary(mock_rows)
    print("falsifiers:", falsifiers(mock_rows))

    try:
        from app.llm.ollama import OllamaLLM
        live = OllamaLLM()
        live_rows = run_suite(live, "ollama")
        write_results(
            live_rows,
            os.path.join(out_dir, "referent_controlled_ollama.json"),
            os.path.join(out_dir, "referent_controlled_ollama.csv"),
        )
        print("\n=== OLLAMA qwen2.5:1.5b (exploratory only) ===")
        print_summary(live_rows)
        print("falsifiers:", falsifiers(live_rows))
    except Exception as exc:
        print(f"\n=== OLLAMA skipped: {exc} ===")


if __name__ == "__main__":
    main()
