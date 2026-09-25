# Legacy ML Baseline — Verified Facts (Phase 0)

This document records what the legacy ML pipeline **actually** does, verified by
inspecting the pickle artifacts (`scripts/inspect_models.py`) and executing the
inference path under the current environment. README claims are deliberately
**not** used as evidence. Every statement below is backed by an observed fact.

Environment used for verification: Python 3.10.11, scikit-learn 1.3.2, numpy 1.26.2
(see `docs/dependency-audit.md` for the version-compatibility discussion).

---

## 1. Dataset (verified indirectly — high confidence)

The `scaler.pkl` `mean_` vector matches, to 2–3 decimal places, the public
column statistics of the Kaggle dataset **"Heart Attack Analysis & Prediction
Dataset"** (`heart.csv`, 303 rows, often mirrored as the UCI Cleveland heart
dataset variant used on Kaggle):

| Feature   | Scaler mean (observed) | Kaggle heart.csv mean |
|-----------|------------------------|-----------------------|
| age       | 54.3663                | 54.37                 |
| sex       | 0.6832                 | 0.68                  |
| cp        | 0.9670                 | 0.97                  |
| trestbps  | 131.6238               | 131.62                |
| chol      | 246.2640               | 246.26                |
| fbs       | 0.1485                 | 0.15                  |
| restecg   | 0.5281                 | 0.53                  |
| thalach   | 149.6469               | 149.65                |
| exang     | 0.3267                 | 0.33                  |
| oldpeak   | 1.0396                 | 1.04                  |
| slope     | 1.3993                 | 1.40                  |
| ca        | 0.7294                 | 0.73                  |
| thal      | 2.3135                 | 2.31                  |

This match on **all 13 features simultaneously** is conclusive.

**Critical dataset caveat:** in this Kaggle dataset the target column semantics
are **inverted relative to the UCI original**: `output/target = 1` means *LESS
chance of heart attack* (healthy), `0` means *more chance* (disease). See
Section 6 — this inverted encoding leaked all the way into the deployed app.

**Training-split evidence:** the scaler statistics equal the **full-dataset**
(303-row) statistics, not a 242-row training subset. If a train/test split had
been applied *before* fitting the scaler, the means would deviate noticeably
(sampling noise on n=242 vs n=303). Conclusion: the scaler was fit on the full
dataset → **train/test contamination (data leakage) in the legacy pipeline**.
This also inflates any legacy reported accuracy.

No dataset file, no training script, and no notebook exist in the repository —
the training code was never committed. Reconstruction above is from artifacts.

## 2. Target and class semantics

- Binary classification, `classes_ = [0, 1]`, `n_features_in_ = 13`.
- Dataset encoding: `0 = disease present (more chance of heart attack)`,
  `1 = no disease (less chance of heart attack)`.
- The app (`app.py`) treats `predict_proba()[:, 1] > 0.5` as "High risk of
  heart disease" — **this is semantically inverted** (see Section 6).

## 3. Feature schema and order (verified from `scaler.feature_names_in_`)

| # | Feature  | Type        | Expected values / range            | Training representation | Inference representation (app) |
|---|----------|-------------|------------------------------------|-------------------------|--------------------------------|
| 1 | age      | numeric     | 29–77 years                        | float                   | `int()` from form              |
| 2 | sex      | categorical | 0 = female, 1 = male               | int                     | `int()`                        |
| 3 | cp       | categorical | 0–3 chest pain type                | int                     | `int()`                        |
| 4 | trestbps | numeric     | 94–200 mmHg (dataset range)        | float                   | `int()`                        |
| 5 | chol     | numeric     | 126–564 mg/dl (dataset range)      | float                   | `int()`                        |
| 6 | fbs      | categorical | 0 / 1 (fasting blood sugar > 120)  | int                     | `int()`                        |
| 7 | restecg  | categorical | 0–2 (dataset uses 0,1,2)           | int                     | `int()`                        |
| 8 | thalach  | numeric     | 71–202 bpm (dataset range)         | float                   | `int()`                        |
| 9 | exang    | categorical | 0 / 1 exercise-induced angina      | int                     | `int()`                        |
| 10| oldpeak  | numeric     | 0.0–6.2 mm ST depression           | float                   | `float()`                      |
| 11| slope    | categorical | 0–2 ST slope                       | int                     | `int()`                        |
| 12| ca       | categorical | 0–4 major vessels (HTML says 0–3!) | int                     | `int()`                        |
| 13| thal     | categorical | 0–3 (HTML says 1–3!)               | int                     | `int()`                        |

