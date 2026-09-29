#!/usr/bin/env python3
"""Zero-dependency deterministic qualification runner for this candidate.

No network access, no mutation outside Python process memory, no external spend.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import traceback

ROOT = pathlib.Path(__file__).resolve().parent
TEST_FILE = ROOT / "tests" / "test_core.py"


def load_tests():
    spec = importlib.util.spec_from_file_location("canonical_path_resolution_tests", TEST_FILE)
    if spec is None or spec.loader is None:
        raise RuntimeError("TEST_MODULE_LOAD_FAILED")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    module = load_tests()
    tests = sorted(
        (name, value)
        for name, value in vars(module).items()
        if name.startswith("test_") and callable(value)
    )
    if not tests:
        print("QUALIFICATION=FAIL reason=NO_TESTS")
        return 2

    failures = []
    for name, test in tests:
        try:
            test()
            print(f"PASS {name}")
        except Exception as exc:  # qualification must expose every deterministic failure
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
