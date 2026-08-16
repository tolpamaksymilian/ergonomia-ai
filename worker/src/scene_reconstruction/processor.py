from __future__ import annotations

import math
import statistics
import time
from datetime import UTC, datetime
from typing import Any, Mapping, Sequence


RECONSTRUCTION_VERSION = "scene-reconstruction-v1.0-beta.1"
GEOMETRY_VERSION = "scene-geometry-v2.0-beta.1"
CONSTRAINT_GRAPH_VERSION = "scene-constraint-graph-v1.0"
SUPPORTED_SCENE_SCHEMA = "1.5"


class ReconstructionInputError(ValueError):
    """A stable, user-correctable reconstruction contract error."""


def build_reconstruction_input(
    scene_state: Mapping[str, Any],
    detection_result: Mapping[str, Any] | None,
    *,
    scene_revision: str,
    image_width: int,
    image_height: int,
) -> dict[str, Any]:
    if scene_state.get("schema_version") != SUPPORTED_SCENE_SCHEMA:
        raise ReconstructionInputError("unsupported_scene_schema")
    if not scene_revision.strip():
        raise ReconstructionInputError("missing_scene_revision")
    if image_width <= 0 or image_height <= 0:
        raise ReconstructionInputError("invalid_image_dimensions")
    regions = scene_state.get("regions")
    objects = scene_state.get("objects")
    graph = scene_state.get("constraintGraph")
    if not isinstance(regions, list) or not isinstance(objects, list) or not isinstance(graph, Mapping):
        raise ReconstructionInputError("invalid_scene_geometry_contract")
    constraints = graph.get("constraints")
    if graph.get("version") != CONSTRAINT_GRAPH_VERSION or not isinstance(constraints, list):
        raise ReconstructionInputError("invalid_constraint_graph")
    if not regions and not constraints and not _legacy_references(scene_state):
        raise ReconstructionInputError("insufficient_data")
    return {
        "schemaVersion": "1.0",
        "sceneRevision": scene_revision,
        "image": {"width": image_width, "height": image_height},
        "regions": regions,
        "objects": objects,
        "planes": scene_state.get("planes", []),
        "constraintGraph": {"version": CONSTRAINT_GRAPH_VERSION, "nodes": graph.get("nodes", []), "constraints": [*constraints, *_shape_constraints(objects, constraints), *_legacy_constraints(scene_state, constraints)]},
        "detectionEvidence": detection_result,
        "solver": {"robustLoss": "HUBER", "autoRepairDerivedGeometry": True, "assumptionsEnabled": False},
    }


