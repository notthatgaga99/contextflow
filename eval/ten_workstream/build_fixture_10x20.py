"""Build interleaved 10-workstream × ~20-turn density fixture (local MockLLM).

  python -m eval.ten_workstream.build_fixture_10x20
  python -m eval.ten_workstream.hop_density --fixture eval/ten_workstream/fixture_10x20.json

Does not retune the gate. Controlled adversarial fixture — not natural chat.
"""

from __future__ import annotations

import json
from pathlib import Path

DIR = Path(__file__).resolve().parent
OUT = DIR / "fixture_10x20.json"
PROBES_OUT = DIR / "probes_10x20.json"

# Per-hop deep arcs: establish → detail → correct → noise facts → revive cues
# Each list length target ~18–22; interleaver spreads them.
ARCS: dict[str, list[dict]] = {
    "A": [
        {"m": "JWT still returns 401 after refresh on the auth service.", "k": "fact", "t": "401 after refresh", "slot": None},
        # Revive/fact cues must uniquely hit A.loop1 ("401 after refresh") vs A.loop2 /
        # C/D 401 siblings — otherwise frozen referent lexical_tie → CLARIFY (not a gate retune).
        {"m": "On the auth service the access token TTL is 15 minutes for JWT 401 after refresh.", "k": "fact", "t": "access token TTL 15 minutes", "slot": "ttl"},
        {"m": "Auth cookies are httpOnly on the auth service for JWT 401 after refresh.", "k": "fact", "t": "httpOnly cookies", "slot": "cookie"},
        {"m": "Refresh endpoint is /auth/refresh on the auth service.", "k": "fact", "t": "refresh at /auth/refresh", "slot": "refresh_path"},
        {"m": "On the auth service, TTL is 5 minutes now, not 15, for JWT 401 after refresh.", "k": "fact", "t": "access token TTL 5 minutes", "slot": "ttl"},
        {"m": "Also rotate the signing key on the auth service.", "k": "fact", "t": "rotate signing key", "slot": "signing"},
        {"m": "Auth audience claim must be api.internal for JWT 401 after refresh.", "k": "constraint", "t": "aud=api.internal", "slot": "aud"},
        {"m": "Issuer is https://auth.example/issuer for JWT 401 after refresh.", "k": "fact", "t": "iss=https://auth.example/issuer", "slot": "iss"},
        {"m": "Clock skew tolerance is 30 seconds on auth for JWT 401 after refresh.", "k": "fact", "t": "clock skew 30s", "slot": "skew"},
        {"m": "Revoke old refresh family after key rotate on JWT auth.", "k": "decision", "t": "revoke refresh family", "slot": "revoke"},
        {"m": "go back to the JWT 401 after refresh on the auth service", "k": None, "t": None, "slot": None},
        {"m": "JWT 401 after refresh on the auth service still", "k": None, "t": None, "slot": None},
        {"m": "Auth service JWT 401 after refresh: keep 5 minute TTL after rotate.", "k": "fact", "t": "keep TTL 5 minutes", "slot": "ttl"},
        {"m": "Did we set aud=api.internal on the auth service for JWT 401 after refresh?", "k": None, "t": None, "slot": None},
        {"m": "Signing key rotation status on auth service?", "k": None, "t": None, "slot": None},
        {"m": "back to JWT refresh 401 — what is the TTL now?", "k": None, "t": None, "slot": None},
        {"m": "Auth skew still 30 seconds for JWT 401 after refresh?", "k": None, "t": None, "slot": None},
        {"m": "Confirm revoke refresh family after rotate on auth JWT 401.", "k": None, "t": None, "slot": None},
        {"m": "JWT still returns 401 after refresh on the auth service.", "k": None, "t": None, "slot": None},
        {"m": "Final check: JWT 401 after refresh — TTL 5 minutes and aud api.internal on the auth service", "k": None, "t": None, "slot": None},
    ],
    "B": [
        # Prefer B.loop1 ("CI failing on Docker step") over B.loop2 ("container healthcheck");
        # bare /healthz or cache-only lines lexical_tie / lexical_miss → CLARIFY or topic-align NEW.
        {"m": "CI is failing on the Docker step again.", "k": "fact", "t": "CI failing on Docker step", "slot": None},
        {"m": "We're using alpine as the builder image for the container.", "k": "decision", "t": "alpine", "slot": "builder"},
        {"m": "Docker healthcheck curls /healthz in CI.", "k": "fact", "t": "healthcheck /healthz", "slot": "health"},
        {"m": "Docker CI cache mount is /var/cache/ci for the failing Docker step.", "k": "fact", "t": "cache /var/cache/ci", "slot": "cache"},
        {"m": "Use debian slim, not alpine, as the builder image.", "k": "decision", "t": "debian slim", "slot": "builder"},
        {"m": "Multi-stage build copies from builder to runtime in Docker CI.", "k": "fact", "t": "multi-stage copy", "slot": "stages"},
        {"m": "Pin base digest for debian slim in CI.", "k": "constraint", "t": "pin debian slim digest", "slot": "pin"},
        {"m": "Docker step OOM was 2Gi — raise to 4Gi.", "k": "decision", "t": "memory 4Gi", "slot": "mem"},
        {"m": "back to CI failing on the Docker step", "k": None, "t": None, "slot": None},
        {"m": "CI failing on Docker step — debian slim builder image", "k": None, "t": None, "slot": None},
        {"m": "Is healthcheck still /healthz in Docker CI?", "k": None, "t": None, "slot": None},
        {"m": "CI failing on Docker step — memory limit 4Gi confirmed?", "k": None, "t": None, "slot": None},
        {"m": "Docker CI failing step multi-stage — runtime user nonroot.", "k": "constraint", "t": "runtime nonroot", "slot": "user"},
        {"m": "back to CI failing on the Docker step builder image choice", "k": None, "t": None, "slot": None},
        {"m": "Pin digest still required for debian slim on the failing Docker CI step?", "k": None, "t": None, "slot": None},
        {"m": "Docker CI failing step — cache path still /var/cache/ci?", "k": None, "t": None, "slot": None},
        {"m": "Revive CI failing on the Docker step — what builder are we on?", "k": None, "t": None, "slot": None},
        {"m": "Docker CI failing step — debian slim and 4Gi mem", "k": None, "t": None, "slot": None},
        {"m": "Confirm nonroot runtime on the CI failing Docker step.", "k": None, "t": None, "slot": None},
        {"m": "Final check: CI failing on Docker step — debian slim, pin digest, 4Gi", "k": None, "t": None, "slot": None},
    ],
    "C": [
        {"m": "The orders API returns 401 even with a valid token.", "k": "fact", "t": "orders API 401 with valid token", "slot": None},
        {"m": "I think the gateway strips the Authorization header on /v2/orders.", "k": "fact", "t": "gateway strips Authorization on /v2/orders", "slot": "gateway"},
        {"m": "Orders path prefix is /v2/orders only.", "k": "constraint", "t": "prefix /v2/orders", "slot": "prefix"},
        {"m": "Gateway allowlist must include Authorization.", "k": "decision", "t": "allowlist Authorization", "slot": "allow"},
        {"m": "Orders service expects Bearer scheme.", "k": "fact", "t": "Bearer scheme", "slot": "scheme"},
        {"m": "back to the orders API 401 with a valid token", "k": None, "t": None, "slot": None},
        {"m": "the gateway Authorization header on /v2/orders", "k": None, "t": None, "slot": None},
        {"m": "Gateway forwards X-Request-Id on orders.", "k": "fact", "t": "forward X-Request-Id", "slot": "xid"},
        {"m": "Orders 401 — is allowlist fixed?", "k": None, "t": None, "slot": None},
        {"m": "the token 401 on the orders API still", "k": None, "t": None, "slot": None},
        {"m": "Keep Bearer only on /v2/orders gateway.", "k": "constraint", "t": "Bearer only", "slot": "scheme"},
        {"m": "Revive orders gateway Authorization strip", "k": None, "t": None, "slot": None},
        {"m": "Orders API: confirm allowlist Authorization", "k": None, "t": None, "slot": None},
        {"m": "X-Request-Id still forwarded on orders?", "k": None, "t": None, "slot": None},
        {"m": "back to orders /v2/orders 401", "k": None, "t": None, "slot": None},
        {"m": "Orders prefix still /v2/orders?", "k": None, "t": None, "slot": None},
        {"m": "Gateway strip bug — Authorization on orders", "k": None, "t": None, "slot": None},
        {"m": "Final orders: allowlist Authorization Bearer /v2/orders", "k": None, "t": None, "slot": None},
        {"m": "orders API 401 with valid token again", "k": None, "t": None, "slot": None},
        {"m": "Confirm gateway does not strip Authorization", "k": None, "t": None, "slot": None},
    ],
    "D": [
        {"m": "The checkout component still renders twice.", "k": "fact", "t": "checkout renders twice", "slot": None},
        {"m": "The frontend toast shows an API 401 when the token is fine on the client.", "k": "fact", "t": "frontend toast API 401", "slot": "toast"},
        {"m": "Checkout uses React 18 StrictMode in dev.", "k": "fact", "t": "StrictMode double invoke", "slot": "strict"},
        {"m": "Disable duplicate fetch in checkout effect.", "k": "decision", "t": "dedupe checkout fetch", "slot": "dedupe"},
        {"m": "the checkout component still rendering twice", "k": None, "t": None, "slot": None},
        {"m": "the frontend toast API 401 on checkout", "k": None, "t": None, "slot": None},
        {"m": "Checkout error boundary swallows 401 toast.", "k": "fact", "t": "error boundary swallows toast", "slot": "boundary"},
        {"m": "Use AbortController on checkout fetch.", "k": "decision", "t": "AbortController checkout", "slot": "abort"},
        {"m": "Revive checkout double-render", "k": None, "t": None, "slot": None},
        {"m": "Is StrictMode still the double-render cause?", "k": None, "t": None, "slot": None},
        {"m": "Checkout dedupe fetch still on?", "k": None, "t": None, "slot": None},
        {"m": "back to checkout toast 401", "k": None, "t": None, "slot": None},
        {"m": "AbortController on checkout — confirm", "k": None, "t": None, "slot": None},
        {"m": "checkout renders twice still?", "k": None, "t": None, "slot": None},
        {"m": "Frontend toast 401 vs real auth — checkout", "k": None, "t": None, "slot": None},
        {"m": "Error boundary should not swallow checkout toast", "k": "constraint", "t": "surface checkout toast", "slot": "boundary"},
        {"m": "Final checkout: dedupe + AbortController + toast", "k": None, "t": None, "slot": None},
        {"m": "Revive checkout StrictMode note", "k": None, "t": None, "slot": None},
        {"m": "checkout double-render and toast 401", "k": None, "t": None, "slot": None},
        {"m": "Confirm checkout fetch aborted on unmount", "k": None, "t": None, "slot": None},
    ],
    "E": [
        {"m": "I need a black dress for a corporate event.", "k": "decision", "t": "black", "slot": "color"},
        {"m": "The event is formal and in the evening.", "k": "constraint", "t": "evening event", "slot": "event_time"},
        {"m": "Also need closed-toe shoes for the corporate event.", "k": "constraint", "t": "closed-toe shoes", "slot": "shoes"},
        {"m": "Actually navy, not black, for the formal evening event.", "k": "decision", "t": "navy", "slot": "color"},
        {"m": "Peplum silhouette for the corporate hosting look.", "k": "decision", "t": "peplum", "slot": "silhouette"},
        {"m": "back to the dress for the corporate event", "k": None, "t": None, "slot": None},
        {"m": "the navy dress for the formal evening event", "k": None, "t": None, "slot": None},
        {"m": "Skip jewelry beyond studs for corporate.", "k": "constraint", "t": "studs only", "slot": "jewelry"},
        {"m": "maybe the navy one?", "k": None, "t": None, "slot": None},
        {"m": "Peplum still the silhouette?", "k": None, "t": None, "slot": None},
        {"m": "Revive corporate outfit color decision", "k": None, "t": None, "slot": None},
        {"m": "Evening formal — navy peplum confirm", "k": None, "t": None, "slot": None},
        {"m": "Closed-toe shoes still required?", "k": None, "t": None, "slot": None},
        {"m": "back to navy peplum corporate hosting", "k": None, "t": None, "slot": None},
        {"m": "Studs only jewelry for the event?", "k": None, "t": None, "slot": None},
        {"m": "Corporate outfit: navy not black", "k": None, "t": None, "slot": None},
        {"m": "Final outfit: navy peplum evening formal", "k": None, "t": None, "slot": None},
        {"m": "What color did we decide for the dress?", "k": None, "t": None, "slot": None},
        {"m": "Revive peplum silhouette for hosting", "k": None, "t": None, "slot": None},
        {"m": "Confirm navy peplum closed-toe corporate evening", "k": None, "t": None, "slot": None},
    ],
    "F": [
        {"m": "Lisbon trip: the hotel needs parking.", "k": "fact", "t": "Lisbon hotel needs parking", "slot": None},
        {"m": "The Lisbon flight is Saturday morning.", "k": "constraint", "t": "Saturday morning flight", "slot": "flight"},
        {"m": "Prefer Alfama area for the Lisbon hotel.", "k": "decision", "t": "Alfama area", "slot": "area"},
        {"m": "Budget under 180 EUR night in Lisbon.", "k": "constraint", "t": "under 180 EUR", "slot": "budget"},
        {"m": "back to the Lisbon hotel parking", "k": None, "t": None, "slot": None},
        {"m": "the Saturday morning Lisbon flight", "k": None, "t": None, "slot": None},
        {"m": "Lisbon: need late checkout Sunday.", "k": "constraint", "t": "late checkout Sunday", "slot": "checkout"},
        {"m": "What about Alfama for Lisbon?", "k": None, "t": None, "slot": None},
        {"m": "Revive Lisbon parking hotel", "k": None, "t": None, "slot": None},
        {"m": "Budget still under 180 EUR Lisbon?", "k": None, "t": None, "slot": None},
        {"m": "Saturday morning flight still set?", "k": None, "t": None, "slot": None},
        {"m": "back to Lisbon trip Alfama", "k": None, "t": None, "slot": None},
        {"m": "Late checkout Sunday in Lisbon?", "k": None, "t": None, "slot": None},
        {"m": "Lisbon hotel with parking near Alfama", "k": None, "t": None, "slot": None},
        {"m": "Confirm Lisbon flight Saturday morning", "k": None, "t": None, "slot": None},
        {"m": "Revive Lisbon budget constraint", "k": None, "t": None, "slot": None},
        {"m": "Final Lisbon: Alfama parking Saturday flight", "k": None, "t": None, "slot": None},
        {"m": "Lisbon trip parking again", "k": None, "t": None, "slot": None},
        {"m": "Alfama still preferred for Lisbon hotel?", "k": None, "t": None, "slot": None},
        {"m": "Confirm under 180 EUR and parking Lisbon", "k": None, "t": None, "slot": None},
    ],
    "G": [
        {"m": "Tonight I'll cook pasta carbonara.", "k": "decision", "t": "pasta carbonara", "slot": "dish"},
        {"m": "Wait, no dairy at all for this dinner.", "k": "constraint", "t": "no dairy", "slot": "diet"},
        {"m": "Risotto instead of pasta carbonara, still no dairy.", "k": "decision", "t": "risotto", "slot": "dish"},
        {"m": "Use oat milk only if needed for dinner.", "k": "constraint", "t": "oat milk only", "slot": "milk"},
        {"m": "back to the dairy-free dinner", "k": None, "t": None, "slot": None},
        {"m": "the dairy-free risotto dinner", "k": None, "t": None, "slot": None},
        {"m": "Add mushrooms to the dairy-free risotto.", "k": "fact", "t": "mushrooms in risotto", "slot": "addin"},
        {"m": "Dinner for two portions.", "k": "constraint", "t": "two portions", "slot": "portions"},
        {"m": "Revive dairy-free risotto", "k": None, "t": None, "slot": None},
        {"m": "No dairy still hard constraint?", "k": None, "t": None, "slot": None},
        {"m": "Oat milk only still?", "k": None, "t": None, "slot": None},
        {"m": "back to dinner risotto mushrooms", "k": None, "t": None, "slot": None},
        {"m": "Two portions dinner confirm", "k": None, "t": None, "slot": None},
        {"m": "What dish did we pick for dairy-free dinner?", "k": None, "t": None, "slot": None},
        {"m": "Revive no-dairy dinner plan", "k": None, "t": None, "slot": None},
        {"m": "Final dinner: dairy-free mushroom risotto", "k": None, "t": None, "slot": None},
        {"m": "pasta carbonara is out — risotto stands", "k": None, "t": None, "slot": None},
        {"m": "Dairy-free dinner mushrooms still in?", "k": None, "t": None, "slot": None},
        {"m": "Confirm oat milk and two portions", "k": None, "t": None, "slot": None},
        {"m": "back to dairy-free risotto dinner", "k": None, "t": None, "slot": None},
    ],
    "H": [
        {"m": "The presentation deck is 12 slides and mentions Lisbon airport traffic.", "k": "fact", "t": "12 slides Lisbon airport chart", "slot": None},
        {"m": "Keep Lisbon as a chart on the deck, not the trip.", "k": "constraint", "t": "Lisbon chart not trip", "slot": "scope"},
        {"m": "Deck title is Q3 Ops Review.", "k": "decision", "t": "title Q3 Ops Review", "slot": "title"},
        {"m": "Speaker notes under 40 words per slide.", "k": "constraint", "t": "notes <40 words", "slot": "notes"},
        {"m": "the presentation deck Lisbon chart", "k": None, "t": None, "slot": None},
        {"m": "the 12 slides Lisbon chart on the deck", "k": None, "t": None, "slot": None},
        {"m": "Add one appendix slide for sources.", "k": "decision", "t": "appendix sources slide", "slot": "appendix"},
        {"m": "Revive presentation deck Lisbon chart", "k": None, "t": None, "slot": None},
        {"m": "Q3 Ops Review title still?", "k": None, "t": None, "slot": None},
        {"m": "Deck: Lisbon is chart not trip — confirm", "k": None, "t": None, "slot": None},
        {"m": "Speaker notes limit still 40 words?", "k": None, "t": None, "slot": None},
        {"m": "back to 12-slide deck", "k": None, "t": None, "slot": None},
        {"m": "Appendix sources slide on deck?", "k": None, "t": None, "slot": None},
        {"m": "Revive deck airport traffic chart", "k": None, "t": None, "slot": None},
        {"m": "Final deck: Q3 Ops Review 12 slides + appendix", "k": None, "t": None, "slot": None},
        {"m": "presentation deck Lisbon chart again", "k": None, "t": None, "slot": None},
        {"m": "Confirm chart scope not Lisbon trip", "k": None, "t": None, "slot": None},
        {"m": "Deck notes under 40 words still", "k": None, "t": None, "slot": None},
        {"m": "back to presentation deck", "k": None, "t": None, "slot": None},
        {"m": "Confirm appendix sources on the deck", "k": None, "t": None, "slot": None},
    ],
    "I": [
        {"m": "I am applying to Stripe for the backend role.", "k": "fact", "t": "Stripe backend role", "slot": None},
        {"m": "The Stripe application deadline is Friday.", "k": "constraint", "t": "deadline Friday", "slot": "deadline"},
        {"m": "Resume emphasizes Go and Postgres for Stripe.", "k": "fact", "t": "Go and Postgres on resume", "slot": "resume"},
        {"m": "Ask referrer for Stripe intro Thursday.", "k": "decision", "t": "referrer intro Thursday", "slot": "referrer"},
        {"m": "the Stripe application deadline Friday", "k": None, "t": None, "slot": None},
        {"m": "Stripe backend role Friday deadline", "k": None, "t": None, "slot": None},
        {"m": "Cover letter under 300 words for Stripe.", "k": "constraint", "t": "cover <300 words", "slot": "cover"},
        {"m": "Revive Stripe Friday deadline", "k": None, "t": None, "slot": None},
        {"m": "Go Postgres resume bullets for Stripe?", "k": None, "t": None, "slot": None},
        {"m": "Referrer intro still Thursday?", "k": None, "t": None, "slot": None},
        {"m": "back to Stripe backend application", "k": None, "t": None, "slot": None},
        {"m": "Cover letter length still under 300?", "k": None, "t": None, "slot": None},
        {"m": "Stripe deadline Friday confirm", "k": None, "t": None, "slot": None},
        {"m": "Final Stripe: Friday deadline Go Postgres", "k": None, "t": None, "slot": None},
        {"m": "Revive Stripe referrer Thursday", "k": None, "t": None, "slot": None},
        {"m": "Stripe backend role application status", "k": None, "t": None, "slot": None},
        {"m": "Confirm Friday deadline Stripe", "k": None, "t": None, "slot": None},
        {"m": "back to Stripe cover letter constraint", "k": None, "t": None, "slot": None},
        {"m": "Stripe resume Go Postgres still", "k": None, "t": None, "slot": None},
        {"m": "Confirm referrer intro Thursday for Stripe", "k": None, "t": None, "slot": None},
    ],
    "J": [
        {"m": "Quick brainrot: what is the tallest Pokémon?", "k": "fact", "t": "tallest Pokémon question", "slot": None},
        {"m": "Trivia correction: it is not Wailord, go with Celesteela.", "k": "decision", "t": "Celesteela", "slot": "answer"},
        {"m": "Celesteela height cited as 30'02\".", "k": "fact", "t": "Celesteela 30'02\"", "slot": "height"},
        {"m": "the tallest Pokémon trivia again", "k": None, "t": None, "slot": None},
        {"m": "Celesteela trivia again", "k": None, "t": None, "slot": None},
        {"m": "back to the tallest Pokémon Celesteela trivia", "k": None, "t": None, "slot": None},
        {"m": "Do not use Wailord as tallest.", "k": "constraint", "t": "not Wailord", "slot": "exclude"},
        {"m": "Revive Celesteela tallest trivia", "k": None, "t": None, "slot": None},
        {"m": "Height 30'02\" still the cite?", "k": None, "t": None, "slot": None},
        {"m": "Trivia: tallest is Celesteela confirm", "k": None, "t": None, "slot": None},
        {"m": "Wailord excluded from tallest answer", "k": None, "t": None, "slot": None},
        {"m": "back to Pokémon height trivia", "k": None, "t": None, "slot": None},
        {"m": "Final trivia: Celesteela not Wailord", "k": None, "t": None, "slot": None},
        {"m": "Revive tallest Pokémon decision", "k": None, "t": None, "slot": None},
        # Avoid curly/quoted height tokens that break MockLLM script substring match → NEW.
        {"m": "Celesteela height cite again for tallest Pokemon trivia", "k": None, "t": None, "slot": None},
        {"m": "Confirm not Wailord for tallest", "k": None, "t": None, "slot": None},
        {"m": "Pokémon trivia Celesteela still", "k": None, "t": None, "slot": None},
        {"m": "back to Celesteela trivia", "k": None, "t": None, "slot": None},
        {"m": "Tallest Pokémon answer Celesteela", "k": None, "t": None, "slot": None},
        {"m": "Final check Celesteela height trivia", "k": None, "t": None, "slot": None},
    ],
}


