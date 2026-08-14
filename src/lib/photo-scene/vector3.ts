import type { EulerDegrees, Vector3Cm } from "../../types/photo-scene";

export const v3 = (x = 0, y = 0, z = 0): Vector3Cm => ({ x, y, z });
export const add3 = (a: Vector3Cm, b: Vector3Cm): Vector3Cm => v3(a.x + b.x, a.y + b.y, a.z + b.z);
export const sub3 = (a: Vector3Cm, b: Vector3Cm): Vector3Cm => v3(a.x - b.x, a.y - b.y, a.z - b.z);
export const scale3 = (a: Vector3Cm, scale: number): Vector3Cm => v3(a.x * scale, a.y * scale, a.z * scale);
export const dot3 = (a: Vector3Cm, b: Vector3Cm) => a.x * b.x + a.y * b.y + a.z * b.z;
export const cross3 = (a: Vector3Cm, b: Vector3Cm): Vector3Cm => v3(a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z, a.x * b.y - a.y * b.x);
export const length3 = (a: Vector3Cm) => Math.hypot(a.x, a.y, a.z);
export const distance3 = (a: Vector3Cm, b: Vector3Cm) => length3(sub3(a, b));
export const normalize3 = (a: Vector3Cm, fallback = v3(0, 1, 0)): Vector3Cm => { const length = length3(a); return length > 1e-9 && Number.isFinite(length) ? scale3(a, 1 / length) : fallback; };
export const lerp3 = (a: Vector3Cm, b: Vector3Cm, t: number): Vector3Cm => add3(a, scale3(sub3(b, a), Math.max(0, Math.min(1, t))));
export const finite3 = (a: Vector3Cm) => [a.x, a.y, a.z].every(Number.isFinite);
export function rotateEuler(point: Vector3Cm, rotation: EulerDegrees): Vector3Cm {
  const x = rotation.x * Math.PI / 180, y = rotation.y * Math.PI / 180, z = rotation.z * Math.PI / 180;
  let p = v3(point.x, point.y * Math.cos(x) - point.z * Math.sin(x), point.y * Math.sin(x) + point.z * Math.cos(x));
  p = v3(p.x * Math.cos(y) + p.z * Math.sin(y), p.y, -p.x * Math.sin(y) + p.z * Math.cos(y));
  return v3(p.x * Math.cos(z) - p.y * Math.sin(z), p.x * Math.sin(z) + p.y * Math.cos(z), p.z);
}
