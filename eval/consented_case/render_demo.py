"""Write a local HTML side-by-side from eval/out/consented/e2e.json. Human labels first."""

from __future__ import annotations

import html
import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[2] / "eval" / "out" / "consented" / "e2e.json"
HTML = Path(__file__).resolve().parents[2] / "eval" / "out" / "consented" / "demo.html"


def main() -> int:
    if not OUT.is_file():
        print("missing", OUT)
        return 2
    data = json.loads(OUT.read_text(encoding="utf-8"))
    parts = [
        "<!doctype html><meta charset=utf-8><title>ContextFlow working context</title>",
        "<style>body{font-family:Georgia,serif;max-width:1200px;margin:2rem auto;line-height:1.4}"
        "pre{white-space:pre-wrap;background:#111;color:#eee;padding:1rem;font-size:12px;font-family:ui-monospace,monospace}"
        ".grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:1rem}"
        ".pipe{background:#f4f1ea;padding:1rem 1.2rem;border-left:4px solid #333;margin:1rem 0}"
        ".warn{color:#8a1f1f;font-weight:bold}"
        "h2{margin-top:2.5rem}</style>",
        "<h1>Messy conversation → working context → continuation</h1>",
        "<p>Internal task ids are secondary. The story is which workstream is live.</p>",
        f"<p>status={html.escape(str(data.get('status')))} provider={html.escape(str(data.get('provider')))}</p>",
    ]
    for p in data.get("probes") or []:
        human = p.get("human") or {}
        ws = human.get("workstream") or p.get("short_description") or "workstream"
        loop = human.get("open_loop") or ""
        parts.append(f"<h2>{html.escape(str(ws))}</h2>")
        if loop:
            parts.append(f"<p>Open loop: <i>{html.escape(str(loop))}</i></p>")
        parts.append(
            "<div class=pipe>"
            "messy history → working memory → return → "
            "proposal (soft) → referent resolution → ACT / CLARIFY → "
            "reconstructed context → answer"
            "</div>"
        )
        parts.append(f"<p><b>User said</b> {html.escape(p.get('message') or '')}</p>")
        res = p.get("resolution") or {}
        parts.append(
            f"<p><b>Decision</b> {html.escape(str(res.get('transition')))}"
            f" — {html.escape(str(ws))}"
            f"<span style='color:#888'> (optional id {html.escape(str(res.get('predicted_task_id')))}"
            f" / {html.escape(str(res.get('predicted_referent_id')))})</span></p>"
        )
        if res.get("clarify_question"):
            parts.append(f"<p>CLARIFY: {html.escape(res['clarify_question'])}</p>")
        crit = (p.get("critical_failure") or {}).get("correct_referent_or_task_thin_context")
        if crit:
            parts.append(
                "<p class=warn>Critical production finding: right workstream, thin context. "
                "This is memory extraction, not routing.</p>"
            )
        rec = p.get("reconstruction") or {}
        miss = rec.get("missing") or {}
        if any(miss.get(k) for k in miss):
            parts.append("<p>Missing from reconstructed context: "
                         + html.escape(json.dumps(miss)) + "</p>")
        ans = p.get("answers") or {}
        parts.append("<div class=grid>")
        parts.append("<div><h3>Full history</h3><p>Everything so far.</p><pre>"
                     + html.escape(str(ans.get("full") or "")) + "</pre></div>")
        parts.append("<div><h3>Recent window</h3><p>Only the last messages.</p><pre>"
                     + html.escape(str(ans.get("recent") or "")) + "</pre></div>")
        parts.append(
            "<div><h3>ContextFlow working context</h3><pre>"
            + html.escape(str(rec.get("rendered") or "(asked to clarify)"))
            + "\n\n--- answer ---\n"
            + html.escape(str(ans.get("contextflow") or ""))
            + "</pre></div>"
        )
        parts.append("</div>")
    HTML.parent.mkdir(parents=True, exist_ok=True)
    HTML.write_text("\n".join(parts), encoding="utf-8")
    print(HTML)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
