import type { CollisionResult3D, HandPosePreset, HumanProfile, ObjectGeometry3D, SceneObjectType, Vector3Cm } from "../../types/photo-scene";

export const SCENE_ERGONOMICS_VERSION = "scene-ergonomics-v1.0-beta.1" as const;
export const SCENE_ASSESSMENT_SCHEMA = "scene-ergonomic-assessment-v1.0" as const;
export const SCENE_REPORT_VERSION = "scene-design-report-v1.0-beta.1" as const;

export type DataSource = "USER_PROVIDED" | "DERIVED" | "SCENE_CALIBRATED" | "SCENE_ESTIMATED" | "UNKNOWN";
export type QualityLevel = "HIGH" | "PARTIAL" | "LOW" | "UNKNOWN";
export type TechnicalValue<T> = { value: T | null; unit: string | null; valid: boolean; quality: number; source: DataSource; frame: string; rejectionReason: string | null };
export type WorkTaskType = "PRECISION" | "LIGHT_WORK" | "MODERATE_FORCE" | "HEAVY_WORK" | "UNKNOWN";
export type HandSide = "LEFT" | "RIGHT";
export type BodyRegion = "HEAD" | "NECK" | "TORSO" | "LEFT_ARM" | "RIGHT_ARM" | "LEFT_HAND" | "RIGHT_HAND" | "LEFT_LEG" | "RIGHT_LEG";
export type WorkZone = "PRIMARY_ZONE" | "FUNCTIONAL_ZONE" | "MAXIMUM_ZONE" | "OUTSIDE_ZONE" | "UNKNOWN";
export type BodyMovementRequirement = "NONE" | "SMALL" | "MODERATE" | "LARGE" | "UNREACHABLE" | "UNKNOWN";

export type SceneManualContext = {
  taskType: WorkTaskType; postureDurationSeconds: number | null; repetitionsPerMinute: number | null;
  objectMassKg: number | null; forceKnown: boolean; rulaForceLoad: number | null; rulaMuscleUse: number | null;
  rebaLoadForce: number | null; rebaCoupling: number | null; rebaActivity: number | null; supportDescription: string | null;
};
export type SceneTaskStep = { id: string; type: "REACH" | "GRASP" | "MOVE_OBJECT" | "PLACE" | "PRESS_BUTTON" | "RETURN"; humanId: string; hand: HandSide; targetObjectId: string | null; targetPointId: string | null; startPose: string | null; endPose: string | null; durationSeconds: number | null; repetitions: number | null };
export type SceneTaskSequence = { id: string; name: string; steps: SceneTaskStep[] };

export type ErgonomicsHumanInput = {
  id: string; profile: HumanProfile; rootPositionCm: Vector3Cm; rootRotationDeg: Vector3Cm;
  jointPositionsCm: Record<string, Vector3Cm>; jointRotationsDeg: Record<string, Vector3Cm>;
  hands: { left: { preset: HandPosePreset }; right: { preset: HandPosePreset } };
  heldObjectIds: string[]; supportState: "STANDING" | "SEATED" | "UNKNOWN"; provenance: DataSource;
};
export type ErgonomicsObjectInput = { id: string; name: string; type: SceneObjectType; geometry: ObjectGeometry3D | null; interactionPoints: { id: string; name: string; type: string; positionCm: Vector3Cm; hand: HandSide | "BOTH" | null }[]; provenance: DataSource };
export type SceneErgonomicsInput = {
  schemaVersion: "scene-ergonomics-input-v1"; sceneId: string; sceneRevision: string; sceneSchemaVersion: "1.4";
  calibrationQuality: QualityLevel; humans: ErgonomicsHumanInput[]; objects: ErgonomicsObjectInput[];
  task: SceneTaskSequence | null; manualContext: SceneManualContext; createdAt: string;
};

