"""Product demo: build snapshot + local HTTP serve.

  python -m eval.product_demo
  python -m eval.product_demo --serve

CONTROLLED SYNTHETIC ENGINEERING DEMO — not a natural-chat benchmark.
MockLLM. Offline. No Vertex / GCP / credentials / network.
"""

from __future__ import annotations

import argparse
import json
import sys
import webbrowser

from eval.product_demo.build import OUT, UI, build, public_demo_payload


def create_app(payload: dict | None = None):
    """FastAPI app for the local product demo (offline MockLLM snapshot)."""
    from fastapi import FastAPI
    from fastapi.responses import FileResponse, JSONResponse

    if payload is None:
        payload = build()
    public = public_demo_payload(payload)

    app = FastAPI(title="ContextFlow product demo")

    @app.get("/")
    def index():
        return FileResponse(UI)

    @app.get("/api/demo")
    def api_demo():
        return JSONResponse(public)

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "service": "contextflow-product-demo",
            "demo_only": True,
            "label": "CONTROLLED SYNTHETIC ENGINEERING DEMO",
            "natural_chat_benchmark": False,
            "llm": "mock",
            "network": False,
            "vertex": False,
            "gcp": False,
            "demo_ok": bool(payload.get("demo_ok")),
        }

    return app


def serve(
    host: str = "127.0.0.1",
    port: int = 8766,
    *,
    payload: dict | None = None,
    open_browser: bool = True,
) -> None:
    import uvicorn

    if payload is None:
        payload = build()
    app = create_app(payload)
    url = f"http://{host}:{port}/"

    # Clear, copy-pasteable launch banner (ASCII-safe for Windows consoles).
    print("", flush=True)
    print("=" * 60, flush=True)
    print("  ContextFlow PRODUCT DEMO", flush=True)
    print("  CONTROLLED SYNTHETIC ENGINEERING DEMO", flush=True)
    print("  NOT A NATURAL-CHAT BENCHMARK", flush=True)
    print("=" * 60, flush=True)
    print(f"  Open this URL:  {url}", flush=True)
    print("  Controls: RESET DEMO | PLAY SCENARIO | STEP", flush=True)
    print("  Offline MockLLM | no GCP | no Vertex | no credentials", flush=True)
    print("=" * 60, flush=True)
    print("", flush=True)
    sys.stdout.flush()

    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    uvicorn.run(app, host=host, port=port, log_level="warning")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="ContextFlow product demo (offline synthetic fixture).",
    )
    ap.add_argument("--serve", action="store_true", help="Serve one-window UI")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8766)
    ap.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not auto-open a browser tab",
    )
    args = ap.parse_args()
    payload = build()
    print(json.dumps({
        "checkpoint": payload["checkpoint"],
        "thesis": payload.get("thesis"),
        "demo_ok": payload.get("demo_ok"),
        "demo_error": payload.get("demo_error"),
        "frames": len(payload["frames"]),
        "fingerprint": payload.get("semantic_fingerprint"),
        "out": str(OUT),
        "disclaimer": payload["disclaimer"],
        "url": f"http://{args.host}:{args.port}/" if args.serve else None,
    }, indent=2), flush=True)
    if args.serve:
        if not payload.get("demo_ok", True):
            print("REFUSING TO SERVE: demo_ok=false — fix invariants first.", flush=True)
            return 1
        serve(
            args.host,
            args.port,
            payload=payload,
            open_browser=not args.no_browser,
        )
    return 0 if payload.get("demo_ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