def _workstreams_from_base() -> list[dict]:
    base = json.loads((DIR / "fixture.json").read_text(encoding="utf-8"))
    return list(base["workstreams"])


def interleave(arcs: dict[str, list[dict]]) -> list[dict]:
    """Round-robin with slight jitter so gaps exist for revive."""
    ids = list(arcs.keys())
    idxs = {i: 0 for i in ids}
    turns: list[dict] = []
    n = 0
    # Pass 1: first 8 of each in RR
    for wave in range(8):
        for wid in ids:
            if idxs[wid] < len(arcs[wid]):
                n += 1
                step = arcs[wid][idxs[wid]]
                idxs[wid] += 1
                turns.append({"turn": n, "ws": wid, "message": step["m"], "_meta": step})
    # Pass 2: remaining in RR
    while any(idxs[i] < len(arcs[i]) for i in ids):
        for wid in ids:
            if idxs[wid] < len(arcs[wid]):
                n += 1
                step = arcs[wid][idxs[wid]]
                idxs[wid] += 1
                turns.append({"turn": n, "ws": wid, "message": step["m"], "_meta": step})
    return turns


def build_scripts(turns: list[dict]) -> tuple[dict, dict]:
    extract: dict = {}
    llm: dict = {}
    for t in turns:
        msg = t["message"]
        wid = t["ws"]
        meta = t.get("_meta") or {}
        # Full message as key — Mock matches `key in message` (longest first for extract).
        key = msg
        llm[key] = {
            "task_id": wid,
            "is_new_task": False,
            "confidence": 0.86,
            "rationale": f"scripted_{wid}",
        }
        if meta.get("k") and meta.get("t"):
            patch = {
                "kind": meta["k"],
                "text": meta["t"],
                "workstream_id": wid,
                "referent_id": f"{wid}.loop1",
            }
            if meta.get("slot"):
                patch["slot"] = meta["slot"]
            extract[key] = {"patches": [patch]}
        else:
            extract[key] = {"patches": [], "uncertain": True}
    return extract, llm