Feature order in the app's `np.array` matches `feature_names_in_` exactly —
the array construction order is correct.

### Frontend ↔ schema mismatches (foundational, correctness-relevant)

- `ca`: HTML restricts to 0–3 and the README claims 0–4; the dataset contains
  values 0–4 (rare 4 = missing-value marker in the original UCI data). The
  trained model saw ca=4 during training (scaler `ca` mean/var cover it), so
  the HTML limit silently blocks an input class the model was trained on.
- `thal`: HTML restricts to 1–3 and labels it "1 = normal, 2 = fixed, 3 =
  reversible" (UCI semantics), but the Kaggle dataset uses 0–3 with different
  semantics (0 = null/missing marker in this dataset). A user entering `0` is
  blocked; the label meanings do not match the training encoding.
- `restecg`: HTML says "0 = Normal, 1 = Abnormal" but the dataset uses 0–2
  (0 = normal, 1 = ST-T abnormality, 2 = LV hypertrophy). Value 2 is possible
  in training data but the HTML offers no range hint and the backend never
  validates.
- Backend performs **no range validation at all** — only `int()`/`float()`
  casts. A crash (500) on non-numeric input, and any in-range-but-nonsense
  value is accepted silently.

## 4. Preprocessing

- Single `StandardScaler` (with_mean=True, with_std=True), fit on the full
  dataset (Section 1), serialized separately — **not** embedded in a Pipeline.
- Inference order in app: build (1, 13) float array → `scaler.transform` →
  `voting_classifier_model.predict_proba(...)[:, 1]`.
- There is **no** feature engineering, encoding, imputation, or clipping —
  raw numeric passthrough plus z-score scaling.

## 5. Model artifacts (all three + scaler)

All artifacts were unpickled successfully under scikit-learn 1.3.2 with an
`InconsistentVersionWarning`: they were serialized under **scikit-learn 1.4.2**
(numeric inspects of the pickles confirm the `_sklearn_version` tuple 1.4.2).
No load error occurs; behavior verified deterministic in tests.

### 5.1 `logistic_regression_model.pkl` (813 bytes)
- `sklearn.linear_model.LogisticRegression`
- Params: C=1.0, solver=lbfgs, max_iter=100, penalty=l2, random_state=42
- 13 features, classes [0, 1], `predict_proba` supported.
- **Currently loaded by `app.py` but never used for inference.**

### 5.2 `random_forest_model.pkl` (741 KB)
- `sklearn.ensemble.RandomForestClassifier`, 100 trees, `max_features='sqrt'`,
  bootstrap=True, random_state=42.
- 13 features, classes [0, 1], `predict_proba` supported.
- **Currently loaded by `app.py` but never used for inference.**

### 5.3 `voting_classifier_model.pkl` (1.48 MB) — the only model used
- `sklearn.ensemble.VotingClassifier`, `voting='soft'`, `flatten_transform=True`.
- Members (in order): `('random_forest', RandomForestClassifier(random_state=42))`,
  `('logistic_regression', LogisticRegression(random_state=42))` — **two**
  members, not three. No GradientBoosting/XGBoost despite README claims.
- Soft voting = mean of member `predict_proba` columns.
- Member probability check (deterministic input `[45,1,0,120,180,0,0,170,0,0.5,1,0,2]`):
  LR 0.608101, RF 0.720000, VC 0.664051 = (0.608101+0.720000)/2 ✓.

### 5.4 `scaler.pkl`
- `sklearn.preprocessing.StandardScaler`, 13 features, `feature_names_in_`
  present (so it was fit on a pandas DataFrame with the column order above).

## 6. ⚠️ Class-semantics inversion (most important finding)

Evidence, all verified from artifacts:

