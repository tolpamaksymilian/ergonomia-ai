export type ProjectStageStatus = "completed" | "in_progress" | "planned";

export const POSE_PIPELINE_VERSION = "pose-v5.1-beta.1";

export type ProjectStageGroup =
  | "foundation"
  | "vision"
  | "metrics"
  | "risk"
  | "reporting"
  | "scene_builder"
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

export type PublicProjectPlan = {
  id: string;
  title: string;
  description: string;
};

const stages = [
  { id: "next-app", title: "Aplikacja Next.js", description: "Interfejs i bezpieczne widoki serwerowe.", status: "completed", group: "foundation" },
  { id: "design-system", title: "Centralny design system", description: "Wspólne tokeny kolorów, powierzchni, obramowań i kontrolek.", status: "completed", group: "foundation" },
  { id: "light-dark-theme", title: "Jasny i ciemny motyw", description: "Domyślny jasny motyw z zapamiętywanym trybem ciemnym.", status: "completed", group: "foundation" },
  { id: "ui-consistency", title: "Spójność interfejsu", description: "Ujednolicone ekrany publiczne, panel, analiza i raport.", status: "completed", group: "foundation" },
  { id: "auth", title: "Supabase Auth", description: "Konta, sesje i role użytkowników.", status: "completed", group: "foundation" },
  { id: "private-storage", title: "Prywatny Storage", description: "Chronione nagrania i wyniki analiz.", status: "completed", group: "foundation" },
  { id: "upload", title: "Upload filmów", description: "Przesyłanie krótkich nagrań z panelu.", status: "completed", group: "foundation" },
  { id: "queue", title: "Kolejka analiz", description: "Kontrolowane przekazywanie zadań workerom.", status: "completed", group: "foundation" },
  { id: "preprocessing", title: "Preprocessing", description: "Przygotowanie filmu do analizy pozy.", status: "completed", group: "vision" },
  { id: "pose-v3", title: "Pose Pipeline V5 beta", description: "Evidence fusion i ograniczone ponowne przetwarzanie trudnych fragmentów.", status: "completed", group: "vision" },
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
  { id: "company-method-specs", title: "Specyfikacja metod zakładowych", description: "Audyt źródłowego skoroszytu i wersjonowane reguły JSON.", status: "completed", group: "risk" },
  { id: "owas-company", title: "OWAS zakładowy", description: "Klasyfikacja pozycji z jawnym manualnym obciążeniem.", status: "completed", group: "risk" },
  { id: "analysis-context", title: "Kontekst analizy i stanowiska", description: "Wersjonowany kontekst, słownik stanowisk i wielokrotne kategorie.", status: "completed", group: "infrastructure" },
  { id: "photo-scene-builder", title: "Projektowanie stanowiska ze zdjęcia — Beta", description: "Regionowy model sceny, Constraint Graph, Scene Geometry V2 i stabilna projekcja operatora.", status: "in_progress", group: "scene_builder" },
  { id: "photo-scene-worker", title: "Scene Detection Worker", description: "Automatyczny, odseparowany etap YOLOX-X z ręcznym fallbackiem.", status: "in_progress", group: "scene_builder" },
  { id: "photo-scene-reconstruction", title: "Scene Reconstruction Worker", description: "Odseparowany etap CPU dopasowujący regiony, płaszczyzny i jawne wymiary bez zgadywania braków.", status: "in_progress", group: "scene_builder" },
  { id: "photo-scene-assessment", title: "Scene Ergonomics Engine V1", description: "Deterministyczna ocena geometrii, postawy 3D, dosiężności, clearance, RULA/REBA i wariantów projektu.", status: "completed", group: "scene_builder" },
  { id: "company-method-inputs", title: "Dane kontekstowe metod", description: "Prywatny zapis i przeliczanie bez ponownego uruchamiania GPU.", status: "completed", group: "risk" },
  { id: "production-profile", title: "Produkcyjny profil progów", description: "Profil zatwierdzony przez specjalistę.", status: "planned", group: "risk" },
  { id: "threshold-panel", title: "Panel progów", description: "Konfiguracja wersjonowanych profili.", status: "planned", group: "risk" },
  { id: "report-engine", title: "Report Engine V2.3", description: "Raport obejmuje stanowisko, kontekst i kategorie oraz zachowuje śledzenie źródła danych.", status: "completed", group: "reporting" },
  { id: "report-worker", title: "Report Worker V1", description: "Osobny etap generowania raportu po ocenie ryzyka.", status: "completed", group: "reporting" },
  { id: "report-json", title: "analysis-report.json", description: "Wersjonowany raport w prywatnym Storage.", status: "completed", group: "reporting" },
  { id: "report-page", title: "Strona raportu", description: "Czytelna prezentacja raportu w panelu.", status: "completed", group: "reporting" },
  { id: "report-completion", title: "Zakończenie analizy", description: "Stan completed i postęp 100% po zapisie raportu.", status: "completed", group: "reporting" },
  { id: "browser-print", title: "Drukowanie raportu", description: "Wersja do druku dostępna w przeglądarce.", status: "completed", group: "reporting" },
  { id: "charts", title: "Wykresy", description: "Zmiany metryk i ekspozycji w czasie.", status: "planned", group: "reporting" },
  { id: "key-frames", title: "Obrazy kluczowych klatek", description: "Generowanie obrazów reprezentatywnych momentów analizy.", status: "planned", group: "reporting" },
  { id: "pdf", title: "PDF", description: "Eksport końcowego raportu.", status: "planned", group: "reporting" },
  { id: "rula", title: "RULA beta", description: "Evidence-aware ocena kończyn górnych z jawnym zakresem braków.", status: "completed", group: "reporting" },
  { id: "reba", title: "REBA beta", description: "Evidence-aware ocena całego ciała bez zgadywania obciążenia.", status: "completed", group: "reporting" },
  { id: "pipeline-manager", title: "Pipeline Manager", description: "Jeden nadzorowany start pełnego łańcucha workerów.", status: "completed", group: "infrastructure" },
  { id: "pipeline-supervisor", title: "Pipeline Supervisor", description: "Automatyczny start, heartbeat, preflight i kontrolowany restart lokalnego pipeline’u.", status: "completed", group: "infrastructure" },
  { id: "live-status", title: "Automatyczne statusy", description: "Lekki polling aktywnych analiz i pojawienie się raportu bez ręcznego odświeżania.", status: "completed", group: "infrastructure" },
  { id: "history-v2", title: "Historia analiz 2.0", description: "Wyszukiwanie, filtry URL, kategorie AND/OR i paginacja serwerowa.", status: "completed", group: "infrastructure" },
  { id: "beta-release", title: "Wersja testowa", description: "Dwa niezależne tryby: analiza filmu oraz Photo Scene Builder w v0.20.0-beta.1.", status: "completed", group: "infrastructure" },
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
  { id: "scene_builder", label: "Projekt ze zdjęcia", description: "Interaktywny model 3D z deterministyczną oceną projektową." },
];

