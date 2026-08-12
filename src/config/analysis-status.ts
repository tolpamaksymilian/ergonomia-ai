export type AnalysisVisualType =
  | "neutral"
  | "queued"
  | "active"
  | "success"
  | "error";

export type AnalysisStatusDefinition = {
  label: string;
  shortLabel: string;
  description: string;
  defaultProgress: number;
  visualType: AnalysisVisualType;
  active: boolean;
  error: boolean;
  final: boolean;
  canShowReport: boolean;
};

const stageDefinitions = {
  queued: status("W kolejce", "W kolejce", "Film czeka na preprocessing.", 0, "queued", true),
  claimed: status("Przygotowanie filmu", "Preprocessing", "Worker przejął film do przygotowania.", 1, "active", true),
  "claimed-for-preprocessing": status("Przygotowanie filmu", "Preprocessing", "Worker przejął film do przygotowania.", 1, "active", true),
  "downloading-source": status("Pobieranie filmu", "Preprocessing", "Pobieramy prywatne nagranie źródłowe.", 3, "active", true),
  "preprocessing-video": status("Przygotowanie filmu", "Preprocessing", "Sprawdzamy i przygotowujemy nagranie do analizy pozy.", 8, "active", true),
  "saving-preprocessing-results": status("Kończenie preprocessingu", "Preprocessing", "Zapisujemy parametry przygotowanego nagrania.", 18, "active", true),
  "ready-for-ai": status("Film gotowy do analizy pozy", "Gotowe do Pose", "Nagranie czeka na Pose Pipeline V3.0.", 20, "queued", true),
  "pose-claimed": status("Analiza pozy w toku", "Pose Pipeline", "Pose Pipeline V3.0 przejął nagranie.", 20, "active", true),
  "downloading-for-pose": status("Analiza pozy w toku", "Pose Pipeline", "Pobieramy film do analizy pozy.", 21, "active", true),
  "downloading-for-pose-v3": status("Analiza pozy w toku", "Pose Pipeline", "Pobieramy film do analizy pozy.", 21, "active", true),
  "initializing-pose-inference": status("Analiza pozy w toku", "Pose Pipeline", "Przygotowujemy modele analizy sylwetki.", 25, "active", true),
  "pose-inference": status("Analiza pozy w toku", "Pose Pipeline", "Wykrywamy i śledzimy sylwetkę pracownika.", 30, "active", true),
  "pose-inference-active-segment-v3": status("Analiza pozy w toku", "Pose Pipeline", "Analizujemy aktywny fragment ruchu ciała i dłoni.", 30, "active", true),
  "pose-v3-rendering-validated-results": status("Tworzenie wyniku pozy", "Pose Pipeline", "Tworzymy film z zatwierdzonymi punktami pozy.", 73, "active", true),
  "uploading-pose-results": status("Zapisywanie wyników pozy", "Pose Pipeline", "Przesyłamy wyniki pozy do prywatnego Storage.", 91, "active", true),
  "uploading-pose-results-v3": status("Zapisywanie wyników pozy", "Pose Pipeline", "Przesyłamy wyniki pozy do prywatnego Storage.", 91, "active", true),
  "saving-pose-results": status("Kończenie analizy pozy", "Pose Pipeline", "Kończymy zapis wyników Pose Pipeline.", 97, "active", true),
  "saving-pose-results-v3": status("Kończenie analizy pozy", "Pose Pipeline", "Kończymy zapis wyników Pose Pipeline.", 97, "active", true),
  "ready-for-ergonomics": status("Poza gotowa do metryk", "Gotowe do metryk", "Analiza pozy jest gotowa. Oczekuje na obliczenie metryk ergonomicznych.", 75, "queued", true),
  "ergonomics-processing": status("Obliczanie metryk", "Metryki", "Obliczamy techniczne metryki ergonomiczne dla wykrytego ruchu.", 78, "active", true),
  "ready-for-risk-assessment": status("Metryki gotowe", "Gotowe do oceny", "Metryki są gotowe i czekają na techniczną ocenę ryzyka.", 90, "queued", true),
  "risk-processing": status("Ocena techniczna w toku", "Risk Engine", "Risk Engine interpretuje metryki według jawnego profilu rozwojowego.", 92, "active", true),
  "ready-for-report": status("Ocena gotowa", "Gotowe do raportu", "Ocena techniczna jest gotowa i czeka na przygotowanie raportu.", 97, "queued", true),
  "report-processing": status("Raport w przygotowaniu", "Raport", "Porządkujemy istniejące wyniki w raport analizy.", 98, "active", true),
  "photo-uploading": status("Przesyłanie zdjęcia", "Przesyłanie", "Oryginalne zdjęcie jest zapisywane w prywatnym Storage.", 0, "active", true),
  "ready-for-scene-detection": status("Projekt czeka na detekcję", "W kolejce", "Scene Detection Worker czeka na możliwość wykrycia kandydatów elementów.", 10, "queued", true),
  "scene-detection-processing": status("Wykrywanie elementów", "Detekcja sceny", "YOLOX-X wyszukuje kandydatów elementów do ręcznego potwierdzenia.", 20, "active", true),
  "scene-detection-failed": status("Detekcja niedostępna", "Tryb ręczny", "Automatyczna detekcja nie powiodła się. Edytor i ręczne dodawanie elementów pozostają dostępne.", 20, "error", false, true, true),
  "scene-ready": status("Scena gotowa do edycji", "Scena gotowa", "Kandydaci zostali przygotowani. Potwierdź elementy, skalibruj obraz i ustaw model człowieka.", 100, "success", false, false, true),
  completed: status("Analiza gotowa", "Gotowa", "Raport jest dostępny.", 100, "success", false, false, true, true),
  "processing-failed": status("Błąd przetwarzania", "Błąd etapu", "Nie udało się przygotować filmu lub wykryć pozycji.", 0, "error", false, true, true),
  "ergonomics-failed": status("Błąd metryk", "Błąd metryk", "Nie udało się obliczyć metryk ergonomicznych. Wyniki pozy zostały zachowane.", 75, "error", false, true, true),
  "risk-failed": status("Błąd oceny ryzyka", "Błąd oceny", "Nie udało się ocenić ryzyka. Wyniki pozy i metryk zostały zachowane.", 90, "error", false, true, true),
  "report-failed": status("Błąd raportu", "Błąd raportu", "Nie udało się przygotować raportu. Wcześniejsze wyniki zostały zachowane.", 97, "error", false, true, true),
} as const satisfies Record<string, AnalysisStatusDefinition>;

