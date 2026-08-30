"""Product demo: build snapshot + local HTTP serve.

  python -m eval.product_demo
  python -m eval.product_demo --serve

DEMO-READY / RESEARCH-PRODUCT CHECKPOINT — not production-ready.
CONTROLLED ADVERSARIAL ENGINEERING FIXTURE. MockLLM. $0. No Vertex.
"""

from __future__ import annotations

import argparse
import json

from eval.product_demo.build import OUT, UI, build


def serve(host: str = "127.0.0.1", port: int = 8766) -> None:
    from fastapi import FastAPI
    from fastapi.responses import FileResponse, JSONResponse
    import uvicorn

    build()
    app = FastAPI(title="ContextFlow product demo")

    @app.get("/")
    def index():
        return FileResponse(UI)

    @app.get("/api/demo")
    def api_demo():
        return JSONResponse(json.loads(OUT.read_text(encoding="utf-8")))

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "service": "contextflow-product-demo",
            "demo_only": True,
            "checkpoint": "DEMO-READY / RESEARCH-PRODUCT CHECKPOINT",
            "fixture": "CONTROLLED ADVERSARIAL ENGINEERING FIXTURE",
            "llm": "mock",
            "network": False,
        }

    print(f"Product demo → http://{host}:{port}/")
    print("DEMO-ONLY · MockLLM · synthetic fixture · not production-ready")
    uvicorn.run(app, host=host, port=port, log_level="warning")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--serve", action="store_true")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8766)
    args = ap.parse_args()
    payload = build()
    print(json.dumps({
        "checkpoint": payload["checkpoint"],
        "frames": len(payload["frames"]),
        "out": str(OUT),
        "disclaimer": payload["disclaimer"],
    }, indent=2))
    if args.serve:
        serve(args.host, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
