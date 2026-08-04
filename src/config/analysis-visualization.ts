export type AnalysisFocusMode = "full" | "upper" | "arm";

export type AnalysisRegionId =
  | "neck"
  | "shoulders"
  | "trunk"
  | "rightElbow"
  | "hips"
  | "knees";

export type AnalysisRegion = {
  id: AnalysisRegionId;
  label: string;
  metric: string;
  description: string;
};

export const analysisRegions = [
  {
    id: "neck",
    label: "Szyja",
    metric: "Oś szyi i tułowia",
    description: "Punkty głowy, szyi i barków wyznaczają geometrię pomiaru 2D.",
  },
  {
    id: "shoulders",
    label: "Barki",
    metric: "Elewacja ramion",
    description: "Położenie barków jest analizowane osobno dla lewej i prawej strony.",
  },
  {
    id: "trunk",
    label: "Tułów",
    metric: "Pochylenie względem pionu",
    description: "Oś biodra–barki tworzy techniczną linię odniesienia dla tułowia.",
  },
  {
    id: "rightElbow",
    label: "Łokieć",
    metric: "Kąt zgięcia",
    description: "Kąt powstaje wyłącznie z dostępnych punktów barku, łokcia i nadgarstka.",
  },
  {
    id: "hips",
    label: "Biodra",
    metric: "Oś centralna ciała",
    description: "Środek bioder stabilizuje główną oś geometryczną sylwetki.",
  },
  {
    id: "knees",
    label: "Kolana",
    metric: "Punkty podporu",
    description: "Kolana i kostki pomagają opisać ustawienie dolnej części ciała.",
  },
] as const satisfies readonly AnalysisRegion[];

export function getAnalysisRegion(id: AnalysisRegionId) {
  return analysisRegions.find((region) => region.id === id) ?? analysisRegions[2];
}
