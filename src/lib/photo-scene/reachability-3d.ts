import type { Human3DState, ReachabilityResult3D, SceneHuman, Vector3Cm } from "../../types/photo-scene";
import { getHumanJointPositions3d } from "./human-3d-model.ts";
import { solveArmIk3d } from "./ik-3d.ts";
import { distance3 } from "./vector3.ts";

export function getReachabilityResult(human: Pick<SceneHuman,"profile"|"human3d">, hand: "LEFT"|"RIGHT", target: Vector3Cm, mode: "ARM_ONLY"|"WHOLE_BODY" = "ARM_ONLY", targetId: string | null = null): ReachabilityResult3D {
  const side = hand === "LEFT" ? "left" : "right", joints = getHumanJointPositions3d(human.human3d), d = human.profile.physicalDimensions;
  const shoulder = joints[`${side}Shoulder`], pole = human.human3d.poleTargetsCm[`${side}Elbow`], ik = solveArmIk3d({ shoulder, target, elbowPole: pole, upperArmCm: d.upperArmLengthCm, forearmCm: d.forearmLengthCm + d.handLengthCm * .45 });
  if (ik.reachable) return { level: ik.atLimit ? "AT_LIMIT" : "REACHABLE", mode, hand, targetId, reachMarginCm: ik.reachMarginCm, reasons: [ik.atLimit ? "arm_near_joint_limit" : "arm_ik_solution"] };
  const bodyAllowance = mode === "WHOLE_BODY" ? human.profile.heightCm * .16 : 0, margin = ik.reachMarginCm + bodyAllowance;
  return { level: mode === "WHOLE_BODY" && margin >= 0 ? "REACHABLE_WITH_BODY_MOVEMENT" : "UNREACHABLE", mode, hand, targetId, reachMarginCm: margin, reasons: mode === "WHOLE_BODY" && margin >= 0 ? ["requires_limited_torso_or_pelvis_motion", "feet_fixed"] : ["target_outside_geometric_reach"] };
}
export function applyArmTarget(human3d: Human3DState, profile: SceneHuman["profile"], hand: "LEFT"|"RIGHT", target: Vector3Cm): Human3DState {
  const side = hand === "LEFT" ? "left" : "right", joints = getHumanJointPositions3d(human3d), d = profile.physicalDimensions;
  const result = solveArmIk3d({ shoulder: joints[`${side}Shoulder`], target, elbowPole: human3d.poleTargetsCm[`${side}Elbow`], upperArmCm: d.upperArmLengthCm, forearmCm: d.forearmLengthCm });
  if (!result.reachable) return human3d;
  const local = structuredClone(human3d.jointPositionsCm); local[`${side}Elbow`] = result.joint; local[`${side}Wrist`] = result.end; local[`${side}Hand`] = target;
  return { ...human3d, jointPositionsCm: local };
}
export function getFingertipReachability(human: Pick<SceneHuman,"profile"|"human3d">, hand: "LEFT"|"RIGHT", target: Vector3Cm, targetId: string | null = null): ReachabilityResult3D {
  const result = getReachabilityResult(human, hand, target, "ARM_ONLY", targetId);
  const side = hand === "LEFT" ? "left" : "right", shoulder = getHumanJointPositions3d(human.human3d)[`${side}Shoulder`];
  const maximum = human.profile.physicalDimensions.upperArmLengthCm + human.profile.physicalDimensions.forearmLengthCm + human.profile.physicalDimensions.handLengthCm;
  const margin = maximum - distance3(shoulder, target);
  return { ...result, level: margin < 0 ? "UNREACHABLE" : margin < 1 ? "AT_LIMIT" : "REACHABLE", reachMarginCm: margin, reasons: [margin < 0 ? "fingertip_target_outside_reach" : "index_fingertip_target"] };
}
