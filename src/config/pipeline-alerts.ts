export type PipelineWatchdogCode =
  | "QUEUE_OK"
  | "QUEUE_WAITING"
  | "WORKER_OFFLINE"
  | "WORKER_BUSY"
  | "CLAIM_DELAY"
  | "PROCESSING"
  | "DEGRADED"
  | "HEALTH_PERSISTENCE_DEGRADED"
  | "STALLED"
  | "FAILED"
  | "COMPLETED"
  | "CRASH_LOOP";

export const pipelineAlerts: Record<PipelineWatchdogCode, { title: string; description: string; tone: "neutral" | "info" | "warning" | "error" | "success" }> = {
  QUEUE_OK: { title: "Analiza oczekuje w kolejce", description: "Worker jest dostępny i powinien automatycznie pobrać zadanie.", tone: "neutral" },
  QUEUE_WAITING: { title: "Film znajduje się w kolejce", description: "Worker działa, ale nie pobrał jeszcze tej analizy.", tone: "warning" },
  WORKER_OFFLINE: { title: "Worker analizy nie jest uruchomiony", description: "Film został zapisany, ale lokalny moduł analizy nie odpowiada.", tone: "error" },
  WORKER_BUSY: { title: "Worker analizuje inne nagranie", description: "Ta analiza pozostaje bezpiecznie w kolejce i ruszy automatycznie.", tone: "info" },
  CLAIM_DELAY: { title: "Worker nie może jeszcze pobrać analizy", description: "System sprawdza kolejkę i spróbuje odzyskać etap automatycznie.", tone: "warning" },
  PROCESSING: { title: "Pipeline pracuje", description: "Heartbeat jest świeży; długi etap Pose nie jest traktowany jako zatrzymany tylko z powodu stałego procentu.", tone: "info" },
  DEGRADED: { title: "Worker wymaga uwagi", description: "Supervisor działa, ale kontrola gotowości wykryła problem. Szczegóły techniczne wskazują brakujący element.", tone: "warning" },
  HEALTH_PERSISTENCE_DEGRADED: { title: "Worker działa z ograniczoną diagnostyką", description: "Analiza może być kontynuowana, ale zapis lub odczyt lokalnego heartbeat jest chwilowo ograniczony.", tone: "warning" },
  STALLED: { title: "Etap nie odpowiada", description: "Ostatnia aktywność workera jest nieaktualna. Dane wcześniejszych etapów pozostają zachowane.", tone: "error" },
  FAILED: { title: "Etap analizy nie powiódł się", description: "Można bezpiecznie ponowić wyłącznie nieudany etap.", tone: "error" },
  COMPLETED: { title: "Pipeline zakończony", description: "Wymagane artefakty analizy zostały przygotowane.", tone: "success" },
  CRASH_LOOP: { title: "Worker zatrzymał automatyczne restarty", description: "Wykryto serię awarii. Sprawdź diagnostykę przed ponownym uruchomieniem.", tone: "error" },
};
