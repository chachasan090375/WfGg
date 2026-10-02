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
            test()
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