def build_probes(turns: list[dict]) -> dict:
    """Late revive probes — one per workstream near the end."""
    by_ws: dict[str, list[dict]] = {}
    for t in turns:
        by_ws.setdefault(t["ws"], []).append(t)
    probes = []
    needed = {
        "A": ["TTL 5", "aud"],
        "B": ["debian slim", "4Gi"],
        "C": ["Authorization", "/v2/orders"],
        "D": ["dedupe", "AbortController"],
        "E": ["navy", "peplum"],
        "F": ["Alfama", "parking"],
        "G": ["risotto", "no dairy"],
        "H": ["Q3 Ops", "Lisbon chart"],
        "I": ["Friday", "Go"],
        "J": ["Celesteela"],
    }
    forbid = {
        "A": ["Lisbon hotel", "navy peplum"],
        "B": ["Celesteela", "risotto"],
        "C": ["debian slim", "navy"],
        "D": ["Alfama", "Celesteela"],
        "E": ["TTL", "Docker"],
        "F": ["peplum", "risotto"],
        "G": ["Stripe", "JWT"],
        "H": ["parking", "Celesteela"],
        "I": ["alpine", "risotto"],
        "J": ["navy", "Docker"],
    }
    for wid, rows in by_ws.items():
        late = rows[-1]
        probes.append({
            "id": f"r20_{wid}",
            "turn": late["turn"],
            "gold_task_id": wid,
            "gold_referent_id": f"{wid}.loop1",
            "gold_policy": "ACT",
            "needed_state": needed.get(wid, []),
            "should_not_carry": forbid.get(wid, []),
            "competing_similar": [],
            "category": "density_revive",
            "utterance_kind": "return",
            "expected_open_workstream_count": 10,
            "expected_gap": "long_density",
        })
    return {"probes": probes}


