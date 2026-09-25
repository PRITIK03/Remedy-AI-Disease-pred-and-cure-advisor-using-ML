# ML Modernization Results — Legacy V1 vs Modern V2 (Phase 1)

All numbers below come from executed runs (see commands at the end). Nothing
is aspirational; where something is descriptive rather than statistically
meaningful, it says so.

## Comparison table

| Aspect           | Legacy V1                                    | Modern V2                                      |
|------------------|----------------------------------------------|------------------------------------------------|
| Dataset          | not in repo; identified via scaler stats     | same dataset, verified + SHA-256, in `ml/data/`|
| Target semantics | **inverted in app** (P(healthy) shown as risk)| corrected: `1 = disease` (flip documented)     |
| Preprocessing    | full-dataset scaler fit (**leakage**)        | ColumnTransformer inside Pipeline (leakage-free)|
| Models           | LR + RF (VotingClassifier soft, 2 members)   | LR, RF, HistGB evaluated; LR selected          |
| Validation       | single 80/20 split (alleged; unverifiable)   | stratified 5-fold CV + locked test split       |
| Probability      | raw `predict_proba`, mislabeled "risk %"     | sigmoid-calibrated P(disease); labeled honestly |
| Explainability   | none                                         | SHAP (global + local) + permutation fallback   |
| Subgroup analysis| none                                         | sex/age bands, small-n caveats explicit        |
| Tracking         | none                                         | MLflow 3.16 (sqlite), params+metrics+model     |
| Artifact         | scaler.pkl + 3 model pkls, 2 unused          | ONE joblib pipeline + metadata.json + metrics  |
| Reproducibility  | none (no training code committed)            | seed-fixed, hash-checked, one-command training |
| Tests            | none                                         | 80 passing (35 legacy-preserved + 45 new)      |

## Actual model metrics (locked test set, n=61)

Modern V2, selected model = logistic_regression, calibration = sigmoid:

| Metric      | Uncalibrated | Calibrated |
|-------------|--------------|------------|
| Accuracy    | 0.8361       | **0.8525** |
| ROC-AUC     | 0.9394       | **0.9372** |
| Sensitivity | —            | 0.7857     |
| Specificity | —            | 0.9091     |
| Precision   | —            | 0.8800     |
| F1          | —            | 0.8302     |
| Brier       | 0.1063       | 0.1115     |

CV (train split, 5-fold stratified): LR 0.9059±0.0315, RF 0.9186±0.0308,
HistGB 0.8770±0.0281 ROC-AUC. Selection: LR (parsimony within 0.02 AUC of the
best; differences are within noise at n=303).

### Honesty note on "accuracy"

The legacy README claimed ~91.3%. That number is unverifiable (no training
code, no eval artifacts) and rested on a pipeline with scaler leakage. The
modern pipeline's honest 85.25% on a properly locked test set is **lower —
and that is the point**: correctness over a prettier number. The ~86% LR
figure measured on the legacy artifacts with correct pairing in Phase 1
(full-data fit, in-sample) is consistent with leakage-inflated historical
claims.

## Semantics verification (the headline fix)

Same input, two generations of the app:

| Profile (clinically) | Legacy V1 output        | Modern V2 output                    |
|----------------------|-------------------------|-------------------------------------|
| Healthy (45M, cp=0, thalach=170, ca=0) | "High risk of heart disease: 66.41%" ❌ | "Low risk of heart disease: 34.83%" ✅ |
| Severe (65M, cp=3, oldpeak=2.5, ca=3)  | "Low risk of heart disease: 18.95%" ❌  | "High risk of heart disease: 85.34%" ✅ |

## Reproduce

```bash
# 1. Environment (once)
py -3.14 -m venv .venv
.venv/Scripts/python -m pip install numpy scipy pandas "scikit-learn==1.7.2" \
    joblib matplotlib shap mlflow pytest pytest-cov ruff flask

# 2. Dataset (once; verifies schema + records SHA-256)
python scripts/download_dataset.py
.venv/Scripts/python scripts/verify_dataset.py

# 3. Train (CV + calibration + selection + explainability + MLflow)
.venv/Scripts/python -m ml.training.train

# 4. Tests
.venv/Scripts/python -m pytest tests/ -v

# 5. Run the app (v2 default)
.venv/Scripts/python app.py           # MODEL_VERSION=v2
MODEL_VERSION=v1 .venv/Scripts/python app.py   # legacy comparison mode
```
