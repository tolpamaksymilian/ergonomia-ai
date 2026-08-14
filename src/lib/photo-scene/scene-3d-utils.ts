import type { SceneHuman, SceneObject, Vector3Cm } from "../../types/photo-scene";
import { getHumanJointPositions3d, setHumanRoot } from "./human-3d-model.ts";
import { distance3, v3 } from "./vector3.ts";

export function measureDistance3d(start: Vector3Cm, end: Vector3Cm): number { return distance3(start, end); }
export function snapVector3ToGrid(point: Vector3Cm, snapCm: 1 | 5 | 10): Vector3Cm {
  const snap = (value: number) => Math.round(value / snapCm) * snapCm;
  return v3(snap(point.x), Math.max(0, snap(point.y)), snap(point.z));
}
export function placeHumanAtSeat3d(human: SceneHuman, seat: SceneObject): { human: SceneHuman; status: "PLACED" | "UNKNOWN_GEOMETRY" } {
  const geometry = seat.geometry3d, height = geometry?.dimensionsCm.height;
  if (!geometry || !height) return { human, status: "UNKNOWN_GEOMETRY" };
  const joints = getHumanJointPositions3d(human.human3d), hipOffset = joints.pelvis.y - human.human3d.rootPositionCm.y;
  const seatTop = geometry.positionCm.y + height / 2;
  const root = v3(geometry.positionCm.x, Math.max(0, seatTop - hipOffset), geometry.positionCm.z);
  return { human: { ...human, human3d: setHumanRoot(human.human3d, root), placement: { ...human.placement, attachedObjectId: seat.id, positionMode: "SEATED_AT_OBJECT" } }, status: "PLACED" };
}
export function workSurfaceTarget3d(object: SceneObject, lateralOffsetCm = 0): Vector3Cm | null {
  const geometry = object.geometry3d, height = geometry?.dimensionsCm.height;
  return geometry && height ? v3(geometry.positionCm.x + lateralOffsetCm, geometry.positionCm.y + height / 2, geometry.positionCm.z) : null;
}
