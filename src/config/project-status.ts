export type ProjectStageStatus =
  | "completed"
  | "in_progress"
  | "planned";

export type ProjectStage = {
  id: string;
  title: string;
  description: string;
  status: ProjectStageStatus;
};

export type ProjectFeature = {
  title: string;
  description: string;
};

export type ProjectTechnology = {
  name: string;
  description: string;
};

export type ProjectMetric = {
  name: string;
  description: string;
};

const completedStages = [
  ["next-supabase", "Infrastruktura Next.js i Supabase", "Aplikacja internetowa, baza danych, Auth i prywatny Storage."],
  ["auth", "Rejestracja i logowanie", "Obsługa kont użytkowników i bezpiecznych sesji."],
  ["roles", "Profile oraz role administratora", "Rozdzielenie dostępu użytkownika i administratora."],
  ["storage", "Prywatny Storage", "Filmy źródłowe i wyniki są chronione regułami dostępu."],
  ["upload", "Upload krótkich filmów", "Przesyłanie nagrań stanowiska pracy z panelu użytkownika."],
  ["queue", "Kolejka analiz", "Kontrolowane przekazywanie nagrań do kolejnych etapów."],
  ["python-worker", "Python worker", "Lokalny proces obliczeniowy obsługujący filmy."],
  ["preprocessing", "Preprocessing filmów", "Odczyt parametrów i przygotowanie materiału do analizy."],
  ["yolox", "YOLOX-X person detection", "Wykrywanie pracownika i odrzucanie przypadkowych obiektów."],
  ["rtmw", "RTMW WholeBody", "Analiza 133 punktów ciała w każdej poprawnej klatce."],
  ["primary-tracking", "Tracking głównego pracownika", "Śledzenie jednej głównej osoby w aktywnym fragmencie."],
  ["active-segment", "Automatyczne przycinanie aktywnego fragmentu", "Zachowanie części nagrania, w której obecny jest pracownik."],
  ["body-smoothing", "Wygładzanie punktów ciała", "Stabilizacja trajektorii punktów bez zmiany modeli pozy."],
  ["hands", "Walidacja dłoni i palców", "Odrzucanie nienaturalnych i niewiarygodnych trajektorii palców."],
  ["h264", "Film wynikowy H.264", "Generowanie prywatnego filmu z wizualizacją zatwierdzonych punktów."],
  ["pose-v3", "Pose Pipeline V3.0", "Modułowy pipeline ciała i zwalidowanych dłoni."],
  ["metrics-v1", "Ergonomics Metrics Engine V1", "Lokalne obliczanie 14 surowych metryk geometrycznych wraz z jakością danych."],
  ["metrics-tests", "Testy jednostkowe metryk", "Testy geometrii, jakości, uszkodzonych klatek i podsumowań."],
] as const;

const inProgressStages = [
  ["metrics-worker-integration", "Integracja ergonomics engine z workerem", "Automatyczne uruchamianie metryk po zakończeniu Pose Pipeline."],
  ["metrics-supabase", "Zapis metryk do Supabase", "Bezpieczne przechowywanie wyników silnika metryk."],
  ["ergonomic-transition", "Automatyczne przejście do oceny ergonomicznej", "Przekazanie zatwierdzonych metryk do przyszłego etapu oceny."],
] as const;

const plannedStages = [
  ["threshold-panel", "Panel edycji progów", "Konfigurowalne zakresy i reguły oceny ergonomicznej."],
  ["risk-classification", "Klasyfikacja poziomu ryzyka", "Końcowa interpretacja pomiarów bez obietnicy automatycznej certyfikacji."],
  ["exposure", "Analiza czasu ekspozycji", "Pomiar czasu utrzymywania wymagających pozycji."],
  ["charts", "Wykresy", "Czytelna prezentacja zmian metryk w czasie."],
  ["final-report", "Raport końcowy", "Podsumowanie pomiarów, jakości danych i przyszłej oceny."],
  ["pdf", "PDF", "Eksport raportu do formatu PDF."],
  ["cleanup", "Automatyczne czyszczenie starych filmów", "Polityka retencji prywatnych materiałów wideo."],
  ["worker-hosting", "Hosting workera", "Uruchomienie procesu obliczeniowego poza komputerem lokalnym."],
  ["worker-monitoring", "Monitoring workera", "Nadzór dostępności, błędów i czasu przetwarzania."],
] as const;

