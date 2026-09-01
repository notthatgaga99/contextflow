# Cloud durability POC

**Reviewer start here:** [`docs/CLOUD_POC_REVIEWER.md`](../../docs/CLOUD_POC_REVIEWER.md)

That page is the **CLOUD TECHNICAL PROOF** walkthrough (authenticated Cloud Run → Vertex → Firestore → frozen routing → WorkingContext → revision survival).

It is **separate** from the local product demo:

```bash
python -m eval.product_demo --serve   # LOCAL — MockLLM, offline — docs/PRODUCT_DEMO.md
```

---

Deterministic unit proof that Firestore-backed memory survives restart without
cross-conversation leakage. **Do not use `CF_MEMORY_BACKEND=memory` for cloud proof.**

## Plan

1. **Request 1 (conversation A):** write durable memory via MemoryWriter.
2. **Request 2 (conversation B):** write unrelated memory.
3. **Restart / redeploy:** new process or new store instances; same Firestore DB.
4. **Request 3 (return to A):** assert A's memory; no B leak; history auditable;
   working context excludes superseded state.

## Local unit (no emulator)

```bash
pytest -q tests/test_firestore_store.py tests/test_cloud_poc_durability.py
```

Uses `FakeFirestoreClient` — same semantics without GCP.

## Live cloud harnesses (cost money)

```bash
python -m eval.cloud_poc.end_to_end_resurrection
python -m eval.cloud_poc.e2e_repeatability
python -m eval.cloud_poc.dynamic_workstream_e2e
```

See `docs/CLOUD_POC_REVIEWER.md` for exact evidence to inspect. **Not production-ready.**