const baseDefinitions = {
  draft: status("Wersja robocza", "Robocza", "Analiza nie została uruchomiona.", 0, "neutral", false),
  uploading: status("Przesyłanie filmu", "Przesyłanie", "Film jest przesyłany do prywatnego Storage.", 0, "active", true),
  queued: stageDefinitions.queued,
  processing: status("Analiza w toku", "W toku", "Trwa przetwarzanie analizy.", 1, "active", true),
  completed: stageDefinitions.completed,
  failed: status("Analiza nieudana", "Nieudana", "Nie udało się ukończyć bieżącego etapu analizy.", 0, "error", false, true, true),
  cancelled: status("Analiza anulowana", "Anulowana", "Analiza została anulowana.", 0, "neutral", false, false, true),
} as const satisfies Record<string, AnalysisStatusDefinition>;

function status(
  label: string,
  shortLabel: string,
  description: string,
  defaultProgress: number,
  visualType: AnalysisVisualType,
  active: boolean,
  error = false,
  final = false,
  canShowReport = false,
): AnalysisStatusDefinition {
  return { label, shortLabel, description, defaultProgress, visualType, active, error, final, canShowReport };
}

export function getAnalysisStatusDefinition(
  technicalStatus: string,
  processingStage: string | null,
): AnalysisStatusDefinition {
  if (processingStage && processingStage in stageDefinitions) {
    return stageDefinitions[processingStage as keyof typeof stageDefinitions];
  }
  return baseDefinitions[technicalStatus as keyof typeof baseDefinitions] ?? baseDefinitions.draft;
}

export function isAnalysisActive(statusValue: string, processingStage: string | null) {
  return getAnalysisStatusDefinition(statusValue, processingStage).active;
}

export function getSafeAnalysisErrorMessage(processingStage: string | null) {
  const definition = getAnalysisStatusDefinition("failed", processingStage);
  return definition.error ? definition.description : baseDefinitions.failed.description;
}

export const analysisPipelineStages = stageDefinitions;