export const projectStatus = {
  projectName: "Ergonomia AI",
  versions: {
    application: "v0.20.0-beta.1",
    sceneBuilder: "photo-scene-builder-v0.9-beta.1",
    sceneGeometry: "scene-geometry-v2.0-beta.1",
    sceneReconstruction: "scene-reconstruction-v1.0-beta.1",
    sceneErgonomics: "scene-ergonomics-v1.0-beta.1",
    sceneDesignReport: "scene-design-report-v1.0-beta.1",
    sceneDetection: "scene-detection-v0.2-beta.1",
    worker: "v0.7.0-beta.1",
    supervisor: "pipeline-supervisor-v1.0-beta.1",
    posePipeline: POSE_PIPELINE_VERSION,
    ergonomicsMetricsEngine: "v1.0",
    riskEngine: "v1.0",
    reportEngine: "analysis-report-v2.3-beta.1",
    assessmentEngine: "assessment-v1.0-beta.1",
    rula: "rula-v1.0-beta.1",
    reba: "reba-v1.0-beta.1",
    companyMethods: "company-methods-v1.2-beta.1",
    owas: "owas-company-v1.1-beta.1",
    workerMode: "Lokalny",
    finalReport: "Dostępny jako JSON i widok panelu",
  },
  stages,
  mvpStages: stages.filter((stage) => [
    "upload", "preprocessing", "pose-v3", "hands", "metrics-engine",
    "ergonomics-worker", "risk-engine", "risk-worker", "report-engine",
    "report-worker", "report-json", "report-page", "report-completion",
    "pipeline-manager", "pipeline-supervisor", "live-status", "beta-release",
  ].includes(stage.id)),
  publicWorkflow: [
    { id: "upload", title: "Prześlij film", description: "Nagranie trafia do prywatnego magazynu i kolejki.", status: "completed", group: "foundation" },
    { id: "analysis", title: "System analizuje ruch", description: "Modele wykrywają sylwetkę, ciało i dłonie.", status: "completed", group: "vision" },
    { id: "results", title: "Otrzymujesz raport", description: "Wyniki, poziom ryzyka i ograniczenia trafiają do jednego widoku.", status: "completed", group: "reporting" },
  ] satisfies readonly ProjectStage[],
  fullPipeline: [
    { id: "pipeline-film", title: "Film", description: "Krótkie nagranie stanowiska.", status: "completed", group: "foundation" },
    { id: "pipeline-upload", title: "Upload i kolejka", description: "Prywatny zapis i kontrolowane przetwarzanie.", status: "completed", group: "foundation" },
    { id: "pipeline-pose", title: "Analiza obrazu", description: "YOLOX-X, RTMW i walidacja dłoni.", status: "completed", group: "vision" },
    { id: "pipeline-pose-json", title: "Dane pozy", description: "Wersjonowany JSON i film wynikowy.", status: "completed", group: "vision" },
    { id: "pipeline-metrics", title: "Metryki", description: "Czternaście pomiarów i kontrola jakości.", status: "completed", group: "metrics" },
    { id: "pipeline-risk", title: "Risk Engine", description: "Ocena techniczna według wersjonowanego profilu.", status: "completed", group: "risk" },
    { id: "pipeline-risk-integration", title: "Integracja oceny", description: "Worker, Storage i widok w panelu.", status: "completed", group: "risk" },
    { id: "pipeline-company-methods", title: "Metody zakładowe", description: "OWAS i opcjonalne dane kontekstowe z prywatnym zapisem.", status: "completed", group: "risk" },
    { id: "pipeline-report", title: "Raport V2", description: "Priorytetowe wnioski, dowody, zalecenia i widok do druku.", status: "completed", group: "reporting" },
  ] satisfies readonly ProjectStage[],
  metricGroups: [
    { name: "Sylwetka i ruch", description: "Pozycja ciała oraz zmiany ruchu w kolejnych klatkach." },
    { name: "Kąty i metryki", description: "Pomiary tułowia, szyi, ramion i kończyn." },
    { name: "Dłonie i nadgarstki", description: "Ułożenie nadgarstków, zamknięcie dłoni i chwyt." },
    { name: "Ryzyko i raport", description: "Techniczna klasyfikacja oraz uporządkowane podsumowanie." },
  ] satisfies readonly ProjectMetricGroup[],
  publicPlans: [
    { id: "charts", title: "Wykresy i kluczowe momenty", description: "Podgląd zmian kątów i najważniejszych fragmentów filmu." },
    { id: "pdf", title: "Raport PDF", description: "Dokument gotowy do pobrania i archiwizacji." },
    { id: "methods-validation", title: "Walidacja metod zakładowych", description: "Potwierdzenie progów i brakujących instrukcji przez kompetentnego specjalistę." },
    { id: "simulator", title: "Ocena projektowanej sceny", description: "Przyszła interpretacja zatwierdzonej geometrii Photo Scenario Buildera." },
  ] satisfies readonly PublicProjectPlan[],
  publicTechnologies: [
    "Next.js",
    "Supabase",
    "Python",
    "PyTorch",
    "YOLOX-X",
    "RTMW",
    "MediaPipe",
    "Three.js",
  ],
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
  ],
  disclaimer: "System wspiera analizę i nie zastępuje oceny specjalisty.",
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