function toStages(
  entries: readonly (readonly [string, string, string])[],
  status: ProjectStageStatus,
): ProjectStage[] {
  return entries.map(([id, title, description]) => ({
    id,
    title,
    description,
    status,
  }));
}

export const projectStatus = {
  projectName: "Ergonomia AI",
  versions: {
    posePipeline: "v3.0",
    ergonomicsMetricsEngine: "v1.0",
    workerMode: "Lokalny",
    workerOnline: "Planowany",
    finalReport: "Planowany",
  },
  stages: [
    ...toStages(completedStages, "completed"),
    ...toStages(inProgressStages, "in_progress"),
    ...toStages(plannedStages, "planned"),
  ],
  publicWorkflow: [
    {
      id: "recording-upload",
      title: "Przesłanie nagrania",
      description: "Krótki film trafia do prywatnego Storage i kolejki analiz.",
      status: "completed",
    },
    {
      id: "worker-detection",
      title: "Wykrycie pracownika",
      description: "YOLOX-X wskazuje głównego pracownika obecnego w nagraniu.",
      status: "completed",
    },
    {
      id: "body-pose",
      title: "Analiza pozy ciała",
      description: "RTMW WholeBody analizuje 133 punkty i ich jakość.",
      status: "completed",
    },
    {
      id: "hand-validation",
      title: "Walidacja ruchu dłoni",
      description: "Dedykowany pipeline ukrywa niewiarygodne punkty palców.",
      status: "completed",
    },
    {
      id: "ergonomic-metrics",
      title: "Obliczenie metryk ergonomicznych",
      description: "Silnik 14 metryk działa lokalnie; integracja z kolejką jest w realizacji.",
      status: "in_progress",
    },
    {
      id: "assessment-report",
      title: "Ocena i raport",
      description: "Końcowa klasyfikacja ryzyka i raport pozostają planowanym etapem.",
      status: "planned",
    },
  ] satisfies ProjectStage[],
  fullPipeline: [
    ["Film", "Krótki materiał źródłowy", "completed"],
    ["Bezpieczny upload", "Prywatny Supabase Storage", "completed"],
    ["Kolejka", "Kontrolowane przetwarzanie", "completed"],
    ["Preprocessing", "Parametry i przygotowanie filmu", "completed"],
    ["YOLOX-X", "Wykrycie pracownika", "completed"],
    ["RTMW WholeBody", "133 punkty ciała", "completed"],
    ["Walidacja dłoni", "Filtrowanie punktów palców", "completed"],
    ["JSON pozy", "Punkty, jakość i znaczniki czasu", "completed"],
    ["Metryki ergonomiczne", "14 surowych pomiarów — silnik lokalny", "in_progress"],
    ["Ocena ryzyka", "Planowany silnik interpretacji", "planned"],
    ["Raport", "Planowane podsumowanie i PDF", "planned"],
  ].map(([title, description, status], index) => ({
    id: `pipeline-${index + 1}`,
    title,
    description,
    status: status as ProjectStageStatus,
  })) satisfies ProjectStage[],
  workingFeatures: [
    ["Logowanie i konta użytkowników", "Bezpieczne sesje, profile i role."],
    ["Prywatne przesyłanie filmów", "Nagrania nie są przechowywane publicznie."],
    ["Kolejka analiz", "Każda analiza przechodzi przez kontrolowane etapy."],
    ["Wykrywanie pracownika", "YOLOX-X wybiera osobę analizowaną."],
    ["Tracking ciała", "RTMW WholeBody śledzi punkty głównego pracownika."],
    ["Analiza dłoni", "Osobny pipeline waliduje punkty palców."],
    ["Przycinanie aktywnego fragmentu", "Wynik skupia się na fragmencie z pracownikiem."],
    ["Film wynikowy", "Prywatny film H.264 prezentuje zatwierdzone punkty."],
    ["Dane pozy", "Pose Pipeline zapisuje wersjonowany JSON."],
    ["Lokalny silnik 14 metryk", "Surowe pomiary geometryczne wraz z jakością danych."],
  ].map(([title, description]) => ({ title, description })) satisfies ProjectFeature[],
  plannedFeatures: [
    ["Automatyczna integracja metryk", "Połączenie lokalnego silnika z kolejką analiz."],
    ["Konfigurowalne progi", "Edytowalne zasady oceny ergonomicznej."],
    ["Końcowa ocena ryzyka", "Interpretacja metryk pozostaje w przygotowaniu."],
    ["Wykresy", "Prezentacja pomiarów w czasie."],
    ["Raport PDF", "Eksport końcowego podsumowania."],
    ["Worker online", "Hosting i monitoring procesu obliczeniowego."],
  ].map(([title, description]) => ({ title, description })) satisfies ProjectFeature[],
  metrics: [
    ["Pochylenie tułowia", "Odchylenie osi tułowia od pionu."],
    ["Położenie szyi", "Kąt szyi względem osi tułowia."],
    ["Ułożenie ramion", "Elewacja lewego i prawego ramienia."],
    ["Kąty łokci", "Zgięcie obu stawów łokciowych."],
    ["Położenie przedramion", "Odchylenie przedramion od pionu."],
    ["Ustawienie nadgarstków", "Kąt wyliczany tylko dla zwalidowanej dłoni."],
    ["Zamknięcie dłoni", "Techniczny wskaźnik zgięcia czterech palców."],
    ["Chwyt kciuk–palec wskazujący", "Znormalizowana odległość pomiędzy opuszkami."],
  ].map(([name, description]) => ({ name, description })) satisfies ProjectMetric[],
  technologies: [
    ["YOLOX-X", "Wykrywa rzeczywistego pracownika w klatce filmu."],
    ["RTMW WholeBody", "Analizuje 133 punkty ciała i ich jakość."],
    ["Pipeline dłoni", "Odrzuca nieprawidłowe punkty oraz nienaturalne trajektorie palców."],
    ["Ergonomics Metrics Engine V1", "Oblicza 14 surowych metryk bez końcowej punktacji ryzyka."],
    ["Supabase", "Obsługuje Auth, dane i prywatny Storage."],
    ["Next.js", "Dostarcza aplikację internetową i bezpieczne widoki serwerowe."],
    ["Python", "Uruchamia lokalny worker oraz moduły obliczeniowe."],
  ].map(([name, description]) => ({ name, description })) satisfies ProjectTechnology[],
  limitations: [
    "Analiza bazuje obecnie głównie na obrazie 2D.",
    "Zasłonięte części ciała mogą być niewidoczne dla modeli.",
    "Jakość wyniku zależy od kamery, oświetlenia i kadru.",
    "Luźna odzież i elementy stanowiska mogą ograniczać detekcję.",
    "Niewiarygodne punkty są odrzucane zamiast sztucznie uzupełniane.",
    "Wynik nie jest diagnozą medyczną ani automatyczną decyzją BHP.",
  ],
} as const;

export function calculateProjectProgress(stages: readonly ProjectStage[]) {
  if (stages.length === 0) {
    return 0;
  }

  const score = stages.reduce((total, stage) => {
    if (stage.status === "completed") {
      return total + 1;
    }

    if (stage.status === "in_progress") {
      return total + 0.5;
    }

    return total;
  }, 0);

  return Math.round((score / stages.length) * 100);
}
