/**
 * Human-readable labels for the categorical feature values.
 * The API always receives the numeric encoding; the UI shows meaning.
 */

export interface FieldOption {
  value: number;
  label: string;
  description?: string;
}

export const SEX_OPTIONS: FieldOption[] = [
  { value: 0, label: "Female" },
  { value: 1, label: "Male" },
];

export const CHEST_PAIN_OPTIONS: FieldOption[] = [
  { value: 0, label: "Typical angina", description: "Classic chest pain pattern" },
  { value: 1, label: "Atypical angina", description: "Unusual chest pain pattern" },
  { value: 2, label: "Non-anginal pain", description: "Chest pain not from the heart" },
  { value: 3, label: "Asymptomatic", description: "No chest pain reported" },
];

export const YES_NO_OPTIONS: FieldOption[] = [
  { value: 0, label: "No" },
  { value: 1, label: "Yes" },
];

export const REST_ECG_OPTIONS: FieldOption[] = [
  { value: 0, label: "Normal" },
  { value: 1, label: "ST-T abnormality", description: "ST-T wave abnormality observed" },
  {
    value: 2,
    label: "LV hypertrophy",
    description: "Probable or definite left ventricular hypertrophy",
  },
];

export const SLOPE_OPTIONS: FieldOption[] = [
  { value: 0, label: "Downsloping" },
  { value: 1, label: "Flat" },
  { value: 2, label: "Upsloping" },
];

export const VESSEL_OPTIONS: FieldOption[] = [
  { value: 0, label: "0 vessels", description: "No major vessels affected" },
  { value: 1, label: "1 vessel" },
  { value: 2, label: "2 vessels" },
  { value: 3, label: "3 vessels" },
  { value: 4, label: "4 vessels", description: "Rare marker value" },
];

export const THAL_OPTIONS: FieldOption[] = [
  { value: 0, label: "Not recorded", description: "Marker value in this dataset" },
  { value: 1, label: "Normal" },
  { value: 2, label: "Fixed defect" },
  { value: 3, label: "Reversible defect" },
];

/** Map a transformed feature name (e.g. "categorical__cp_0") to readable text. */
export function prettyFeatureName(raw: string): string {
  const FEATURE_LABELS: Record<string, string> = {
    "numeric__age": "Age",
    "numeric__trestbps": "Resting blood pressure",
    "numeric__chol": "Cholesterol",
    "numeric__thalach": "Maximum heart rate",
    "numeric__oldpeak": "ST depression",
    "binary__sex": "Sex (male)",
    "binary__fbs": "High fasting blood sugar",
    "binary__exang": "Exercise-induced angina",
    "categorical__cp_0": "Chest pain: typical angina",
    "categorical__cp_1": "Chest pain: atypical angina",
    "categorical__cp_2": "Chest pain: non-anginal",
    "categorical__cp_3": "Chest pain: asymptomatic",
    "categorical__restecg_0": "ECG: normal",
    "categorical__restecg_1": "ECG: ST-T abnormality",
    "categorical__restecg_2": "ECG: LV hypertrophy",
    "categorical__slope_0": "ST slope: downsloping",
    "categorical__slope_1": "ST slope: flat",
    "categorical__slope_2": "ST slope: upsloping",
    "categorical__ca_0": "0 affected vessels",
    "categorical__ca_1": "1 affected vessel",
    "categorical__ca_2": "2 affected vessels",
    "categorical__ca_3": "3 affected vessels",
    "categorical__ca_4": "4 affected vessels",
    "categorical__thal_0": "Thal: not recorded",
    "categorical__thal_1": "Thal: normal",
    "categorical__thal_2": "Thal: fixed defect",
    "categorical__thal_3": "Thal: reversible defect",
  };
  return FEATURE_LABELS[raw] ?? raw;
}
