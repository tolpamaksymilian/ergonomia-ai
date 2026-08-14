import type {
  CalibrationReference, GeometryMeasurement, MeasurementAxis, MeasurementKind,
  MeasurementPlane, MeasurementPurpose, NormalizedPoint, ObjectDimensionKey,
  ReferenceDimensionType,
} from "../../types/photo-scene";

export type MeasurementSemantics = {
  measurementKind: MeasurementKind;
  axis: MeasurementAxis;
  plane: MeasurementPlane;
  purpose: MeasurementPurpose;
};

export type CalibrationValidation = {
  valid: boolean;
  code: "VALID_VERTICAL_REFERENCE" | "NOT_SELECTED_FOR_CALIBRATION" | "SEMANTICS_REVIEW_REQUIRED"
    | "WRONG_PURPOSE" | "WRONG_AXIS" | "WRONG_PLANE" | "UNSUPPORTED_KIND"
    | "INVALID_VALUE" | "INVALID_WORLD_HEIGHTS" | "DIRECTION_WARNING";
  warning: string | null;
};

const VERTICAL_KINDS = new Set<MeasurementKind>([
  "VERTICAL_HEIGHT", "OBJECT_HEIGHT", "WORK_SURFACE_HEIGHT", "SHELF_HEIGHT",
  "SEAT_HEIGHT", "SCREEN_HEIGHT",
]);

export const MEASUREMENT_KIND_LABELS: Record<MeasurementKind, string> = {
  VERTICAL_HEIGHT: "Wysokość pionowa",
  HORIZONTAL_WIDTH: "Szerokość pozioma",
  DEPTH: "Głębokość",
  FLOOR_DISTANCE: "Odległość po podłodze",
  OBJECT_HEIGHT: "Wysokość obiektu",
  OBJECT_WIDTH: "Szerokość obiektu",
  OBJECT_DEPTH: "Głębokość obiektu",
  WORK_SURFACE_HEIGHT: "Wysokość blatu od podłogi",
  SHELF_HEIGHT: "Wysokość półki od podłogi",
  SEAT_HEIGHT: "Wysokość siedziska od podłogi",
  SCREEN_HEIGHT: "Wysokość ekranu",
  CUSTOM_DISTANCE: "Inny wymiar",
};

export function semanticsForReferenceType(type: ReferenceDimensionType): MeasurementSemantics {
  switch (type) {
    case "HEIGHT": return vertical("VERTICAL_HEIGHT");
    case "WORK_SURFACE_HEIGHT": return vertical("WORK_SURFACE_HEIGHT");
    case "SHELF_HEIGHT": return vertical("SHELF_HEIGHT");
    case "REACH_HEIGHT": return { ...vertical("VERTICAL_HEIGHT"), purpose: "HUMAN_SCALE_VALIDATION" };
    case "WIDTH": return { measurementKind: "HORIZONTAL_WIDTH", axis: "HORIZONTAL", plane: "OBJECT_FRONT_PLANE", purpose: "OBJECT_DESCRIPTION" };
    case "DEPTH": return { measurementKind: "DEPTH", axis: "GROUND_Y", plane: "OBJECT_TOP_PLANE", purpose: "OBJECT_DESCRIPTION" };
    case "DISTANCE": return { measurementKind: "FLOOR_DISTANCE", axis: "GROUND_X", plane: "GROUND_PLANE", purpose: "OBJECT_DESCRIPTION" };
    default: return { measurementKind: "CUSTOM_DISTANCE", axis: "ARBITRARY", plane: "UNKNOWN_PLANE", purpose: "INFORMATION_ONLY" };
  }
}

export function semanticsForDimensionKey(key: ObjectDimensionKey): MeasurementSemantics {
  if (key === "widthCm" || key === "seatWidthCm" || key === "workingWidthCm") {
    return { measurementKind: "OBJECT_WIDTH", axis: "HORIZONTAL", plane: "OBJECT_FRONT_PLANE", purpose: "OBJECT_DESCRIPTION" };
  }
  if (key === "depthCm" || key === "seatDepthCm" || key === "userDistanceCm") {
    return { measurementKind: "OBJECT_DEPTH", axis: "GROUND_Y", plane: "OBJECT_TOP_PLANE", purpose: "OBJECT_DESCRIPTION" };
  }
  if (key === "workSurfaceHeightCm") return vertical("WORK_SURFACE_HEIGHT", "OBJECT_DESCRIPTION");
  if (key === "keyShelfHeightCm") return vertical("SHELF_HEIGHT", "OBJECT_DESCRIPTION");
  if (key === "seatHeightCm") return vertical("SEAT_HEIGHT", "OBJECT_DESCRIPTION");
  if (key === "screenCenterHeightCm" || key === "screenHeightCm") return vertical("SCREEN_HEIGHT", "OBJECT_DESCRIPTION");
  return vertical("OBJECT_HEIGHT", "OBJECT_DESCRIPTION");
}

