import importlib, inspect, traceback, sys
import tests.conftest as cf

FIXTURES = {"registry": cf.registry, "mock": cf.mock}
MODULES = ["tests.test_routing", "tests.test_references",
           "tests.test_compiler", "tests.test_registry",
           "tests.test_provider_independence"]

passed = failed = 0
for modname in MODULES:
    mod = importlib.import_module(modname)
    for name, fn in sorted(vars(mod).items()):
        if not (name.startswith("test_") and callable(fn)):
            continue
        params = list(inspect.signature(fn).parameters)
        kwargs = {p: FIXTURES[p]() for p in params if p in FIXTURES}
        try:
            fn(**kwargs)
            passed += 1
            print(f"PASS {modname}.{name}")
        except Exception:
            failed += 1
            print(f"FAIL {modname}.{name}")
            traceback.print_exc()
print(f"\n=== {passed} passed, {failed} failed ===")
sys.exit(1 if failed else 0)
