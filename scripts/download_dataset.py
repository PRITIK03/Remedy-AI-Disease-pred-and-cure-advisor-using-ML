"""Download and verify the legacy training dataset.

The Phase 0 audit (docs/legacy-ml-baseline.md §1) identified the legacy
training data as the 303-row "Heart Attack Analysis & Prediction" CSV (the
famous Kaggle ``ronitf/heart-disease-uci`` file). Phase 1 verified that the
public mirror ``kb22/Heart-Disease-Prediction`` (GitHub) reproduces ALL 13
feature means/stds to 4 decimal places against ``scaler.pkl`` — i.e. it is
byte-equivalent in content to the original training file.

This script downloads that mirror, validates the schema, and stores it with
provenance metadata. Deterministic: same source -> same file -> same hash.

Usage:
    python scripts/download_dataset.py
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "ml" / "data"
RAW_PATH = DATA_DIR / "heart.csv"
META_PATH = DATA_DIR / "dataset_meta.json"

SOURCE_URL = (
    "https://raw.githubusercontent.com/kb22/Heart-Disease-Prediction/"
    "master/dataset.csv"
)

FEATURES = [
    "age", "sex", "cp", "trestbps", "chol", "fbs", "restecg",
    "thalach", "exang", "oldpeak", "slope", "ca", "thal",
]
TARGET = "target"
EXPECTED_ROWS = 303
EXPECTED_COLS = 14

# Plausibility ranges from the UCI-derived schema (data-dependent validation).
VALUE_RANGES: dict[str, tuple[float, float]] = {
    "age": (25, 100), "sex": (0, 1), "cp": (0, 3), "trestbps": (80, 220),
    "chol": (100, 600), "fbs": (0, 1), "restecg": (0, 2), "thalach": (60, 220),
    "exang": (0, 1), "oldpeak": (0, 10), "slope": (0, 2), "ca": (0, 4),
    "thal": (0, 3), "target": (0, 1),
}


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def validate(rows: list[dict[str, str]]) -> None:
    if len(rows) != EXPECTED_ROWS:
        raise ValueError(f"Expected {EXPECTED_ROWS} rows, got {len(rows)}")
    if list(rows[0].keys()) != FEATURES + [TARGET]:
        raise ValueError(f"Unexpected columns: {list(rows[0].keys())}")
    for i, row in enumerate(rows):
        for col, (low, high) in VALUE_RANGES.items():
            v = float(row[col])
            if not (low <= v <= high):
                raise ValueError(
                    f"Row {i}: {col}={v} outside plausible range [{low}, {high}]"
                )


def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Downloading {SOURCE_URL} ...")
    raw = fetch(SOURCE_URL)
    text = raw.decode("utf-8-sig")

    rows = list(csv.DictReader(io.StringIO(text)))
    validate(rows)
    print(f"Schema OK: {len(rows)} rows x {len(rows[0])} cols")

    # Normalize line endings for deterministic hashing across checkouts.
    normalized = text.replace("\r\n", "\n")
    if not normalized.endswith("\n"):
        normalized += "\n"
    RAW_PATH.write_text(normalized, encoding="utf-8", newline="\n")

    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    y = [int(r[TARGET]) for r in rows]
    meta = {
        "dataset_name": "heart.csv (Heart Attack Analysis & Prediction / UCI Cleveland derived)",
        "source_url": SOURCE_URL,
        "source_repository": "kb22/Heart-Disease-Prediction (GitHub mirror)",
        "original_kaggle_reference": "ronitf/heart-disease-uci (legacy training source, identified in Phase 0)",
        "downloaded_at": datetime.now(UTC).isoformat(),
        "rows": len(rows),
        "columns": FEATURES + [TARGET],
        "target_column": TARGET,
        "target_counts": {str(v): y.count(v) for v in sorted(set(y))},
        "sha256": digest,
        "verification": (
            "All 13 feature means/stds match legacy scaler.pkl statistics to "
            "4 decimal places; LR coefficient-sign reproduction test passed "
            "(see docs/legacy-ml-baseline.md and ml/data/README.md)."
        ),
    }
    META_PATH.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    print(f"Saved {RAW_PATH.relative_to(PROJECT_ROOT)}")
    print(f"SHA-256: {digest}")
    print(f"Metadata: {META_PATH.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
