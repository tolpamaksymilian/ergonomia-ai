const manualInputLabels: Record<string, string> = {
  external_load: "Masa lub siła związana z zadaniem",
  force_load: "Kategoria siły lub obciążenia",
  load_force: "Kategoria siły lub obciążenia",
  rula_force_load: "Kategoria siły lub obciążenia RULA",
  reba_load_force: "Kategoria siły lub obciążenia REBA",
  reba_coupling: "Jakość chwytu lub uchwytu",
  coupling: "Jakość chwytu lub uchwytu",
  reba_activity: "Aktywność i utrzymywanie pozycji",
  activity: "Aktywność i utrzymywanie pozycji",
  rula_muscle_use: "Długotrwałe lub powtarzalne użycie mięśni",
  balanced_weight_distribution: "Równomierne podparcie i rozkład ciężaru",
  foot_support: "Podparcie stóp",
  weight_distribution_and_leg_support: "Rozkład ciężaru i podparcie nóg",
  shoulder_elevation: "Uniesienie barku",
  arm_abduction: "Odwiedzenie ramienia",
  arm_support: "Podparcie ramienia",
  arm_across_midline: "Przekroczenie linii środkowej ciała przez ramię lub przedramię",
  radial_ulnar_deviation: "Odchylenie nadgarstka na bok",
  wrist_deviation_or_twist: "Odchylenie lub skręt nadgarstka",
  wrist_pronation_supination: "Skręt przedramienia lub nadgarstka",
  neck_side_bend: "Boczne zgięcie szyi",
  neck_twist: "Skręt szyi",
  trunk_side_bend: "Boczne zgięcie tułowia",
  trunk_twist: "Skręt tułowia",
  hip: "Położenie biodra",
  knee: "Położenie kolana",
  ankle: "Położenie kostki",
};

export function manualInputLabel(value: string) {
  const normalized = value.replace(/^(left|right)_/, "");
  return manualInputLabels[value] ?? manualInputLabels[normalized] ?? "Dodatkowa informacja wymagająca potwierdzenia";
}
