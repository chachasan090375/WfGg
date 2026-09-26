#!/usr/bin/env python3
"""Legacy entrypoint kept for historical workflows.

Active consolidation logic is version-agnostic and lives in
architecture-council-platform-consolidation.py.
"""
from pathlib import Path
import runpy

TARGET=Path(__file__).with_name("architecture-council-platform-consolidation.py")
runpy.run_path(str(TARGET),run_name="__main__")
