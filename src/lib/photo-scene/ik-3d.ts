import type { Vector3Cm } from "../../types/photo-scene";
import { add3, cross3, distance3, finite3, normalize3, scale3, sub3, v3 } from "./vector3.ts";

export type TwoBoneIk3DResult = { root: Vector3Cm; joint: Vector3Cm; end: Vector3Cm; reachable: boolean; atLimit: boolean; reachMarginCm: number };

export function solveTwoBoneIk3d(root: Vector3Cm, target: Vector3Cm, pole: Vector3Cm, upperLengthCm: number, lowerLengthCm: number): TwoBoneIk3DResult {
  if (![upperLengthCm, lowerLengthCm].every((v) => Number.isFinite(v) && v > 0) || ![root,target,pole].every(finite3)) throw new Error("Invalid 3D IK input.");
  const toTarget = sub3(target, root), distance = distance3(root, target), maximum = upperLengthCm + lowerLengthCm, minimum = Math.abs(upperLengthCm - lowerLengthCm);
  const clamped = Math.max(minimum + 1e-6, Math.min(maximum - 1e-6, distance)), direction = normalize3(toTarget, v3(1,0,0));
  const poleDirection = sub3(pole, root), normal = normalize3(cross3(direction, poleDirection), v3(0,0,1)), bend = normalize3(cross3(normal, direction), v3(0,1,0));
  const along = (upperLengthCm ** 2 - lowerLengthCm ** 2 + clamped ** 2) / (2 * clamped);
  const height = Math.sqrt(Math.max(0, upperLengthCm ** 2 - along ** 2));
  const joint = add3(root, add3(scale3(direction, along), scale3(bend, height)));
  const end = add3(root, scale3(direction, clamped));
  return { root, joint, end, reachable: distance <= maximum + 1e-6 && distance >= minimum - 1e-6, atLimit: distance >= maximum * .96, reachMarginCm: maximum - distance };
}

export function solveArmIk3d(input: { shoulder: Vector3Cm; target: Vector3Cm; elbowPole: Vector3Cm; upperArmCm: number; forearmCm: number }) { return solveTwoBoneIk3d(input.shoulder, input.target, input.elbowPole, input.upperArmCm, input.forearmCm); }
export function solveLegIk3d(input: { hip: Vector3Cm; target: Vector3Cm; kneePole: Vector3Cm; thighCm: number; lowerLegCm: number }) { return solveTwoBoneIk3d(input.hip, input.target, input.kneePole, input.thighCm, input.lowerLegCm); }
