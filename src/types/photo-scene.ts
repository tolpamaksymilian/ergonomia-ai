export type AnalysisType = "VIDEO" | "PHOTO_SCENE";

export type NormalizedPoint = { x: number; y: number };
export type NormalizedBox = { x: number; y: number; width: number; height: number };

export type SceneObjectType =
  | "WORK_SURFACE" | "TABLE" | "SHELF" | "RACK" | "CHAIR" | "STOOL"
  | "CONVEYOR" | "MACHINE" | "CONTROL_PANEL" | "MONITOR" | "CONTAINER"
  | "PALLET" | "OTHER";

export type SceneObjectStatus =
  | "DETECTED" | "USER_CONFIRMED" | "USER_MODIFIED" | "USER_ADDED" | "USER_REJECTED";

export type SceneObjectMeasurement = {
  heightCm: number | null;
  widthCm: number | null;
  depthCm: number | null;
  workSurfaceHeightCm: number | null;
  lowerEdgeHeightCm: number | null;
  upperEdgeHeightCm: number | null;
};

export type SceneObject = {
  id: string;
  sourceClass: string | null;
  type: SceneObjectType;
  name: string;
  bbox: NormalizedBox;
  detectorConfidence: number | null;
  source: "YOLOX_X_COCO" | "USER";
  status: SceneObjectStatus;
  visible: boolean;
  measurements: SceneObjectMeasurement;
  referencePoint: (NormalizedPoint & { heightCm: number }) | null;
};

export type CalibrationAnchor = {
  id: string;
  lower: NormalizedPoint;
  upper: NormalizedPoint;
  pixelDistance: number;
  realDistanceCm: number;
  objectId: string | null;
  source: "USER_PROVIDED";
};

export type SceneCalibration = {
  status: "UNCALIBRATED" | "PARTIALLY_CALIBRATED" | "CALIBRATED_2D";
  floorBaseline: { start: NormalizedPoint; end: NormalizedPoint } | null;
  anchors: CalibrationAnchor[];
};

export type HumanProfile = {
  name: string;
  heightCm: number;
  armSpanCm: number;
  functionalReachCm: number;
  shoulderHeightCm: number | null;
  elbowHeightCm: number | null;
  eyeHeightCm: number | null;
  hipHeightCm: number | null;
  upperLimbLengthCm: number | null;
  forearmLengthCm: number | null;
  handLengthCm: number | null;
  lowerLimbLengthCm: number | null;
  geometrySource: "USER_MEASUREMENTS" | "APPROXIMATE_DISPLAY_GEOMETRY";
};

export type HumanJointName =
  | "head" | "neck" | "leftShoulder" | "rightShoulder" | "leftElbow"
  | "rightElbow" | "leftWrist" | "rightWrist" | "leftHip" | "rightHip"
  | "leftKnee" | "rightKnee" | "leftAnkle" | "rightAnkle";

export type HumanPose = {
  preset: "STANDING" | "SEATED" | "REACHING" | "CUSTOM";
  mirrored: boolean;
  scaleLocked: boolean;
  joints: Record<HumanJointName, NormalizedPoint>;
};

export type SceneState = {
  schema_version: "1.0";
  objects: SceneObject[];
  calibration: SceneCalibration;
  human: HumanProfile | null;
  pose: HumanPose | null;
  viewport: { zoom: number; pan_x: number; pan_y: number };
  selectedObjectId?: string | null;
  reachVisible?: boolean;
};

export type SceneDetectionCandidate = {
  id: string;
  source_class: string;
  suggested_scene_type: SceneObjectType;
  bounding_box: NormalizedBox;
  confidence: number | null;
  source: "YOLOX_X_COCO";
  status: "DETECTED";
};

export type SceneDetection = {
  schema_version: "1.0";
  detection_version: "scene-detection-v0.1-beta.1";
  analysis_id: string;
  source_image: { width: number; height: number };
  candidates: SceneDetectionCandidate[];
  limitations: string[];
};
