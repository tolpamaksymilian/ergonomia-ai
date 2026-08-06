export type ProjectStageStatus = "completed" | "in_progress" | "planned";

export type ProjectStageGroup =
  | "foundation"
  | "vision"
  | "metrics"
  | "risk"
  | "reporting"
  | "infrastructure";

export type ProjectStage = {
  id: string;
  title: string;
  description: string;
  status: ProjectStageStatus;
  group: ProjectStageGroup;
};

export type ProjectTechnology = {
  name: string;
  description: string;
};

export type ProjectMetricGroup = {
  name: string;
  description: string;
};

const stages = [
  { id: "next-app", title: "Aplikacja Next.js", description: "Interfejs i bezpieczne widoki serwerowe.", status: "completed", group: "foundation" },
  { id: "auth", title: "Supabase Auth", description: "Konta, sesje i role użytkowników.", status: "completed", group: "foundation" },
  { id: "private-storage", title: "Prywatny Storage", description: "Chronione nagrania i wyniki analiz.", status: "completed", group: "foundation" },
  { id: "upload", title: "Upload filmów", description: "Przesyłanie krótkich nagrań z panelu.", status: "completed", group: "foundation" },
  { id: "queue", title: "Kolejka analiz", description: "Kontrolowane przekazywanie zadań workerom.", status: "completed", group: "foundation" },
  { id: "preprocessing", title: "Preprocessing", description: "Przygotowanie filmu do analizy pozy.", status: "completed", group: "vision" },
  { id: "pose-v3", title: "Pose Pipeline V3.0", description: "Wersjonowany pipeline analizy sylwetki.", status: "completed", group: "vision" },
  { id: "yolox", title: "YOLOX-X", description: "Wykrywanie głównego pracownika.", status: "completed", group: "vision" },
  { id: "rtmw", title: "RTMW WholeBody", description: "Analiza punktów ciała w klatkach filmu.", status: "completed", group: "vision" },
  { id: "hands", title: "Analiza dłoni", description: "Walidacja punktów dłoni i palców.", status: "completed", group: "vision" },
  { id: "result-video", title: "Film wynikowy", description: "Prywatny podgląd zatwierdzonych punktów.", status: "completed", group: "vision" },
  { id: "metrics-engine", title: "Metrics Engine V1", description: "Czternaście metryk geometrycznych.", status: "completed", group: "metrics" },
  { id: "ergonomics-worker", title: "Ergonomics Worker", description: "Osobny etap obliczania metryk.", status: "completed", group: "metrics" },
  { id: "metrics-persistence", title: "Zapis metryk", description: "Pełny JSON w Storage i podsumowanie w bazie.", status: "completed", group: "metrics" },
  { id: "risk-ready-transition", title: "Etap gotowy do ryzyka", description: "Przejście do ready-for-risk-assessment.", status: "completed", group: "metrics" },
  { id: "risk-engine", title: "Risk Engine V1", description: "Transparentna klasyfikacja metryk według jawnego profilu.", status: "completed", group: "risk" },
  { id: "risk-tests", title: "Testy Risk Engine", description: "Testy profili, ekspozycji i agregacji.", status: "completed", group: "risk" },
  { id: "risk-queue-integration", title: "Integracja z kolejką", description: "Automatyczne przekazanie metryk do Risk Engine.", status: "completed", group: "risk" },
  { id: "risk-worker", title: "Risk Worker", description: "Osobny worker etapu oceny technicznej.", status: "completed", group: "risk" },
  { id: "risk-storage", title: "Zapis risk-assessment.json", description: "Prywatny wynik oceny w Storage.", status: "completed", group: "risk" },
  { id: "risk-panel", title: "Wyniki ryzyka w panelu", description: "Czytelna prezentacja wyniku technicznego.", status: "completed", group: "risk" },
  { id: "production-profile", title: "Produkcyjny profil progów", description: "Profil zatwierdzony przez specjalistę.", status: "planned", group: "risk" },
  { id: "threshold-panel", title: "Panel progów", description: "Konfiguracja wersjonowanych profili.", status: "planned", group: "risk" },
  { id: "report-engine", title: "Report Engine V1", description: "Deterministyczne uporządkowanie istniejących wyników.", status: "completed", group: "reporting" },
  { id: "report-worker", title: "Report Worker V1", description: "Osobny etap generowania raportu po ocenie ryzyka.", status: "completed", group: "reporting" },
  { id: "report-json", title: "analysis-report.json", description: "Wersjonowany raport w prywatnym Storage.", status: "completed", group: "reporting" },
  { id: "report-page", title: "Strona raportu", description: "Czytelna prezentacja raportu w panelu.", status: "completed", group: "reporting" },
  { id: "report-completion", title: "Zakończenie analizy", description: "Stan completed i postęp 100% po zapisie raportu.", status: "completed", group: "reporting" },
  { id: "browser-print", title: "Drukowanie raportu", description: "Wersja do druku dostępna w przeglądarce.", status: "completed", group: "reporting" },
  { id: "charts", title: "Wykresy", description: "Zmiany metryk i ekspozycji w czasie.", status: "planned", group: "reporting" },
  { id: "key-frames", title: "Obrazy kluczowych klatek", description: "Generowanie obrazów reprezentatywnych momentów analizy.", status: "planned", group: "reporting" },
  { id: "pdf", title: "PDF", description: "Eksport końcowego raportu.", status: "planned", group: "reporting" },
  { id: "rula", title: "RULA", description: "Planowana metoda oceny kończyn górnych.", status: "planned", group: "reporting" },
  { id: "reba", title: "REBA", description: "Planowana metoda oceny całego ciała.", status: "planned", group: "reporting" },
  { id: "pipeline-manager", title: "Pipeline Manager", description: "Jeden nadzorowany start pełnego łańcucha workerów.", status: "completed", group: "infrastructure" },
  { id: "live-status", title: "Automatyczne statusy", description: "Lekki polling aktywnych analiz i pojawienie się raportu bez ręcznego odświeżania.", status: "completed", group: "infrastructure" },
  { id: "beta-release", title: "Wersja testowa MVP", description: "Kompletny przepływ v0.2.1-beta.1 gotowy do testów.", status: "completed", group: "infrastructure" },
  { id: "worker-hosting", title: "Hosting workera", description: "Przygotowanie uruchomienia workerów poza komputerem lokalnym.", status: "in_progress", group: "infrastructure" },
  { id: "automatic-cleanup", title: "Czyszczenie filmów", description: "Automatyczna polityka retencji danych.", status: "planned", group: "infrastructure" },
  { id: "validation-tests", title: "Testy walidacyjne", description: "Walidacja dokładności na większym zestawie zróżnicowanych nagrań.", status: "in_progress", group: "infrastructure" },
  { id: "result-presentation", title: "Prezentacja wyników", description: "Dalsze upraszczanie i rozwój wizualnej prezentacji wyników.", status: "in_progress", group: "reporting" },
  { id: "comparison", title: "Porównywanie analiz", description: "Porównanie wariantów tego samego stanowiska.", status: "planned", group: "reporting" },
  { id: "workstation-simulator", title: "Symulator stanowiska", description: "Przyszła koncepcja projektowania stanowiska ze zdjęcia lub modelu 3D.", status: "planned", group: "reporting" },
] as const satisfies readonly ProjectStage[];

