# Dependency Audit (Phase 0)

`requirements.txt` is a **`pip freeze` of an entire Jupyter development
environment**, not a curated dependency list (it contains jupyterlab,
notebook, ipykernel, debugpy, pywin32, etc. — none of which the app uses).
Environment reality vs. the file:

| Package       | requirements.txt | Installed env (actual) | Models trained on |
|---------------|------------------|------------------------|-------------------|
| scikit-learn  | 1.5.2            | 1.3.2                  | **1.4.2**         |
| numpy         | 2.1.2            | 1.26.2                 | (1.4.2-era)       |
| Flask         | 3.0.3            | 3.0.3                  | —                 |
| Werkzeug      | 3.0.4            | 3.0.3                  | —                 |
| scipy         | 1.14.1           | 1.13.0                 | —                 |
| joblib        | 1.4.2            | 1.3.2                  | —                 |
| pandas        | 2.2.3            | 2.1.3                  | —                 |
| gunicorn      | 23.0.0           | 23.0.0                 | —                 |
| pytest        | (not listed)     | 9.1.1                  | —                 |

## Key findings

1. **Three-way version mismatch on scikit-learn.** The pickles carry
   `_sklearn_version = 1.4.2`. The environment runs 1.3.2, and requirements
   pins 1.5.2. Unpickling under 1.3.2 currently works with only an
   `InconsistentVersionWarning`, and predictions were verified deterministic.
   Installing per requirements.txt (1.5.2) was NOT tested in this phase and is
   the more likely-to-succeed target if a reinstall is desired — it is the
   nearest ≥1.4.2 version. **Do not assume any pin is "the" training version
   without a load test.**
2. **numpy 2.x risk.** requirements pins numpy 2.1.2 while the installed
   sklearn 1.3.2 was built against numpy 1.x. Mixing numpy 2.x with older
   binary wheels is a known ABI break source. Any future environment build
   must resolve sklearn+numpy together.
3. **`openai==0.28.0`** is present — the legacy app never calls any LLM. It is
   dead weight from the dev environment (and a pre-1.0 API version at that).
4. **pywin32** — Windows-only transitive noise from the Jupyter env; the
   Procfile targets gunicorn (Linux/Heroku) where it would not even install
   cleanly.
5. **No pinned test tooling** in requirements despite pytest being the plan.
6. **`xgboost==2.1.2`** is listed but no artifact uses XGBoost (verified by
   unpickling all three models — members are RF + LR only).

## Table (per Phase 0 spec)

| Current dependency | Why it exists | Used by | Current issue | Recommended future replacement/upgrade | Phase when it should change |
|---|---|---|---|---|---|
| Flask 3.0.3 | web app | app.py | fine for now | keep (or FastAPI in Phase 2) | Phase 2 |
| scikit-learn (mixed versions) | legacy pickles | app.py | trained 1.4.2 ≠ env 1.3.2 ≠ pin 1.5.2 | pin exactly one version proven by load test; track in model registry metadata | Phase 1 |
| numpy 2.1.2 (pin) | sklearn dep | sklearn | ABI risk with older sklearn wheels | resolve jointly with sklearn | Phase 1 |
| gunicorn 23.0.0 | Procfile deployment | deployment | fine | keep | Phase 8 |
| pandas 2.2.3 (pin) | not used at runtime | nothing runtime | unused at runtime | drop until Phase 1 (data pipeline) | Phase 1 |
| xgboost 2.1.2 | dev-env freeze | nothing | unused | drop unless Phase 1 adds it deliberately | Phase 1 |
| openai 0.28.0 | dev-env freeze | nothing | unused, ancient API | drop now (or Phase 4 LLM layer) | Phase 1/4 |
| jupyterlab/notebook/ipykernel/etc. | dev-env freeze | nothing | bloats install | drop; move to dev extras in pyproject | Phase 1 |
| pywin32 | dev-env freeze | nothing | breaks Linux deploys | drop | Phase 1 |
| pytest (unlisted) | testing | tests | not pinned in file | add to dev extras | Phase 1 |

## Recommendation

Do **not** mass-upgrade in Phase 0. The installed env (sklearn 1.3.2 +
numpy 1.26.2) is *proven working with the artifacts* by this phase's tests —
it is the safest known-good combination and was used for the recorded
baseline outputs. In Phase 1, build a fresh env (likely via `pyproject.toml`
+ lockfile), load-test the pickles against sklearn ≥1.4.2, and only then
re-pin.
