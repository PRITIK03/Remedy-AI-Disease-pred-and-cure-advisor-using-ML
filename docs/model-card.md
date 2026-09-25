# Model Card — cardiovascular-disease-risk v2.0.0

## Model overview

A logistic-regression model (inside a calibrated sklearn Pipeline) that
estimates the **probability of the "disease" class** for a 303-row,
UCI-Cleveland-derived heart-disease dataset, from 13 routinely collected
clinical features. The output is a **model-estimated probability**, not a
clinically validated risk score.

- **Model name:** `cardiovascular-disease-risk`
- **Version:** 2.0.0
- **Selected estimator:** LogisticRegression (max_iter=1000, seed=42) inside
  `Pipeline(preprocessor → classifier)` wrapped in
  `CalibratedClassifierCV(method=sigmoid, cv=5)` — one serialized artifact:
  `models/v2/cardio_risk_pipeline.joblib`
- **Positive class:** `1 = disease`

## Intended use

Educational/portfolio decision-support prototype demonstrating a correct,
leakage-free, reproducible ML pipeline with honest evaluation. It may be used
to explore how such a system is built and documented.

## Out-of-scope use

- **Not a clinical diagnostic device.**
- Not for emergency decision-making.
- Not validated for real-world medical care of any kind.
- Not for use with real patients in any setting.

## Training data

- **Dataset:** `ml/data/heart.csv` — 303 rows × 14 columns (13 features +
  `target`), SHA-256 `d235cad39b7bcc1d63c7b672146fb3b6108b861201d2e29e288ec7fe03e35082`
  (recorded in `ml/data/dataset_meta.json`).
- **Provenance:** mirror of the Kaggle `ronitf/heart-disease-uci` file, itself
  a mislabeled derivative of the UCI Cleveland heart-disease data (mixed
  Cleveland/Hungarian/VA/Switzerland rows per the Kaggle documentation).
- **Identity verification:** all 13 feature means/stds match the legacy
  `scaler.pkl` statistics to 4 decimals; a fresh LR reproduces the legacy
  model's coefficient signs on all 13 features. See `ml/data/README.md`.
- **Population:** historical, small, and of limited demographic diversity
  (1990s-era research cohort; 68% male). No external validation exists.

## Features

| # | Feature  | Type        | Encoding in training data |
|---|----------|-------------|---------------------------|
| 1 | age      | numeric     | years                     |
| 2 | sex      | binary      | 0 = female, 1 = male      |
| 3 | cp       | categorical | 0–3 chest pain type       |
| 4 | trestbps | numeric     | mmHg                      |
| 5 | chol     | numeric     | mg/dl                     |
| 6 | fbs      | binary      | 1 if fasting sugar > 120  |
| 7 | restecg  | categorical | 0–2                       |
| 8 | thalach  | numeric     | bpm                       |
| 9 | exang    | binary      | 1 = exercise angina       |
| 10| oldpeak  | numeric     | mm ST depression          |
| 11| slope    | categorical | 0–2                       |
| 12| ca       | categorical | 0–4 major vessels         |
| 13| thal     | categorical | 0–3                       |

## Target definition (modern pipeline)

- **1 = disease** (more chance of heart attack)
- **0 = no disease** (less chance of heart attack)

The source dataset encodes the **opposite** (`1 = healthy`). The training
loader applies the documented transformation `y_modern = 1 − y_source`
(`ml/config.py:flip_target`), verified by
`tests/test_target_semantics.py`. The legacy v1 app interpreted
`predict_proba()[:, 1]` as "risk" — i.e. it published P(healthy) as risk;
that inversion is corrected in v2.

## Preprocessing

Fitted **inside the pipeline** (leakage-free by construction; the legacy
scaler was fit on the full dataset — a documented leakage bug):

- **numeric** (age, trestbps, chol, thalach, oldpeak): median-impute +
  StandardScaler
- **binary** (sex, fbs, exang): passthrough
- **categorical** (cp, restecg, slope, ca, thal): most-frequent-impute +
  OneHotEncoder(handle_unknown="ignore") → 27 transformed columns

## Evaluation (actual measured results)

Locked test set (n=61, stratified, seed=42), calibration=sigmoid:

| Metric                | Uncalibrated | Calibrated |
|-----------------------|--------------|------------|
| Accuracy              | 0.8361       | 0.8525     |
| ROC-AUC               | 0.9394       | 0.9372     |
| Sensitivity (recall)  | —            | 0.7857     |
| Specificity           | —            | 0.9091     |
| Precision             | —            | 0.8800     |
| F1                    | —            | 0.8302     |
| Brier score           | 0.1063       | 0.1115     |

Confusion matrix (calibrated, threshold 0.5): TN=30, FP=3, FN=6, TP=22
(6 disease cases missed — unacceptable clinically, typical for a prototype).

**CV results (5-fold stratified, train split only, 303-row dataset — treat
±std as descriptive, not inferential):**

| Candidate                 | ROC-AUC (mean ± std) | Brier | F1     |
|---------------------------|----------------------|-------|--------|
| logistic_regression       | 0.9059 ± 0.0315      | 0.1207| 0.8126 |
| random_forest             | 0.9186 ± 0.0308      | 0.1205| 0.8208 |
| hist_gradient_boosting    | 0.8770 ± 0.0281      | 0.1530| 0.7909 |

## Calibration

Method: `CalibratedClassifierCV(method="sigmoid")` (Platt scaling, internal
5-fold CV on train only). On the train split, calibration changed Brier as
follows (LR: 0.0909 → 0.0976; RF: 0.0650 → 0.0633; HGB: 0.0118 → 0.0571 —
the HGB train number reflects severe overfitting, correctly detected).
On the locked test set, the calibrated LR has marginally worse Brier than
uncalibrated (0.1115 vs 0.1063) with slightly better accuracy/AUC-parity.
Calibration is retained in the artifact for honest probability outputs;
**the difference is within noise at this dataset size**.

## Explainability

- **Global:** mean |SHAP| (LinearExplainer, background = 242-row train split
  transformed matrix). Top drivers: `ca_0` (0.576), `cp_0` (0.524),
  `sex` (0.454), `thal_2` (0.430), `oldpeak` (0.385) — directionally
  consistent with clinical expectations (few affected vessels + asymptomatic
  cp push toward "no disease").
- **Local:** per-prediction contributions averaged over the 5 calibrated
  members, name-aligned (background_sample.joblib persisted at training).
- **Wording policy:** SHAP values are *model contributions* — never causal or
  clinical explanations.

## Limitations

- **Tiny dataset** (303 rows, 61-row test set): all metrics have wide
  confidence intervals; differences between candidates are not significant.
- **Historical, biased data**: 1990s cohort, 68% male, single region.
- **Label noise**: the Kaggle file's inverted/mislabeled target is documented;
  semantics were corrected but the underlying labels were never clinically
  adjudicated.
- **No external validation, no prospective validation, no calibration across
  sites.**
- 6 of 28 disease cases missed at the 0.5 threshold (sensitivity 0.79).
- Logistic regression on one-hot features cannot capture interactions the
  tree models might; tree candidates were not significantly better in CV.

## Version

2.0.0 — trained 2026-09-25 with Python 3.14.7 / scikit-learn 1.7.2;
metadata in `models/v2/metadata.json`, metrics in `models/v2/metrics.json`,
MLflow run `c506277ae2204cf087228f88a6a537fa` (sqlite tracking: `mlflow.db`).
