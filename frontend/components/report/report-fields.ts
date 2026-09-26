import type { AssessmentCreate } from "@/types/api";

export const REPORT_FIELDS: { key: keyof AssessmentCreate; label: string; hint: string }[] = [
  { key: "age", label: "Age (years)", hint: "25-100" },
  { key: "sex", label: "Sex (0=female, 1=male)", hint: "0 or 1" },
  { key: "cp", label: "Chest pain type", hint: "0-3" },
  { key: "trestbps", label: "Resting BP (mmHg)", hint: "80-220" },
  { key: "chol", label: "Cholesterol (mg/dl)", hint: "100-600" },
  { key: "fbs", label: "Fasting sugar > 120", hint: "0 or 1" },
  { key: "restecg", label: "Resting ECG", hint: "0-2" },
  { key: "thalach", label: "Max heart rate", hint: "60-220" },
  { key: "exang", label: "Exercise angina", hint: "0 or 1" },
  { key: "oldpeak", label: "ST depression", hint: "0-10" },
  { key: "slope", label: "ST slope", hint: "0-2" },
  { key: "ca", label: "Vessels (ca)", hint: "0-4" },
  { key: "thal", label: "Thal", hint: "0-3" },
];
