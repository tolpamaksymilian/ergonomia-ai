import type { FingerName, HandPosePreset, HandRigState, HumanProfile, Vector3Cm } from "../../types/photo-scene";
import { add3, rotateEuler, v3 } from "./vector3.ts";

const FINGERS: FingerName[] = ["thumb", "index", "middle", "ring", "little"];
const PRESET_CURLS: Record<HandPosePreset, Record<FingerName, number>> = {
  OPEN: curls(0, 0, 0, 0, 0), RELAXED: curls(.18, .18, .24, .3, .36),
  POWER_GRIP: curls(.78, .92, .96, .96, .9), CYLINDER_GRIP: curls(.62, .78, .82, .82, .76),
  SPHERE_GRIP: curls(.45, .58, .62, .64, .6), PINCH: curls(.62, .56, .12, .18, .22),
  LATERAL_PINCH: curls(.7, .28, .55, .62, .68), CLOSED_FIST: curls(1, 1, 1, 1, 1),
};

export function createHandRig(preset: HandPosePreset = "RELAXED"): HandRigState {
  return { preset, fingers: Object.fromEntries(FINGERS.map((finger) => [finger, { curl: PRESET_CURLS[preset][finger], opposition: finger === "thumb" ? thumbOpposition(preset) : 0 }])) as HandRigState["fingers"], palmRotationDeg: { x: 0, y: 0, z: 0 } };
}
export function applyHandPreset(hand: HandRigState, preset: HandPosePreset): HandRigState { const next = createHandRig(preset); return { ...next, palmRotationDeg: hand.palmRotationDeg }; }
export function setFingerCurl(hand: HandRigState, finger: FingerName, curl: number, opposition = hand.fingers[finger].opposition): HandRigState { return { ...hand, preset: hand.preset, fingers: { ...hand.fingers, [finger]: { curl: clamp01(curl), opposition: clamp01(opposition) } } }; }

export type FingerJointPositions = Record<string, Vector3Cm>;
export function getFingerJointPositions(profile: HumanProfile, hand: HandRigState, side: "left" | "right", wrist: Vector3Cm): FingerJointPositions {
  const d = profile.physicalDimensions, sign = side === "left" ? -1 : 1, palmLength = d.handLengthCm * .42;
  const output: FingerJointPositions = { palmCenter: add3(wrist, v3(sign * palmLength * .45, 0, 0)) };
  FINGERS.forEach((finger, index) => {
    const isThumb = finger === "thumb", length = d.handLengthCm * (isThumb ? .42 : [.62, .72, .76, .7, .58][index]);
    const segments = isThumb ? 3 : 3, base = add3(output.palmCenter, v3(sign * (isThumb ? .05 : .36) * palmLength, (2 - index) * d.handWidthCm * .13, isThumb ? d.handWidthCm * .36 : (index - 2) * d.handWidthCm * .16));
    output[`${finger}MCP`] = base; let point = base;
    for (let segment = 1; segment <= segments; segment += 1) {
      const curl = hand.fingers[finger].curl * (isThumb ? 68 : 86), opposition = hand.fingers[finger].opposition * (isThumb ? 48 : 0);
      const direction = rotateEuler(v3(sign * length / segments, 0, 0), { x: 0, y: opposition * sign, z: -curl * sign });
      point = add3(point, direction); output[`${finger}${segment === segments ? "TIP" : segment === 1 ? "PIP" : "DIP"}`] = point;
    }
  });
  return output;
}
export function gripGeometryForDiameter(profile: HumanProfile, diameterCm: number, preset: HandPosePreset) {
  if (!Number.isFinite(diameterCm) || diameterCm <= 0) return { status: "GRIP_GEOMETRY_INVALID" as const, reason: "invalid_object_diameter" };
  const maximum = profile.physicalDimensions.maxGripDiameterCm * (preset === "SPHERE_GRIP" ? 1.25 : 1);
  return diameterCm <= maximum ? { status: "GRIP_GEOMETRY_VALID" as const, reason: null } : diameterCm <= maximum * 1.25 ? { status: "GRIP_GEOMETRY_PARTIAL" as const, reason: "near_hand_span_limit" } : { status: "GRIP_GEOMETRY_INVALID" as const, reason: "object_exceeds_hand_span" };
}
function curls(thumb: number, index: number, middle: number, ring: number, little: number) { return { thumb, index, middle, ring, little }; }
function thumbOpposition(preset: HandPosePreset) { return preset === "PINCH" ? .9 : preset === "LATERAL_PINCH" ? .65 : preset.includes("GRIP") || preset === "CLOSED_FIST" ? .72 : .2; }
function clamp01(value: number) { return Math.max(0, Math.min(1, Number.isFinite(value) ? value : 0)); }