export type JointAngleSet = Record<string, TechnicalValue<number>>;
export type PostureSnapshot = { humanId: string; humanRootCm: Vector3Cm; jointAngles: JointAngleSet; supportState: string; handState: Record<string,string>; heldObjectIds: string[]; collisions: CollisionResult3D[]; taskProgress: number | null };
export type WorkHeightResult = { objectId: string | null; surfaceHeightCm: TechnicalValue<number>; elbowHeightCm: TechnicalValue<number>; shoulderHeightCm: TechnicalValue<number>; hipHeightCm: TechnicalValue<number>; eyeHeightCm: TechnicalValue<number>; differenceFromElbowCm: TechnicalValue<number>; taskType: WorkTaskType; classification: "BELOW_REFERENCE" | "AT_REFERENCE" | "ABOVE_REFERENCE" | "UNKNOWN" };
export type ReachAssessment = { humanId: string; objectId: string; pointId: string; pointName: string; hand: HandSide; zone: WorkZone; reachMarginCm: number | null; armOnly: string; wholeBody: string; movementRequirement: BodyMovementRequirement; crossBody: boolean; targetHeightRelativeToShoulderCm: number | null; targetHeightRelativeToKneeCm: number | null; horizontalFromShoulderCm: number | null; quality: number };
export type ClearanceItem = { humanId: string; objectId: string; bodyRegion: BodyRegion; level: "CLEAR" | "CONTACT" | "PENETRATION" | "UNKNOWN_GEOMETRY"; minimumClearanceCm: number | null; quality: number; source: DataSource };
export type VisionResult = { humanId: string; objectId: string; pointId: string | null; distanceCm: number | null; verticalAngleDeg: number | null; horizontalAngleDeg: number | null; blocked: boolean | null; quality: number; reason: string | null };
export type GripAssessment = { humanId: string; hand: HandSide; objectId: string | null; preset: HandPosePreset; geometryStatus: "GEOMETRY_VALID" | "GEOMETRY_PARTIAL" | "GEOMETRY_INVALID" | "UNKNOWN"; massKg: number | null; massSource: DataSource; wristFlexionDeg: number | null; wristDeviationDeg: number | null; reasons: string[] };
export type MethodEvidence = { name: string; rawInput: number | string | boolean | null; scoreComponent: number | null; possibleScores: number[]; source: DataSource; quality: number; missingEvidence: string[] };
export type MethodResult = { method: "RULA" | "REBA"; side: HandSide; status: "COMPLETE" | "PARTIAL" | "INSUFFICIENT_DATA"; score: number | null; scoreRange: { min: number; max: number } | null; components: Record<string,MethodEvidence>; methodVersion: string; tableSourceVersion: string };
export type FindingType = "HIGH_WORK_SURFACE"|"LOW_WORK_SURFACE"|"OVERHEAD_REACH"|"LOW_REACH"|"CROSS_BODY_REACH"|"REACH_AT_LIMIT"|"UNREACHABLE_TARGET"|"COLLISION"|"INSUFFICIENT_CLEARANCE"|"TRUNK_FLEXION"|"TRUNK_ROTATION"|"NECK_FLEXION"|"SHOULDER_ELEVATION"|"WRIST_DEVIATION"|"GRIP_GEOMETRY_ISSUE"|"VISUAL_TARGET_ANGLE"|"TASK_PATH_COLLISION";
export type SceneFinding = { id:string; type:FindingType; priority:"HIGH"|"MEDIUM"|"INFORMATIONAL"; humanId:string; bodyRegion:BodyRegion|null; objectId:string|null; taskStepId:string|null; measurement:string; value:number|null; rule:string; quality:number; source:DataSource; description:string };
export type SceneRecommendation = { id:string; sourceFindingId:string; priority:"HIGH"|"MEDIUM"|"INFORMATIONAL"; text:string; reason:string; quality:number };
export type MissingDatum = { id:string; label:string; reason:string; materialFor:string[]; priority:"REQUIRED"|"RECOMMENDED"|"OPTIONAL" };
export type TaskSample = { stepId:string; progress:number; angles:JointAngleSet; reach:ReachAssessment|null; collisions:CollisionResult3D[]; rankingScore:number };
export type TaskAssessment = { taskId:string; samples:TaskSample[]; worstSample:TaskSample|null; firstCollision:TaskSample|null; maximumReachSample:TaskSample|null; exposure:{known:boolean; totalDurationSeconds:number|null; timeAtReachLimitSeconds:number|null; elevatedArmSeconds:number|null; trunkFlexionSeconds:number|null} };

export type SceneAssessmentResult = {
  schemaVersion: typeof SCENE_ASSESSMENT_SCHEMA; engineVersion: typeof SCENE_ERGONOMICS_VERSION; reportVersion: typeof SCENE_REPORT_VERSION;
  calculatedAt: string; sceneId: string; sceneRevision: string; sceneSchemaVersion: "1.4"; status: "CURRENT" | "STALE";
  humans: Record<string,{ posture:PostureSnapshot; workHeight:WorkHeightResult|null; reach:ReachAssessment[]; clearance:ClearanceItem[]; vision:VisionResult[]; grip:GripAssessment[]; rula:{left:MethodResult;right:MethodResult}; reba:{left:MethodResult;right:MethodResult} }>;
  task: TaskAssessment|null; findings:SceneFinding[]; recommendations:SceneRecommendation[]; missingData:MissingDatum[];
  quality:{overall:QualityLevel;modules:Record<string,QualityLevel>;coverage:number}; limitations:string[];
  traceability:{sceneRevision:string;humanIds:string[];taskId:string|null;engineVersion:string;calculatedAt:string};
};

export const emptyManualContext = (): SceneManualContext => ({ taskType:"UNKNOWN", postureDurationSeconds:null, repetitionsPerMinute:null, objectMassKg:null, forceKnown:false, rulaForceLoad:null, rulaMuscleUse:null, rebaLoadForce:null, rebaCoupling:null, rebaActivity:null, supportDescription:null });
