import type { QualityGrade } from "./schemas";

export function qualityGrade(ratio: number | null): QualityGrade {
  if (ratio === null || !Number.isFinite(ratio)) return "limited";
  if (ratio >= 0.85) return "good";
  if (ratio >= 0.65) return "acceptable";
  if (ratio >= 0.4) return "poor";
  return "limited";
}

export const QUALITY_GRADE_LABELS: Record<QualityGrade, string> = {
  good: "Dobra",
  acceptable: "Akceptowalna",
  poor: "Słaba",
  limited: "Ograniczona",
};