def reconstruct_scene(document: Mapping[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    _validate_reconstruction_input(document)
    image = document["image"]
    regions, repairs = _repair_regions(document["regions"], image)
    objects = [item for item in document["objects"] if isinstance(item, Mapping) and item.get("status") != "USER_REJECTED"]
    constraints = [item for item in document["constraintGraph"]["constraints"] if _usable_constraint(item)]
    dimensions, residuals, outliers, conflicts = _fit_dimensions(constraints, objects)
    scale = _vertical_scale(constraints, outliers, image)
    planes = _build_planes(regions, dimensions)
    ground = next((item for item in regions if item.get("type") == "FLOOR_REGION" and item.get("quality") != "INVALID"), None)
    movement = next((item for item in regions if item.get("type") == "MOVEMENT_ZONE" and item.get("quality") != "INVALID"), None)
    object_quality: dict[str, str] = {}
    world_geometry: dict[str, Any] = {}
    for item in objects:
        object_id = str(item.get("id", ""))
        values = dimensions.get(object_id, {})
        has_region = any(region.get("associatedObjectId") == object_id and region.get("quality") != "INVALID" for region in regions)
        quality = "HIGH" if has_region and all(values.get(key) for key in ("heightCm", "widthCm", "depthCm")) else "PARTIAL" if has_region else "TWO_D_ONLY"
        object_quality[object_id] = quality
        world_geometry[object_id] = {"status": quality, "cornersCm": _cuboid(values)}
    ground_plane = next((plane for plane in planes if ground and plane.get("regionId") == ground.get("id")), None)
    for region in regions:
        if region.get("type") not in {"FLOOR_REGION", "MOVEMENT_ZONE", "STANDING_ZONE", "INTERACTION_ZONE", "NO_GO_ZONE"}:
            continue
        homography = ground_plane.get("homography") if isinstance(ground_plane, Mapping) else None
        projected = [
            _project_ground_point(point, homography)
            for point in region.get("polygonImageNormalized", [])
        ] if isinstance(homography, list) else []
        valid = [point for point in projected if point is not None]
        world_geometry[f"region:{region.get('id')}"] = {
            "status": "PROJECTIVE" if projected and len(valid) == len(projected) else "PARTIAL",
            "cornersCm": [],
            "polygonCm": valid,
            "sourcePlaneId": ground_plane.get("id") if isinstance(ground_plane, Mapping) else None,
        }
    readiness = _readiness(ground is not None, movement is not None, scale, dimensions, object_quality, bool(conflicts))
    next_measurements = _next_measurement(objects, regions, dimensions, readiness)
    has_derived_dimension = any(any(isinstance(value, (int, float)) and math.isfinite(value) for value in item.values()) for item in dimensions.values())
    status = "INCONSISTENT" if conflicts else "UNDERDETERMINED" if not constraints or (not has_derived_dimension and scale.get("pixelsPerCm") is None) else "SOLVED" if readiness["FULL_3D"]["status"] == "READY" else "PARTIAL"
    reconstruction_state = {
        "version": RECONSTRUCTION_VERSION,
        "geometryVersion": GEOMETRY_VERSION,
        "sceneRevision": document["sceneRevision"],
        "status": status,
        "cameraModel": _camera_model(planes, document.get("detectionEvidence")),
        "readiness": readiness,
        "objectQuality": object_quality,
        "constraintResiduals": residuals,
        "outlierConstraintIds": outliers,
        "autoRepairs": repairs,
        "conflicts": conflicts,
        "missingConstraints": [item["reason"] for item in next_measurements],
        "nextBestMeasurements": next_measurements,
        "derivedDimensions": dimensions,
        "worldGeometry": world_geometry,
        "verticalScaleModel": scale,
        "diagnostics": _diagnostics(status, scale, repairs, outliers),
        "runtimeMs": round((time.perf_counter() - started) * 1000, 3),
        "completedAt": datetime.now(UTC).isoformat(),
    }
    return {
        "schemaVersion": "1.0",
        "generatedBy": "Ergonomia AI Scene Reconstruction Engine",
        **reconstruction_state,
        "input": {"sceneRevision": document["sceneRevision"], "regionCount": len(regions), "objectCount": len(objects), "constraintCount": len(constraints)},
        "groundModel": {"regionId": ground.get("id") if ground else None, "status": "PROJECTIVE" if ground and any(plane.get("regionId") == ground.get("id") and plane.get("homography") for plane in planes) else "PARTIAL" if ground else "UNRESOLVED"},
        "planes": planes,
        "derivedDimensions": dimensions,
        "worldGeometry": world_geometry,
        "quality": {"conditioning": "UNSTABLE" if conflicts else "GOOD" if status == "SOLVED" else "LIMITED", "reprojectionErrorPx": _stats(list(residuals.values()))},
    }


def reconstruction_summary(result: Mapping[str, Any]) -> dict[str, Any]:
    state_keys = (
        "version", "geometryVersion", "sceneRevision", "status", "cameraModel", "readiness",
        "objectQuality", "constraintResiduals", "outlierConstraintIds", "autoRepairs", "conflicts",
        "missingConstraints", "nextBestMeasurements", "derivedDimensions", "worldGeometry", "verticalScaleModel", "diagnostics", "runtimeMs", "completedAt",
    )
    return {
        "reconstructionState": {key: result.get(key) for key in state_keys},
        "planes": result.get("planes", []),
        "objectCount": len(result.get("objects", {})) if isinstance(result.get("objects"), Mapping) else len(result.get("objectQuality", {})),
        "regionCount": result.get("input", {}).get("regionCount", 0),
    }


def _validate_reconstruction_input(document: Mapping[str, Any]) -> None:
    if document.get("schemaVersion") != "1.0" or not str(document.get("sceneRevision", "")).strip():
        raise ReconstructionInputError("unsupported_reconstruction_input")
    image = document.get("image")
    graph = document.get("constraintGraph")
    if not isinstance(image, Mapping) or not isinstance(graph, Mapping) or graph.get("version") != CONSTRAINT_GRAPH_VERSION:
        raise ReconstructionInputError("invalid_reconstruction_input")
    if not isinstance(document.get("regions"), list) or not isinstance(document.get("objects"), list) or not isinstance(graph.get("constraints"), list):
        raise ReconstructionInputError("invalid_reconstruction_collections")


def _legacy_references(scene: Mapping[str, Any]) -> list[Any]:
    calibration = scene.get("calibration")
    return calibration.get("references", []) if isinstance(calibration, Mapping) and isinstance(calibration.get("references"), list) else []


def _legacy_constraints(scene: Mapping[str, Any], existing: Sequence[Any] = ()) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    represented = {
        str(item.get("target", {}).get("id"))
        for item in existing
        if isinstance(item, Mapping) and isinstance(item.get("target"), Mapping) and item.get("target", {}).get("id")
    }
    for reference in _legacy_references(scene):
        if not isinstance(reference, Mapping) or reference.get("semanticStatus") != "CONFIRMED" or not reference.get("active", True):
            continue
        if str(reference.get("id")) in represented:
            continue
        axis = reference.get("axis")
        kind = "HEIGHT" if axis == "VERTICAL" else "DEPTH" if axis == "GROUND_Y" else "WIDTH" if axis in {"HORIZONTAL", "GROUND_X"} else "DISTANCE"
        result.append({
            "id": f"legacy-reference:{reference.get('id')}", "type": kind, "nodeIds": [], "objectId": reference.get("objectId"), "regionId": None,
            "target": {"kind": "EDGE", "id": reference.get("id"), "point": None}, "rawValue": reference.get("valueCm"), "effectiveValue": reference.get("valueCm"),
            "unit": "cm", "source": "USER_PROVIDED", "weight": 1, "useForSolver": kind != "HEIGHT" or reference.get("useForCalibration") is True,
            "status": "ACTIVE" if kind != "HEIGHT" or reference.get("useForCalibration") is True else "DISABLED", "residual": None,
            "imageSegment": {"start": reference.get("start"), "end": reference.get("end")},
        })
    return result


def _usable_constraint(value: Any) -> bool:
    if not isinstance(value, Mapping) or value.get("useForSolver") is not True or value.get("status") == "DISABLED":
        return False
    if value.get("type") not in {"HEIGHT", "WIDTH", "DEPTH", "DISTANCE"}:
        return True
    raw = value.get("rawValue")
    return isinstance(raw, (int, float)) and not isinstance(raw, bool) and math.isfinite(raw) and raw > 0


def _shape_constraints(objects: Sequence[Any], existing: Sequence[Any]) -> list[dict[str, Any]]:
    identifiers = {str(item.get("id")) for item in existing if isinstance(item, Mapping)}
    result: list[dict[str, Any]] = []
    for item in objects:
        if not isinstance(item, Mapping):
            continue
        object_id = str(item.get("id", ""))
        for assumption in item.get("shapeAssumptions", []):
            if assumption == "FREEFORM":
                continue
            identifier = f"assumption:{object_id}:{assumption}"
            if identifier in identifiers:
                continue
            kind = "RECTANGULAR" if assumption == "RECTANGULAR" else "COPLANAR" if assumption == "PLANAR" else "PARALLEL"
            result.append({"id": identifier, "type": kind, "nodeIds": [f"object:{object_id}"], "objectId": object_id, "regionId": None, "target": {"kind": "OBJECT", "id": object_id, "point": None}, "rawValue": None, "effectiveValue": None, "unit": "none", "source": "USER_CONFIRMED", "weight": 1, "useForSolver": True, "status": "ACTIVE", "residual": None, "imageSegment": None})
    return result


def _fit_dimensions(constraints: Sequence[Mapping[str, Any]], objects: Sequence[Mapping[str, Any]]) -> tuple[dict[str, dict[str, float]], dict[str, float], list[str], list[dict[str, Any]]]:
    groups: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for item in constraints:
        kind = str(item.get("type"))
        if kind in {"HEIGHT", "WIDTH", "DEPTH", "DISTANCE"}:
            entity_id = str(item.get("objectId") or (f"region:{item.get('regionId')}" if item.get("regionId") else "scene"))
            groups.setdefault((entity_id, kind), []).append(item)
    dimensions: dict[str, dict[str, float]] = {}
    residuals: dict[str, float] = {}
    outliers: list[str] = []
    conflicts: list[dict[str, Any]] = []
    by_id = {str(item.get("id")): item for item in objects}
    for (object_id, kind), items in sorted(groups.items()):
        entries = [(str(item.get("id")), float(item["rawValue"]), _provenance_weight(str(item.get("source"))) * max(float(item.get("weight", 1)), 1e-9)) for item in items]
        fit, rejected = _robust_location(entries)
        outliers.extend(rejected)
        residuals.update({entry_id: abs(value - fit) for entry_id, value, _weight in entries})
        authoritative = [value for item, (_entry_id, value, _weight) in zip(items, entries) if item.get("source") in {"USER_PROVIDED", "USER_CONFIRMED"}]
        assumptions = by_id.get(object_id, {}).get("shapeAssumptions", [])
        if "RECTANGULAR" in assumptions and len(authoritative) == 2 and _relative_range(authoritative) > .15:
            conflicts.append({"id": f"conflict:{object_id}:{kind}", "objectId": object_id, "constraintIds": [entry[0] for entry in entries], "code": "CONSTRAINT_CONFLICT", "message": f"Podane wartości {kind.lower()} nie są zgodne z założeniem prostokątnego obiektu."})
        key = {"HEIGHT": "heightCm", "WIDTH": "widthCm", "DEPTH": "depthCm"}.get(kind)
        if object_id != "scene" and key and math.isfinite(fit):
            dimensions.setdefault(object_id, {})[key] = fit
    return dimensions, residuals, sorted(set(outliers)), conflicts


def _robust_location(entries: Sequence[tuple[str, float, float]]) -> tuple[float, list[str]]:
    center = _weighted_median(entries)
    mad = statistics.median(abs(value - center) for _id, value, _weight in entries)
    threshold = max(1.0, mad * 3.5, abs(center) * .1)
    rejected = [entry_id for entry_id, value, _weight in entries if abs(value - center) > threshold]
    inliers = [entry for entry in entries if entry[0] not in rejected] or list(entries)
    estimate = _weighted_median(inliers)
    for _iteration in range(8):
        scale = max(1.0, statistics.median(abs(value - estimate) for _id, value, _weight in inliers) * 1.4826)
        numerator = denominator = 0.0
        for _entry_id, value, weight in inliers:
            residual = value - estimate
            huber = 1.0 if abs(residual) <= 1.345 * scale else 1.345 * scale / abs(residual)
            numerator += value * weight * huber
            denominator += weight * huber
        if denominator <= 1e-12:
            break
        updated = numerator / denominator
        if not math.isfinite(updated) or abs(updated - estimate) < 1e-9:
            break
        estimate = updated
    return estimate, rejected


def _weighted_median(entries: Sequence[tuple[str, float, float]]) -> float:
    ordered = sorted(entries, key=lambda item: item[1])
    total = sum(item[2] for item in ordered)
    cumulative = 0.0
    for _entry_id, value, weight in ordered:
        cumulative += weight
        if cumulative >= total / 2:
            return value
    return ordered[-1][1]


def _vertical_scale(constraints: Sequence[Mapping[str, Any]], outliers: Sequence[str], image: Mapping[str, Any]) -> dict[str, Any]:
    entries: list[tuple[str, float, float, float]] = []
    for item in constraints:
        segment = item.get("imageSegment")
        if item.get("type") != "HEIGHT" or str(item.get("id")) in outliers or not isinstance(segment, Mapping):
            continue
        distance = _pixel_distance(segment.get("start"), segment.get("end"), image)
        value = float(item["rawValue"])
        if distance > 1e-9:
            start, end = _effective_point(segment.get("start")), _effective_point(segment.get("end"))
            if start is not None and end is not None:
                entries.append((str(item.get("id")), distance / value, _provenance_weight(str(item.get("source"))), (start["y"] + end["y"]) / 2))
    if not entries:
        return {"kind": "UNRESOLVED", "pixelsPerCm": None, "coefficients": None, "sourceConstraintIds": [], "quality": "UNKNOWN"}
    perspective = _fit_inverse_affine_vertical(entries)
    if perspective is not None:
        return perspective
    compact = [(identifier, scale, weight) for identifier, scale, weight, _y in entries]
    scale, rejected = _robust_location(compact)
    source_ids = [entry[0] for entry in entries if entry[0] not in rejected]
    return {"kind": "ROBUST_CONSTANT", "pixelsPerCm": scale, "coefficients": None, "sourceConstraintIds": source_ids, "quality": "HIGH" if len(source_ids) >= 3 else "MEDIUM"}


def _fit_inverse_affine_vertical(entries: Sequence[tuple[str, float, float, float]]) -> dict[str, Any] | None:
    if len(entries) < 3 or max(item[3] for item in entries) - min(item[3] for item in entries) < .15:
        return None
    weights = [item[2] for item in entries]
    coefficients: tuple[float, float] | None = None
    for _iteration in range(6):
        s = sy = syy = st = syt = 0.0
        for (_identifier, scale, _base_weight, y), weight in zip(entries, weights):
            target = 1.0 / scale
            s += weight
            sy += weight * y
            syy += weight * y * y
            st += weight * target
            syt += weight * y * target
        determinant = s * syy - sy * sy
        if not math.isfinite(determinant) or abs(determinant) <= 1e-12:
            return None
        coefficients = ((st * syy - sy * syt) / determinant, (s * syt - sy * st) / determinant)
        if not all(math.isfinite(value) for value in coefficients) or min(coefficients[0], coefficients[0] + coefficients[1]) <= 1e-12:
            return None
        residuals = [abs(1.0 / item[1] - (coefficients[0] + coefficients[1] * item[3])) for item in entries]
        robust_scale = max(1e-12, statistics.median(residuals) * 1.4826)
        weights = [item[2] * (1.0 if residual <= 1.345 * robust_scale else 1.345 * robust_scale / residual) for item, residual in zip(entries, residuals)]
    if coefficients is None:
        return None
    residuals = [abs(1.0 / item[1] - (coefficients[0] + coefficients[1] * item[3])) for item in entries]
    typical = statistics.median(1.0 / item[1] for item in entries)
    threshold = max(1e-12, statistics.median(residuals) * 3.5, typical * .1)
    inliers = [item for item, residual in zip(entries, residuals) if residual <= threshold]
    if len(inliers) < 3:
        return None
    reference_y = statistics.median(item[3] for item in inliers)
    denominator = coefficients[0] + coefficients[1] * reference_y
    return {"kind": "INVERSE_AFFINE_VERTICAL", "pixelsPerCm": 1.0 / denominator, "coefficients": list(coefficients), "sourceConstraintIds": [item[0] for item in inliers], "quality": "HIGH"} if denominator > 1e-12 else None


def _repair_regions(regions: Sequence[Any], image: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    result: list[dict[str, Any]] = []
    repairs: list[dict[str, Any]] = []
    for raw_region in regions:
        if not isinstance(raw_region, Mapping):
            continue
        region = dict(raw_region)
        polygon = raw_region.get("polygonImageNormalized")
        if not isinstance(polygon, list) or len(polygon) < 3:
            region["quality"] = "INVALID"
            result.append(region)
            continue
        effective = [_effective_point(item) for item in polygon]
        if any(point is None for point in effective):
            region["quality"] = "INVALID"
            result.append(region)
            continue
        points = [point for point in effective if point is not None]
        if _self_intersects(points):
            center = {"x": sum(point["x"] for point in points) / len(points), "y": sum(point["y"] for point in points) / len(points)}
            ordered = sorted(zip(polygon, points), key=lambda item: math.atan2(item[1]["y"] - center["y"], item[1]["x"] - center["x"]))
            before = [_raw_point(item) for item in polygon]
            region["polygonImageNormalized"] = [item[0] for item in ordered]
            region["source"] = "AUTO_REPAIRED"
            region["quality"] = "MEDIUM"
            repairs.append({"id": f"repair:{region.get('id')}:polygon-order", "type": "POLYGON_ORDER", "entityId": region.get("id"), "before": before, "after": [item[1] for item in ordered], "delta": _order_delta(points, [item[1] for item in ordered], image), "unit": "px", "reason": "Uporządkowano samoprzecinający się wielokąt; surowe punkty zachowano."})
        elif abs(_polygon_area(points)) <= 1e-12:
            region["quality"] = "INVALID"
        result.append(region)
    return result, repairs


def _build_planes(regions: Sequence[Mapping[str, Any]], dimensions: Mapping[str, Mapping[str, float]]) -> list[dict[str, Any]]:
    planes: list[dict[str, Any]] = []
    for region in regions:
        if region.get("type") not in {"FLOOR_REGION", "WORK_SURFACE", "OBJECT_TOP_FACE", "CONTROL_PANEL_REGION", "SHELF_REGION"} or region.get("quality") == "INVALID":
            continue
        object_id = region.get("associatedObjectId")
        values = dimensions.get(str(object_id), {}) if object_id else dimensions.get(f"region:{region.get('id')}", {})
        polygon = region.get("polygonImageNormalized", [])
        effective = [_effective_point(point) for point in polygon]
        homography = _solve_homography(
            [point for point in effective if point is not None],
            float(values["widthCm"]),
            float(values["depthCm"]),
        ) if len(effective) == 4 and all(point is not None for point in effective) and values.get("widthCm") and values.get("depthCm") else None
        projective = homography is not None
        planes.append({"id": region.get("planeId") or f"plane:{region.get('id')}", "kind": "GROUND" if region.get("type") == "FLOOR_REGION" else "CONTROL_PANEL" if region.get("type") == "CONTROL_PANEL_REGION" else "SHELF" if region.get("type") == "SHELF_REGION" else "OBJECT_TOP", "regionId": region.get("id"), "objectId": object_id, "normal": {"x": 0, "y": 1, "z": 0}, "offsetCm": 0 if region.get("type") == "FLOOR_REGION" else values.get("heightCm"), "homography": homography, "source": "SOLVER_DERIVED" if projective else "SOLVER_ESTIMATED", "quality": "HIGH" if projective else "MEDIUM", "locked": bool(region.get("locked"))})
    return planes


def _solve_homography(source: Sequence[Mapping[str, float]], width_cm: float, depth_cm: float) -> list[float] | None:
    if len(source) != 4 or width_cm <= 0 or depth_cm <= 0:
        return None
    target = ((0.0, 0.0), (width_cm, 0.0), (width_cm, depth_cm), (0.0, depth_cm))
    matrix: list[list[float]] = []
    for point, (world_x, world_z) in zip(source, target):
        x, y = point["x"], point["y"]
        matrix.append([x, y, 1.0, 0.0, 0.0, 0.0, -world_x * x, -world_x * y, world_x])
        matrix.append([0.0, 0.0, 0.0, x, y, 1.0, -world_z * x, -world_z * y, world_z])
    solution = _gaussian_solve(matrix)
    return [*solution, 1.0] if solution is not None else None


def _project_ground_point(value: Any, homography: Sequence[float]) -> dict[str, float] | None:
    point = _effective_point(value)
    if point is None or len(homography) != 9 or not all(isinstance(item, (int, float)) and math.isfinite(item) for item in homography):
        return None
    denominator = homography[6] * point["x"] + homography[7] * point["y"] + homography[8]
    if not math.isfinite(denominator) or abs(denominator) <= 1e-12:
        return None
    x = (homography[0] * point["x"] + homography[1] * point["y"] + homography[2]) / denominator
    z = (homography[3] * point["x"] + homography[4] * point["y"] + homography[5]) / denominator
    return {"x": x, "y": 0.0, "z": z} if math.isfinite(x) and math.isfinite(z) else None


def _gaussian_solve(augmented: Sequence[Sequence[float]]) -> list[float] | None:
    rows = [list(row) for row in augmented]
    size = len(rows)
    if size == 0 or any(len(row) != size + 1 for row in rows):
        return None
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(rows[row][column]))
        if abs(rows[pivot][column]) < 1e-12:
            return None
        rows[column], rows[pivot] = rows[pivot], rows[column]
        divisor = rows[column][column]
        for item in range(column, size + 1):
            rows[column][item] /= divisor
        for row in range(size):
            if row == column:
                continue
            factor = rows[row][column]
            for item in range(column, size + 1):
                rows[row][item] -= factor * rows[column][item]
    solution = [row[size] for row in rows]
    return solution if all(math.isfinite(value) for value in solution) else None


def _readiness(has_ground: bool, has_movement: bool, scale: Mapping[str, Any], dimensions: Mapping[str, Mapping[str, float]], quality: Mapping[str, str], conflict: bool) -> dict[str, Any]:
    if conflict:
        invalid = {"status": "INVALID", "reasons": ["Rzeczywiste wymiary są sprzeczne z aktywnymi założeniami."]}
        return {goal: dict(invalid) for goal in ("HUMAN_PLACEMENT", "WORK_HEIGHT", "REACH", "COLLISION", "FULL_3D")}
    values = list(dimensions.values())
    has_scale = isinstance(scale.get("pixelsPerCm"), (int, float))
    has_height = any(item.get("heightCm") for item in values)
    has_depth = bool(values) and all(item.get("depthCm") for item in values)
    return {
        "HUMAN_PLACEMENT": {"status": "READY" if has_ground and has_scale else "PARTIAL" if has_ground or has_scale else "INSUFFICIENT", "reasons": [] if has_ground and has_scale else ["Zaznacz podłogę i dodaj rzeczywistą wysokość pionową."]},
        "WORK_HEIGHT": {"status": "READY" if has_height else "NEEDS_HEIGHT", "reasons": [] if has_height else ["Podaj wysokość powierzchni roboczej."]},
        "REACH": {"status": "READY" if has_ground and has_scale else "INSUFFICIENT", "reasons": [] if has_ground and has_scale and has_movement else ["Pole ruchu jest opcjonalne; geometria operatora wymaga podłogi i skali."]},
        "COLLISION": {"status": "READY" if has_depth else "NEEDS_DEPTH", "reasons": [] if has_depth else ["Brakuje głębokości obiektu; kolizja pozostaje nieznana."]},
        "FULL_3D": {"status": "READY" if has_ground and any(item == "HIGH" for item in quality.values()) else "PARTIAL", "reasons": [] if has_ground and any(item == "HIGH" for item in quality.values()) else ["Część obiektów ma niepełną geometrię."]},
    }


def _next_measurement(objects: Sequence[Mapping[str, Any]], regions: Sequence[Mapping[str, Any]], dimensions: Mapping[str, Mapping[str, float]], readiness: Mapping[str, Any]) -> list[dict[str, Any]]:
    if readiness["HUMAN_PLACEMENT"]["status"] != "READY":
        return [{"measurementKind": "VERTICAL_HEIGHT", "objectId": None, "suggestedPoints": None, "reason": "Dodaj jedną rzeczywistą pionową wysokość przy obszarze podłogi.", "expectedBenefit": "Pozwoli stabilnie osadzać operatora w scenie."}]
    for item in objects:
        object_id = str(item.get("id"))
        values = dimensions.get(object_id, {})
        region = next((region for region in regions if region.get("associatedObjectId") == object_id and region.get("type") in {"WORK_SURFACE", "OBJECT_TOP_FACE"}), None)
        points = region.get("polygonImageNormalized", []) if region else []
        if not values.get("heightCm"):
            return [_measurement("WORK_SURFACE_HEIGHT", object_id, points, 0, f"Podaj rzeczywistą wysokość: {item.get('name', 'obiekt')}.", "Wyznaczy wysokość roboczą.")]
        if not values.get("widthCm"):
            return [_measurement("OBJECT_WIDTH", object_id, points, 0, f"Podaj rzeczywistą szerokość: {item.get('name', 'obiekt')}.", "Pozwoli wyznaczyć skalę płaszczyzny.")]
        if not values.get("depthCm"):
            return [_measurement("OBJECT_DEPTH", object_id, points, 1, f"Podaj rzeczywistą głębokość: {item.get('name', 'obiekt')}.", "Pozwoli wyznaczyć płaszczyznę i poprawi model kolizji.")]
    return []


def _measurement(kind: str, object_id: str, points: Sequence[Any], edge: int, reason: str, benefit: str) -> dict[str, Any]:
    effective = [_effective_point(item) for item in points]
    usable = [item for item in effective if item is not None]
    suggested = {"start": usable[edge % len(usable)], "end": usable[(edge + 1) % len(usable)]} if len(usable) >= 2 else None
    return {"measurementKind": kind, "objectId": object_id, "suggestedPoints": suggested, "reason": reason, "expectedBenefit": benefit}


def _camera_model(planes: Sequence[Mapping[str, Any]], detection: Any) -> dict[str, Any]:
    projective = any(item.get("homography") for item in planes)
    perspective = detection.get("perspective_evidence", {}) if isinstance(detection, Mapping) else {}
    return {"version": "camera-model-v2.0", "status": "PROJECTIVE" if projective else "PARTIAL" if planes else "UNRESOLVED", "vanishingDirections": {"x": perspective.get("vanishing_point") if isinstance(perspective, Mapping) else None, "y": None, "vertical": None}, "evidenceQuality": "MEDIUM" if projective else "LOW", "intrinsicsEstimated": False, "diagnostics": ["Planar homography available."] if projective else ["Camera intrinsics unresolved; solvePnP was not used."]}


def _diagnostics(status: str, scale: Mapping[str, Any], repairs: Sequence[Any], outliers: Sequence[Any]) -> list[dict[str, str]]:
    values = [{"code": f"RECONSTRUCTION_{status}", "message": f"Stan rekonstrukcji: {status}."}]
    if scale.get("pixelsPerCm") is None:
        values.append({"code": "VERTICAL_SCALE_UNRESOLVED", "message": "Pionowa projekcja nie została wyznaczona."})
    if repairs:
        values.append({"code": "AUTO_REPAIRS_RECORDED", "message": f"Zapisano korekty: {len(repairs)}."})
    if outliers:
        values.append({"code": "OUTLIERS_ISOLATED", "message": f"Odizolowano odstające ograniczenia: {len(outliers)}."})
    return values


def _cuboid(values: Mapping[str, float]) -> list[dict[str, float]]:
    if not all(values.get(key) for key in ("widthCm", "heightCm", "depthCm")):
        return []
    return [{"x": x, "y": y, "z": z} for x in (0.0, values["widthCm"]) for y in (0.0, values["heightCm"]) for z in (0.0, values["depthCm"])]


def _stats(values: Sequence[float]) -> dict[str, float | None]:
    finite = [value for value in values if math.isfinite(value)]
    return {"mean": sum(finite) / len(finite) if finite else None, "median": statistics.median(finite) if finite else None, "maximum": max(finite) if finite else None}


def _effective_point(value: Any) -> dict[str, float] | None:
    if not isinstance(value, Mapping):
        return None
    candidate = value.get("effective", value)
    if not isinstance(candidate, Mapping):
        return None
    x, y = candidate.get("x"), candidate.get("y")
    return {"x": float(x), "y": float(y)} if isinstance(x, (int, float)) and isinstance(y, (int, float)) and math.isfinite(x) and math.isfinite(y) else None


def _raw_point(value: Any) -> Any:
    return value.get("raw") if isinstance(value, Mapping) else None


def _pixel_distance(start: Any, end: Any, image: Mapping[str, Any]) -> float:
    first, second = _effective_point(start), _effective_point(end)
    if first is None or second is None:
        return 0.0
    return math.hypot((first["x"] - second["x"]) * float(image["width"]), (first["y"] - second["y"]) * float(image["height"]))


def _polygon_area(points: Sequence[Mapping[str, float]]) -> float:
    return sum(point["x"] * points[(index + 1) % len(points)]["y"] - points[(index + 1) % len(points)]["x"] * point["y"] for index, point in enumerate(points)) / 2


def _orientation(a: Mapping[str, float], b: Mapping[str, float], c: Mapping[str, float]) -> int:
    value = (b["y"] - a["y"]) * (c["x"] - b["x"]) - (b["x"] - a["x"]) * (c["y"] - b["y"])
    return (value > 0) - (value < 0)


def _self_intersects(points: Sequence[Mapping[str, float]]) -> bool:
    for first in range(len(points)):
        for second in range(first + 1, len(points)):
            if abs(first - second) <= 1 or (first == 0 and second == len(points) - 1):
                continue
            a, b, c, d = points[first], points[(first + 1) % len(points)], points[second], points[(second + 1) % len(points)]
            if _orientation(a, b, c) != _orientation(a, b, d) and _orientation(c, d, a) != _orientation(c, d, b):
                return True
    return False


def _order_delta(before: Sequence[Mapping[str, float]], after: Sequence[Mapping[str, float]], image: Mapping[str, Any]) -> float:
    return sum(math.hypot((first["x"] - second["x"]) * float(image["width"]), (first["y"] - second["y"]) * float(image["height"])) for first, second in zip(before, after))


def _relative_range(values: Sequence[float]) -> float:
    maximum = max(values)
    return 0.0 if maximum <= 1e-12 else (maximum - min(values)) / maximum


def _provenance_weight(source: str) -> float:
    return {"USER_PROVIDED": 10, "USER_CONFIRMED": 8, "WORKER_DETECTED": 3, "WORKER_SUGGESTED": 2, "SOLVER_DERIVED": 5, "SOLVER_ESTIMATED": 1.5, "AUTO_REPAIRED": 1, "ASSUMED": .25, "UNKNOWN": .1}.get(source, .1)