def main() -> None:
    ws = _workstreams_from_base()
    turns_raw = interleave(ARCS)
    extract, llm = build_scripts(turns_raw)
    turns = [{"turn": t["turn"], "ws": t["ws"], "message": t["message"]} for t in turns_raw]
    fx = {
        "meta": {
            "kind": "synthetic_adversarial_engineering_fixture",
            "not": "natural human behavior",
            "conversation_id": "ten-ws-10x20",
            "n_workstreams": 10,
            "seed": 20,
            "n_user_turns": len(turns),
            "target": "10 workstreams x ~20 interleaved turns + revive",
            "built_by": "eval.ten_workstream.build_fixture_10x20",
        },
        "workstreams": ws,
        "turns": turns,
        "extract_scripts": extract,
        "llm_scripts": llm,
    }
    OUT.write_text(json.dumps(fx, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    probes = build_probes(turns_raw)
    PROBES_OUT.write_text(json.dumps(probes, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    from collections import Counter
    c = Counter(t["ws"] for t in turns)
    print(json.dumps({
        "fixture": str(OUT),
        "probes": str(PROBES_OUT),
        "n_turns": len(turns),
        "per_ws": dict(sorted(c.items())),
        "min_ws_turns": min(c.values()),
        "max_ws_turns": max(c.values()),
    }, indent=2))


if __name__ == "__main__":
    main()
