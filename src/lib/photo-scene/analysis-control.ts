import { emptyMeasurements } from "./schema.ts";
import type { NormalizedBox, SceneDetection, SceneDetectionCandidate, SceneObject, SceneState, WorkerDimensionSuggestion } from "../../types/photo-scene";

export type PhotoAnalysisStatus =
  | "NOT_ANALYZED"
  | "QUEUED"
  | "ANALYZING"
  | "READY"
  | "NO_DETECTIONS"
  | "ERROR"
  | "WORKER_OFFLINE";

export type PhotoAnalysisUi = {
  status: PhotoAnalysisStatus;
  label: string;
  buttonLabel: string;
  buttonEnabled: boolean;
  indeterminateProgress: boolean;
  stalled: boolean;
};

export type PhotoAnalysisContext = {
  processingStage: string | null;
  detection: SceneDetection | null;
  heartbeatAt?: string | null;
  updatedAt?: string | null;
  workerStatus?: "online" | "offline" | "degraded" | "restarting" | "crash_loop" | "unknown" | null;
  now?: number;
  stallAfterMs?: number;
};

export function derivePhotoAnalysisUi(context: PhotoAnalysisContext): PhotoAnalysisUi {
  const now = context.now ?? Date.now();
  const stallAfterMs = context.stallAfterMs ?? 120_000;
  const activityAt = validTimestamp(context.heartbeatAt) ?? validTimestamp(context.updatedAt);
  const stalled = activityAt !== null && now - activityAt > stallAfterMs;
  const workerOffline = context.workerStatus === "offline" || context.workerStatus === "crash_loop";
  if (context.processingStage === "scene-detection-processing") {
    if (stalled || workerOffline) return ui("WORKER_OFFLINE", "Analiza wygląda na zatrzymaną", "Ponów analizę zdjęcia", true, false, true);
    return ui("ANALYZING", "Analizowanie", "Analizuję zdjęcie…", false, true, false);
  }
  if (context.processingStage === "ready-for-scene-detection") {
    if (stalled && context.workerStatus !== "online" && context.workerStatus !== "restarting") return ui("WORKER_OFFLINE", "Worker analizy zdjęcia nie odpowiada", "Ponów analizę zdjęcia", true, false, true);
    return ui("QUEUED", "W kolejce", "Analiza w kolejce…", false, true, false);
  }
  if (context.processingStage === "scene-detection-failed") return ui("ERROR", "Błąd", "Ponów analizę zdjęcia", true, false, false);
  if (context.detection) {
    return context.detection.candidates.length
      ? ui("READY", "Gotowe", "Analizuj ponownie", true, false, false)
      : ui("NO_DETECTIONS", "Nie wykryto elementów", "Analizuj ponownie", true, false, false);
  }
  return ui("NOT_ANALYZED", "Nie analizowano", "Analizuj zdjęcie", true, false, false);
}

export function mergeSceneDetection(state: SceneState, detection: SceneDetection | null): SceneState {
  if (!detection) return state;
  const objects = [...state.objects];
  const candidateObjectIds = new Map<string, string>();
  for (const candidate of detection.candidates) {
    const match = bestObjectMatch(objects, candidate);
    if (match) {
      candidateObjectIds.set(candidate.id, match.id);
      continue;
    }
    const created = detectedObject(candidate);
    objects.push(created);
    candidateObjectIds.set(candidate.id, created.id);
  }

  const workerSuggestions = [...state.workerSuggestions];
  for (const incoming of detection.dimension_suggestions ?? []) {
    const suggestion = { ...incoming, object_id: candidateObjectIds.get(incoming.object_id) ?? incoming.object_id };
    if (!objects.some((object) => object.id === suggestion.object_id)) continue;
    if (workerSuggestions.some((existing) => sameSuggestion(existing, suggestion))) continue;
    workerSuggestions.push(suggestion);
  }
  const verticalAngle = detection.perspective_evidence?.dominant_vertical_angle_deg;
  const calibration = !state.calibration.verticalDirectionConfirmed && typeof verticalAngle === "number" && Number.isFinite(verticalAngle)
    ? { ...state.calibration, verticalDirection: suggestedUpVector(verticalAngle), verticalDirectionSource: "WORKER_SUGGESTED" as const }
    : state.calibration;
  return { ...state, objects, workerSuggestions, calibration };
}

export function intersectionOverUnion(first: NormalizedBox, second: NormalizedBox) {
  const left = Math.max(first.x, second.x);
  const top = Math.max(first.y, second.y);
  const right = Math.min(first.x + first.width, second.x + second.width);
  const bottom = Math.min(first.y + first.height, second.y + second.height);
  const intersection = Math.max(0, right - left) * Math.max(0, bottom - top);
  const union = first.width * first.height + second.width * second.height - intersection;
  return union > 0 ? intersection / union : 0;
}

function bestObjectMatch(objects: SceneObject[], candidate: SceneDetectionCandidate) {
  return objects
    .map((object) => ({ object, overlap: intersectionOverUnion(object.bbox, candidate.bounding_box) }))
    .filter(({ object, overlap }) => overlap >= 0.58 && (object.type === candidate.suggested_scene_type || object.sourceClass === candidate.source_class))
    .sort((left, right) => right.overlap - left.overlap)[0]?.object ?? null;
}

function detectedObject(candidate: SceneDetectionCandidate): SceneObject {
  return {
    id: candidate.id,
    sourceClass: candidate.source_class,
    type: candidate.suggested_scene_type,
    name: candidate.suggested_scene_type.replaceAll("_", " ").toLocaleLowerCase("pl-PL"),
    bbox: candidate.bounding_box,
    detectorConfidence: candidate.confidence,
    source: candidate.source,
    status: "DETECTED",
    visible: true,
    locked: false,
    measurements: emptyMeasurements(),
    geometryMeasurements: [],
    interactionPoints: [],
    referencePoint: null,
  };
}

function sameSuggestion(first: WorkerDimensionSuggestion, second: WorkerDimensionSuggestion) {
  if (first.id === second.id) return true;
  if (first.object_id !== second.object_id || first.dimension_type !== second.dimension_type) return false;
  return pointDistance(first.endpoints.start, second.endpoints.start) < .025 && pointDistance(first.endpoints.end, second.endpoints.end) < .025;
}

function pointDistance(first: { x: number; y: number }, second: { x: number; y: number }) {
  return Math.hypot(first.x - second.x, first.y - second.y);
}

function suggestedUpVector(screenAngleDeg: number) {
  const radians = screenAngleDeg * Math.PI / 180;
  const vector = { x: Math.cos(radians), y: Math.sin(radians) };
  return vector.y > 0 ? { x: -vector.x, y: -vector.y } : vector;
}

function validTimestamp(value: string | null | undefined) {
  if (!value) return null;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function ui(
  status: PhotoAnalysisStatus,
  label: string,
  buttonLabel: string,
  buttonEnabled: boolean,
  indeterminateProgress: boolean,
  stalled: boolean,
): PhotoAnalysisUi {
  return { status, label, buttonLabel, buttonEnabled, indeterminateProgress, stalled };
}