1. LR coefficients on scaled features (class 1 = positive class):
   - Disease markers `exang −0.367`, `oldpeak −0.684`, `ca −0.724`,
     `thal −0.455` → **negative**
   - Protective marker `thalach +0.379` → **positive**
   If class 1 meant disease, these signs would be reversed.
2. Deterministic probes:
   - Clinically healthy profile `[45,1,0,120,180,0,0,170,0,0.5,1,0,2]`
     → class 1, proba 0.664 → app says **"High risk: 66.41%"**
   - Clinically severe profile `[65,1,3,160,300,1,2,100,1,2.5,2,3,3]`
     → class 0, proba 0.189 → app says **"Low risk: 18.95%"**

**Conclusion:** class 1 = *no disease*. The app's displayed percentage and
High/Low label are inverted 180°. The "High risk" threshold `> 0.5` is applied
to the wrong column of the probability matrix.

**Phase 0 decision:** per instructions, legacy behavior is preserved and NOT
silently patched. The inversion is documented here and in the README audit;
a `--invert-check` probe lives in the test suite so the next phase fixes it
deliberately (by swapping to `[:, 0]` or relabeling) as a conscious change.

## 7. Verified deterministic baseline outputs (sklearn 1.3.2, numpy 1.26.2)

Inputs are raw feature vectors in schema order; probabilities are the app's
`predict_proba()[:, 1]` value (VC = voting classifier):

| Case       | Raw input                                                             | VC proba [:,1] | LR proba | RF proba | VC predict |
|------------|-----------------------------------------------------------------------|----------------|----------|----------|------------|
| low_risk   | [45,1,0,120,180,0,0,170,0,0.5,1,0,2]                                  | 0.664051       | 0.608101 | 0.720000 | 1          |
| high_risk  | [65,1,3,160,300,1,2,100,1,2.5,2,3,3]                                  | 0.189465       | 0.058929 | 0.320000 | 0          |
| median     | [54,0,1,132,246,0,1,150,0,1.0,2,0,2]                                  | 0.945440       | 0.940881 | 0.950000 | 1          |

(Note how `median` — a near-dataset-mean row with cp=1 — gets 94.5% "risk";
consistent with class 1 = healthy/mean-like.)

These exact values are asserted (within tolerance) in `tests/test_legacy_model.py`
so any future change to artifacts or preprocessing is caught.

## 8. Recommendation ("remedy") logic

Pure rule-based Python in `get_remedies()` — **no AI/ML involved**:

- Triggered rules (on raw, unscaled inputs):
  - `predicted_risk > 0.5` → "Consult a healthcare professional immediately…"
  - `age > 50` → regular check-ups
  - `chol > 200` → heart-healthy diet
  - `trestbps > 130` → monitor BP / lifestyle
  - `thalach < 120` → aerobic exercise
  - `oldpeak > 1` → discuss stress test / cardiac rehab
- Plus 6 unconditional generic lifestyle tips appended to every response.

Note: because of the Section 6 inversion, the "consult a professional
immediately" advice fires for **healthy** users and not for sick ones.

## 9. Threshold

`prediction_prob > 0.5` (hardcoded, applied to the wrong class column —
see Section 6). No calibration, no threshold tuning, no cost sensitivity.

## 10. Known legacy issues summary

1. **Inverted risk semantics** (Section 6) — user-facing correctness bug.
2. **Data leakage** — scaler fit on full dataset (Section 1); any legacy
   accuracy claim (~90/91%) is therefore not trustworthy.
3. Hardcoded Windows absolute model paths (`C:\Users\priti\...`) — app cannot
   start on any other machine.
4. Template resolution broken — `index.html` is in the repo root, Flask's
   default `templates/` folder does not exist.
5. No input validation; 500 on malformed form data.
6. README claims (accuracy, three-model ensemble incl. GradientBoosting,
   input validation, "enterprise-grade", API docs, CI, static assets) are
   largely false — see `docs/readme-audit.md`.
7. Two of three models are dead weight at runtime (loaded, never used).
8. No `.gitignore`; no tests; no logging; `debug=True` hardcoded; pickle
   artifacts pinned to sklearn 1.4.2 while requirements pins 1.5.2.
