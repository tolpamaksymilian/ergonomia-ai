import type { ObjectGeometry3D, Primitive3DType, SceneObject } from "../../types/photo-scene";
import { v3 } from "./vector3.ts";

export function createPrimitive3d(type: Primitive3DType, positionCm = v3(), dimensions: Partial<ObjectGeometry3D["dimensionsCm"]> = {}): ObjectGeometry3D {
  const defaults = primitiveDimensions(type), merged = { ...defaults, ...dimensions };
  const complete = type === "SPHERE" ? positive(merged.diameter) : type === "CYLINDER" || type === "HANDLE" || type === "BOTTLE" ? positive(merged.diameter) && positive(merged.length) : positive(merged.width) && positive(merged.height) && positive(merged.depth);
  return { type, positionCm, rotationDeg: v3(), dimensionsCm: merged, source: "USER_PROVIDED", geometryQuality: complete ? "COMPLETE" : "PARTIAL", collisionEnabled: complete && type !== "PLANE_PROXY", collisionGroup: "STATIC_SCENE", massKg: null, massSource: null };
}
export function geometry3dFromSceneObject(object: SceneObject): ObjectGeometry3D | null {
  const width = object.measurements.widthCm, height = object.measurements.heightCm ?? object.measurements.workSurfaceHeightCm, depth = object.measurements.depthCm;
  if (!positive(width) || !positive(height)) return null;
  return { type: depth ? "BOX" : "PLANE_PROXY", positionCm: v3(0, height / 2, 0), rotationDeg: v3(), dimensionsCm: { width, height, depth, diameter: null, length: null }, source: "DERIVED_FROM_CONFIRMED_DIMENSIONS", geometryQuality: depth ? "COMPLETE" : "PARTIAL", collisionEnabled: Boolean(depth), collisionGroup: depth ? "STATIC_SCENE" : "NON_COLLIDING_REFERENCE", massKg: null, massSource: null };
}
export function setObjectMass(geometry: ObjectGeometry3D, massKg: number | null): ObjectGeometry3D { return { ...geometry, massKg: positive(massKg) ? massKg : null, massSource: positive(massKg) ? "USER_PROVIDED" : null }; }
function primitiveDimensions(type: Primitive3DType): ObjectGeometry3D["dimensionsCm"] { if (type === "SPHERE") return { width:null,height:null,depth:null,diameter:10,length:null }; if (["CYLINDER","HANDLE","BOTTLE"].includes(type)) return { width:null,height:null,depth:null,diameter:5,length:20 }; return { width:30,height:20,depth:20,diameter:null,length:null }; }
function positive(value: unknown): value is number { return typeof value === "number" && Number.isFinite(value) && value > 0; }
