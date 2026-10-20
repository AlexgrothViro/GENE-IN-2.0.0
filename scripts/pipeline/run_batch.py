#!/usr/bin/env python3
"""Checkout-local adapter: never resolve genein from another editable install."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from genein.pipeline.batch import main

if __name__ == "__main__":
    raise SystemExit(main(repo_root=ROOT))