export const projectStageGroups: ReadonlyArray<{
  id: ProjectStageGroup;
  label: string;
  description: string;
}> = [
  { id: "foundation", label: "Fundament aplikacji", description: "Konta, dane i obsługa nagrań." },
  { id: "vision", label: "Analiza obrazu", description: "Wykrywanie i śledzenie sylwetki." },
  { id: "metrics", label: "Metryki", description: "Pomiary geometryczne i ich zapis." },
  { id: "risk", label: "Ocena ryzyka", description: "Transparentna interpretacja metryk." },
  { id: "reporting", label: "Raportowanie", description: "Prezentacja i eksport wyników." },
  { id: "infrastructure", label: "Infrastruktura produkcyjna", description: "Hosting, retencja i walidacja." },
];

export const projectStatus = {
  projectName: "Ergonomia AI",
  versions: {
    posePipeline: "v3.0",
    ergonomicsMetricsEngine: "v1.0",
    riskEngine: "v1.0",
    reportEngine: "v1.0",
    workerMode: "Lokalny",
    finalReport: "Dostępny jako JSON i widok panelu",
  },
  stages,
  mvpStages: stages.filter((stage) => [
    "upload", "preprocessing", "pose-v3", "hands", "metrics-engine",
    "ergonomics-worker", "risk-engine", "risk-worker", "report-engine",
    "report-worker", "report-json", "report-page", "report-completion",
    "pipeline-manager", "live-status", "beta-release",
  ].includes(stage.id)),
  publicWorkflow: [
    { id: "upload", title: "Prześlij film", description: "Nagranie trafia do prywatnego magazynu i kolejki.", status: "completed", group: "foundation" },
    { id: "analysis", title: "System analizuje ruch", description: "Modele wykrywają sylwetkę, ciało i dłonie.", status: "completed", group: "vision" },
    { id: "results", title: "Otrzymujesz wyniki", description: "System porządkuje metryki potrzebne do dalszej oceny.", status: "completed", group: "metrics" },
  ] satisfies readonly ProjectStage[],
  fullPipeline: [
    { id: "pipeline-film", title: "Film", description: "Krótkie nagranie stanowiska.", status: "completed", group: "foundation" },
    { id: "pipeline-upload", title: "Upload i kolejka", description: "Prywatny zapis i kontrolowane przetwarzanie.", status: "completed", group: "foundation" },
    { id: "pipeline-pose", title: "Analiza obrazu", description: "YOLOX-X, RTMW i walidacja dłoni.", status: "completed", group: "vision" },
    { id: "pipeline-pose-json", title: "Dane pozy", description: "Wersjonowany JSON i film wynikowy.", status: "completed", group: "vision" },
    { id: "pipeline-metrics", title: "Metryki", description: "Czternaście pomiarów i kontrola jakości.", status: "completed", group: "metrics" },
    { id: "pipeline-risk", title: "Risk Engine", description: "Ocena techniczna według wersjonowanego profilu.", status: "completed", group: "risk" },
    { id: "pipeline-risk-integration", title: "Integracja oceny", description: "Worker, Storage i widok w panelu.", status: "completed", group: "risk" },
    { id: "pipeline-report", title: "Raport V1", description: "Wersjonowany JSON, widok panelu i drukowanie w przeglądarce.", status: "completed", group: "reporting" },
  ] satisfies readonly ProjectStage[],
  metricGroups: [
    { name: "Tułów i szyja", description: "Pochylenie tułowia oraz ustawienie szyi." },
    { name: "Ramiona i łokcie", description: "Ułożenie ramion, łokci i przedramion." },
    { name: "Nadgarstki i dłonie", description: "Nadgarstki, zamknięcie dłoni i chwyt." },
    { name: "Czas utrzymywania pozycji", description: "Ekspozycja liczona przez niezależny Risk Engine." },
  ] satisfies readonly ProjectMetricGroup[],
  metricNames: [
    "Pochylenie tułowia", "Zgięcie szyi", "Elewacja lewego ramienia", "Elewacja prawego ramienia",
    "Zgięcie lewego łokcia", "Zgięcie prawego łokcia", "Pochylenie lewego przedramienia", "Pochylenie prawego przedramienia",
    "Zgięcie lewego nadgarstka", "Zgięcie prawego nadgarstka", "Zamknięcie lewej dłoni", "Zamknięcie prawej dłoni",
    "Chwyt lewej dłoni", "Chwyt prawej dłoni",
  ],
  technologies: [
    { name: "Next.js", description: "Aplikacja internetowa i widoki serwerowe." },
    { name: "Supabase", description: "Auth, baza danych i prywatny Storage." },
    { name: "Python", description: "Workery oraz silniki obliczeniowe." },
    { name: "YOLOX-X", description: "Wykrywanie głównego pracownika." },
    { name: "RTMW", description: "Analiza punktów całego ciała." },
    { name: "MediaPipe", description: "Dodatkowe punkty dłoni podlegające walidacji." },
    { name: "Metrics Engine", description: "Surowe pomiary geometryczne." },
    { name: "Risk Engine", description: "Niezależny screening oparty na profilu." },
    { name: "Report Engine", description: "Deterministyczne podsumowanie istniejących wyników." },
  ] satisfies readonly ProjectTechnology[],
  limitations: [
    "Analiza opiera się głównie na obrazie 2D.",
    "Zasłonięte części ciała mogą pozostać niewidoczne.",
    "Kadr, światło i ubranie wpływają na jakość danych.",
    "Niewiarygodne punkty są odrzucane, a nie uzupełniane.",
    "System wspiera analizę i nie zastępuje oceny specjalisty.",
  ],
} as const;

export function calculateProjectProgress(items: readonly ProjectStage[]) {
  if (items.length === 0) return 0;

  const score = items.reduce((total, stage) => {
    if (stage.status === "completed") return total + 1;
    if (stage.status === "in_progress") return total + 0.5;
    return total;
  }, 0);

  return Math.round((score / items.length) * 100);
}

export function countProjectStages(items: readonly ProjectStage[]) {
  return {
    completed: items.filter((stage) => stage.status === "completed").length,
    inProgress: items.filter((stage) => stage.status === "in_progress").length,
    planned: items.filter((stage) => stage.status === "planned").length,
  };
}