export function isVerticalCalibrationReference(reference: CalibrationReference): boolean {
  return validateMeasurementForCalibration(reference).valid;
}

export function validateMeasurementForCalibration(reference: CalibrationReference): CalibrationValidation {
  if (!reference.useForCalibration) return invalid("NOT_SELECTED_FOR_CALIBRATION", null);
  if (reference.semanticStatus !== "CONFIRMED") return invalid("SEMANTICS_REVIEW_REQUIRED", "Najpierw potwierdź znaczenie tego pomiaru.");
  if (reference.purpose !== "CALIBRATION" && reference.purpose !== "HUMAN_SCALE_VALIDATION") return invalid("WRONG_PURPOSE", "Pomiar opisuje obiekt, ale nie jest referencją kalibracyjną.");
  if (!VERTICAL_KINDS.has(reference.measurementKind)) return invalid("UNSUPPORTED_KIND", "Tylko wysokość pionowa może zasilać skalę człowieka.");
  if (reference.axis !== "VERTICAL") return invalid("WRONG_AXIS", "Oś pomiaru nie jest pionowa.");
  if (reference.plane !== "VERTICAL_PLANE") return invalid("WRONG_PLANE", "Pomiar nie należy do płaszczyzny pionowej.");
  if (!Number.isFinite(reference.valueCm) || reference.valueCm <= 0 || !Number.isFinite(reference.pixelDistance) || reference.pixelDistance <= 0) return invalid("INVALID_VALUE", "Pomiar nie ma prawidłowej wartości lub długości obrazu.");
  const bottom = reference.worldAnchors.bottom?.worldHeightCm;
  const top = reference.worldAnchors.top?.worldHeightCm;
  if (bottom === null || bottom === undefined || top === null || top === undefined || !Number.isFinite(bottom) || !Number.isFinite(top) || top <= bottom) return invalid("INVALID_WORLD_HEIGHTS", "Wysokość wymaga dolnego i górnego poziomu świata.");
  if (Math.abs((top - bottom) - reference.valueCm) > Math.max(.5, reference.valueCm * .01)) return invalid("INVALID_WORLD_HEIGHTS", "Różnica wysokości punktów nie odpowiada wartości pomiaru.");
  return { valid: true, code: "VALID_VERTICAL_REFERENCE", warning: null };
}

export function measurementDirectionWarning(start: NormalizedPoint, end: NormalizedPoint, semantics: Pick<MeasurementSemantics, "axis">, verticalDirection: NormalizedPoint | null): string | null {
  const direction = normalize({ x: end.x - start.x, y: end.y - start.y });
  if (!direction) return "Punkty pomiaru są zbyt blisko siebie.";
  const vertical = normalize(verticalDirection ?? { x: 0, y: -1 })!;
  const alignment = Math.abs(direction.x * vertical.x + direction.y * vertical.y);
  if (semantics.axis === "VERTICAL" && alignment < Math.cos(55 * Math.PI / 180)) return "Ten pomiar wygląda na poziomy. Czy na pewno ma być wysokością?";
  if (semantics.axis === "HORIZONTAL" && alignment > Math.cos(35 * Math.PI / 180)) return "Ten pomiar wygląda na pionowy. Sprawdź, czy wskazano oba końce tej samej krawędzi.";
  return null;
}

export function semanticColor(measurement: Pick<CalibrationReference, "measurementKind" | "useForCalibration" | "semanticStatus" | "residualStatus">) {
  if (measurement.semanticStatus !== "CONFIRMED" || measurement.residualStatus === "OUTLIER") return "#ef4444";
  if (measurement.useForCalibration && VERTICAL_KINDS.has(measurement.measurementKind)) return "#22d3ee";
  if (measurement.measurementKind === "FLOOR_DISTANCE") return "#14b8a6";
  return "#f59e0b";
}

export function geometrySemantics(measurement: GeometryMeasurement): MeasurementSemantics {
  return {
    measurementKind: measurement.measurementKind,
    axis: measurement.axis,
    plane: measurement.plane,
    purpose: measurement.purpose,
  };
}

function vertical(measurementKind: MeasurementKind, purpose: MeasurementPurpose = "CALIBRATION"): MeasurementSemantics {
  return { measurementKind, axis: "VERTICAL", plane: "VERTICAL_PLANE", purpose };
}

function invalid(code: CalibrationValidation["code"], warning: string | null): CalibrationValidation {
  return { valid: false, code, warning };
}

function normalize(point: NormalizedPoint): NormalizedPoint | null {
  const length = Math.hypot(point.x, point.y);
  return length > 1e-8 ? { x: point.x / length, y: point.y / length } : null;
}
