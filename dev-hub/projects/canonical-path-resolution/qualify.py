#!/usr/bin/env python3
"""Zero-dependency deterministic qualification runner for this candidate.

No network access, no mutation outside Python process memory, no external spend.
"""

from __future__ import annotations

import importlib.util
import pathlib
import inspect
import sys
import tempfile
import traceback

ROOT = pathlib.Path(__file__).resolve().parent
TEST_DIR = ROOT / "tests"


def load_modules():
    modules = []
    for index, test_file in enumerate(sorted(TEST_DIR.glob("test_*.py"))):
        spec = importlib.util.spec_from_file_location(
            f"canonical_path_resolution_tests_{index}", test_file
        )
        if spec is None or spec.loader is None:
            raise RuntimeError(f"TEST_MODULE_LOAD_FAILED:{test_file.name}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        modules.append(module)
    return modules



class MonkeyPatch:
    """Minimal zero-dependency monkeypatch fixture with deterministic undo."""
    def __init__(self):
        self._undo = []

    def setattr(self, obj, name, value):
        existed = hasattr(obj, name)
        old = getattr(obj, name, None)
        setattr(obj, name, value)
        self._undo.append((obj, name, existed, old))

    def undo(self):
        while self._undo:
            obj, name, existed, old = self._undo.pop()
            if existed:
                setattr(obj, name, old)
            else:
                delattr(obj, name)


def run_test(test):
    """Provide the only fixtures used by this zero-dependency test suite."""
    params = inspect.signature(test).parameters
    unsupported = sorted(set(params) - {"tmp_path", "monkeypatch"})
    if unsupported:
        raise RuntimeError("UNSUPPORTED_FIXTURES:" + ",".join(unsupported))
    patch = MonkeyPatch()
    try:
        with tempfile.TemporaryDirectory(prefix="canonical-path-qualify-") as tmp:
            kwargs = {}
            if "tmp_path" in params:
                kwargs["tmp_path"] = pathlib.Path(tmp)
            if "monkeypatch" in params:
                kwargs["monkeypatch"] = patch
            test(**kwargs)
    finally:
        patch.undo()


def main() -> int:
    modules = load_modules()
    tests = []
    for module in modules:
        tests.extend(
            (f"{module.__name__}.{name}", value)
            for name, value in vars(module).items()
            if name.startswith("test_") and callable(value)
        )
    tests.sort(key=lambda item: item[0])

    if not tests:
        print("QUALIFICATION=FAIL reason=NO_TESTS")
        return 2

    failures = []
    for name, test in tests:
        try:
            run_test(test)
            print(f"PASS {name}")
        except Exception as exc:
            failures.append(name)
            print(f"FAIL {name}: {exc}")
            traceback.print_exc()

    print(f"TESTS_TOTAL={len(tests)}")
    print(f"TESTS_PASS={len(tests) - len(failures)}")
    print(f"TESTS_FAIL={len(failures)}")
    if failures:
        print("QUALIFICATION=FAIL")
        return 1
    print("QUALIFICATION=PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
