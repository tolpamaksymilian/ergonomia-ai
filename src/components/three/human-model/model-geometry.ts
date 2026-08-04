import * as THREE from "three";

import type { Point3D } from "@/config/analysis-visualization";

export function segmentTransform(start: Point3D, end: Point3D) {
  const startVector = new THREE.Vector3(...start);
  const endVector = new THREE.Vector3(...end);
  const direction = new THREE.Vector3().subVectors(endVector, startVector);
  const midpoint = new THREE.Vector3().addVectors(startVector, endVector).multiplyScalar(0.5);
  const quaternion = new THREE.Quaternion().setFromUnitVectors(
    new THREE.Vector3(0, 1, 0),
    direction.clone().normalize(),
  );

  return { midpoint, quaternion, length: direction.length() };
}

export function createTaperedProfile(
  length: number,
  startRadius: number,
  endRadius: number,
  muscleBias = 0.08,
) {
  const half = length / 2;
  const cap = Math.min(length * 0.12, Math.max(startRadius, endRadius) * 0.72);
  const middleRadius = Math.max(startRadius, endRadius) * (1 + muscleBias);

  return [
    new THREE.Vector2(0, -half),
    new THREE.Vector2(startRadius * 0.84, -half),
    new THREE.Vector2(startRadius, -half + cap),
    new THREE.Vector2(middleRadius, -length * 0.08),
    new THREE.Vector2(endRadius * 1.04, half - cap),
    new THREE.Vector2(endRadius * 0.82, half),
    new THREE.Vector2(0, half),
  ];
}

export function createShellProfile(
  points: ReadonlyArray<readonly [radius: number, y: number]>,
) {
  return points.map(([radius, y]) => new THREE.Vector2(radius, y));
}

export function interpolatePoint(start: Point3D, end: Point3D, progress: number): Point3D {
  return [
    THREE.MathUtils.lerp(start[0], end[0], progress),
    THREE.MathUtils.lerp(start[1], end[1], progress),
    THREE.MathUtils.lerp(start[2], end[2], progress),
  ];
}
