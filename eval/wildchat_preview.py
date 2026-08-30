import json
from pathlib import Path

p = json.loads(Path("data/wildchat/longtail80.json").read_text(encoding="utf-8"))
turns = [c["n_user"] for c in p["conversations"]]
st = sorted(turns)
print(
    "n", len(turns),
    "median", st[len(st) // 2],
    "mean", round(sum(turns) / len(turns), 1),
    "p90", st[int(0.9 * len(turns))],
    "max", max(turns),
    "redacted", sum(1 for c in p["conversations"] if c["redacted"]),
)
lines = []
for i, c in enumerate(p["conversations"]):
    cid = str(c["conversation_hash"])[:20]
    lines.append(f"\n===== {i:02d} turns={c['n_user']} redacted={c['redacted']} id={cid} =====")
    for j, t in enumerate(c["user_texts"]):
        lines.append(f"U{j:02d} {t[:240]}")
out = Path("data/wildchat/preview.txt")
out.write_text("\n".join(lines), encoding="utf-8")
print("wrote", out, "lines", len(lines))
