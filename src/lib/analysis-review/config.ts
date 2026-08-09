import type { DeviationBand, ReviewMetricName } from "./schemas";

export type MetricDefinition = {
  label: string;
  shortLabel: string;
  unit: "deg" | "ratio";
  group: string;
  bodyArea: string;
  deviation?: { boundaries: readonly [number, number, number]; center: number };
};

export const METRIC_NAMES = [
  "trunk_inclination_deg",
  "neck_flexion_deg",
  "left_upper_arm_elevation_deg",
  "right_upper_arm_elevation_deg",
  "left_elbow_flexion_deg",
  "right_elbow_flexion_deg",
  "left_forearm_inclination_deg",
  "right_forearm_inclination_deg",
  "left_wrist_flexion_deg",
  "right_wrist_flexion_deg",
  "left_hand_closure_ratio",
  "right_hand_closure_ratio",
  "left_pinch_distance_ratio",
  "right_pinch_distance_ratio",
] as const satisfies readonly ReviewMetricName[];

export const METRIC_DEFINITIONS: Record<ReviewMetricName, MetricDefinition> = {
  trunk_inclination_deg: metric("Pochylenie tułowia", "Tułów", "deg", "Tułów i szyja", "trunk", [10, 25, 45]),
  neck_flexion_deg: metric("Zgięcie szyi", "Szyja", "deg", "Tułów i szyja", "neck", [10, 20, 35]),
  left_upper_arm_elevation_deg: metric("Uniesienie lewego ramienia", "Lewe ramię", "deg", "Ramiona", "left_arm", [20, 45, 90]),
  right_upper_arm_elevation_deg: metric("Uniesienie prawego ramienia", "Prawe ramię", "deg", "Ramiona", "right_arm", [20, 45, 90]),
  left_elbow_flexion_deg: metric("Zgięcie lewego łokcia", "Lewy łokieć", "deg", "Łokcie i przedramiona", "left_elbow", [30, 50, 75], 90),
  right_elbow_flexion_deg: metric("Zgięcie prawego łokcia", "Prawy łokieć", "deg", "Łokcie i przedramiona", "right_elbow", [30, 50, 75], 90),
  left_forearm_inclination_deg: metric("Pochylenie lewego przedramienia", "Lewe przedramię", "deg", "Łokcie i przedramiona", "left_elbow", [20, 45, 75]),
  right_forearm_inclination_deg: metric("Pochylenie prawego przedramienia", "Prawe przedramię", "deg", "Łokcie i przedramiona", "right_elbow", [20, 45, 75]),
  left_wrist_flexion_deg: metric("Zgięcie lewego nadgarstka", "Lewy nadgarstek", "deg", "Nadgarstki", "left_wrist", [10, 25, 45]),
  right_wrist_flexion_deg: metric("Zgięcie prawego nadgarstka", "Prawy nadgarstek", "deg", "Nadgarstki", "right_wrist", [10, 25, 45]),
  left_hand_closure_ratio: metric("Zamknięcie lewej dłoni", "Lewa dłoń", "ratio", "Dłonie", "left_hand"),
  right_hand_closure_ratio: metric("Zamknięcie prawej dłoni", "Prawa dłoń", "ratio", "Dłonie", "right_hand"),
  left_pinch_distance_ratio: metric("Odległość kciuk–palec wskazujący lewej dłoni", "Lewy chwyt precyzyjny", "ratio", "Dłonie", "left_hand"),
  right_pinch_distance_ratio: metric("Odległość kciuk–palec wskazujący prawej dłoni", "Prawy chwyt precyzyjny", "ratio", "Dłonie", "right_hand"),
};

export const DEVIATION_LABELS: Record<DeviationBand, string> = {
  neutral: "neutralne",
  mild: "łagodne odchylenie",
  elevated: "podwyższone odchylenie",
  strong: "silne odchylenie",
  unknown: "brak wiarygodnych danych",
};

export const QUALITY_WARNING_LABELS: Record<string, string> = {
  HIGH_MOTION_BLUR: "Fragmenty nagrania są rozmazane podczas szybkiego ruchu.",
  LOW_BODY_COVERAGE: "Część sylwetki przez znaczną część nagrania znajdowała się poza kadrem.",
  EXCESSIVE_HAND_OCCLUSION: "Widoczność dłoni była ograniczona.",
  EXCESSIVE_LIMB_OCCLUSION: "Elementy sylwetki były okresowo zasłonięte.",
  EXCESSIVE_TRACK_LOSS: "Śledzenie sylwetki było okresowo tracone i ponownie podejmowane.",
  EXCESSIVE_HAND_SWAP_RISK: "Identyfikacja lewej i prawej dłoni była okresowo niejednoznaczna.",
  HIGH_FINGER_REJECTION: "Znaczna część punktów palców została odrzucona przez walidację.",
  HOLDING_LOW_CONFIDENCE: "Dane o trzymaniu przedmiotu zawierają okresy ograniczonej jakości.",
};

export function classifyDeviation(name: ReviewMetricName, value: number | null): DeviationBand {
  const rule = METRIC_DEFINITIONS[name].deviation;
  if (value === null || !Number.isFinite(value) || !rule) return "unknown";
  const magnitude = Math.abs(value - rule.center);
  if (magnitude < rule.boundaries[0]) return "neutral";
  if (magnitude < rule.boundaries[1]) return "mild";
  if (magnitude < rule.boundaries[2]) return "elevated";
  return "strong";
}

function metric(
  label: string,
  shortLabel: string,
  unit: "deg" | "ratio",
  group: string,
  bodyArea: string,
  boundaries?: readonly [number, number, number],
  center = 0,
): MetricDefinition {
  return { label, shortLabel, unit, group, bodyArea, deviation: boundaries ? { boundaries, center } : undefined };
}
