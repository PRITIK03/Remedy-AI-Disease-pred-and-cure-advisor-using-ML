"""Guard for modern-stack tests.

The v2 artifact is trained with the modern .venv (Python 3.14 / sklearn 1.7).
When the test suite runs under the legacy system interpreter (Python 3.10 /
sklearn 1.3.2, which must keep running the Phase 0 regression tests), these
modules must SKIP with a clear reason instead of failing to unpickle.
"""

from __future__ import annotations

import json

import pytest


def require_modern_env() -> None:
    """Module-level skip unless the v2 artifact matches this interpreter."""
    import sklearn

    from ml.config import METADATA_PATH

    if not METADATA_PATH.exists():
        pytest.skip(
            "v2 artifact missing — run `.venv/Scripts/python -m ml.training.train`",
            allow_module_level=True,
        )
    meta = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    trained = meta.get("sklearn_version")
    if trained != sklearn.__version__:
        pytest.skip(
            f"v2 artifact requires sklearn {trained}; this interpreter has "
            f"{sklearn.__version__} (legacy environment — Phase 0 tests only)",
            allow_module_level=True,
        )
