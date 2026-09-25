"""Verify the stored dataset against the legacy scaler statistics.

Confirms that ml/data/heart.csv is the same data the legacy scaler was fit
on (all 13 means/stds within tolerance) and that the schema is intact.

Usage (run inside the modern venv):
    .venv/Scripts/python scripts/verify_dataset.py
"""

from __future__ import annotations

import csv
import hashlib
import json
import pickle
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = PROJECT_ROOT / "ml" / "data" / "heart.csv"
META_PATH = PROJECT_ROOT / "ml" / "data" / "dataset_meta.json"
SCALER_PATH = PROJECT_ROOT / "scaler.pkl"  # legacy artifact, untouched

FEATURES = [
    "age", "sex", "cp", "trestbps", "chol", "fbs", "restecg",
    "thalach", "exang", "oldpeak", "slope", "ca", "thal",
]
TARGET = "target"
TOL = 1e-3


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    failures: list[str] = []

    text = DATA_PATH.read_text(encoding="utf-8")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    meta = json.loads(META_PATH.read_text(encoding="utf-8"))
    print(f"SHA-256: {digest}")
    if meta.get("sha256") != digest:
        failures.append("dataset_meta.json sha256 does not match file content")

    rows = list(csv.DictReader(text.splitlines()))
    print(f"Rows: {len(rows)}  Columns: {list(rows[0].keys())}")
    if len(rows) != 303:
        failures.append(f"row count {len(rows)} != 303")
    if list(rows[0].keys()) != FEATURES + [TARGET]:
        failures.append("column names/order mismatch")

    X = np.array([[float(r[f]) for f in FEATURES] for r in rows])
    y = np.array([int(r[TARGET]) for r in rows])
    print(f"Target counts: 0={int((y == 0).sum())} 1={int((y == 1).sum())}")

    with open(SCALER_PATH, "rb") as f:
        scaler = pickle.load(f)

    print("\nFeature-statistics match vs legacy scaler.pkl:")
    for i, name in enumerate(FEATURES):
        dm, ds = X[:, i].mean(), X[:, i].std(ddof=0)
        sm, ss = float(scaler.mean_[i]), float(scaler.scale_[i])
        ok = abs(dm - sm) < TOL and abs(ds - ss) < TOL
        status = "MATCH" if ok else "DIFF"
        print(f"  {name:9s} mean {dm:9.4f} vs {sm:9.4f} | std {ds:8.4f} vs {ss:8.4f}  {status}")
        if not ok:
            failures.append(f"{name}: data ({dm:.4f},{ds:.4f}) vs scaler ({sm:.4f},{ss:.4f})")

    print()
    if failures:
        print("VERIFICATION FAILED:")
        for f_ in failures:
            print(f"  - {f_}")
        return 1
    print("VERIFICATION PASSED: dataset is the legacy training data.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
