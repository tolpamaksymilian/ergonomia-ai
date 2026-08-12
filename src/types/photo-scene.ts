export type AnalysisType = "VIDEO" | "PHOTO_SCENE";

export type NormalizedPoint = { x: number; y: number };
export type NormalizedBox = { x: number; y: number; width: number; height: number };

export type SceneObjectType =
  | "WORK_SURFACE" | "TABLE" | "SHELF" | "RACK" | "CHAIR" | "STOOL"
  | "CONVEYOR" | "MACHINE" | "CONTROL_PANEL" | "MONITOR" | "CONTAINER"
  | "PALLET" | "WORK_ZONE" | "HANDLE" | "OTHER";

export type SceneObjectStatus =
  | "DETECTED" | "USER_CONFIRMED" | "USER_MODIFIED" | "USER_ADDED" | "USER_REJECTED";

export type ObjectDimensionKey =
  | "heightCm" | "widthCm" | "depthCm" | "workSurfaceHeightCm"
  | "lowerEdgeHeightCm" | "upperEdgeHeightCm" | "seatHeightCm"
  | "backrestHeightCm" | "seatDepthCm" | "screenCenterHeightCm"
  | "userDistanceCm" | "keyShelfHeightCm" | "workingWidthCm";

export type SceneObjectMeasurement = Record<ObjectDimensionKey, number | null>;

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
  locked: boolean;
  measurements: SceneObjectMeasurement;
  referencePoint: (NormalizedPoint & { heightCm: number }) | null;
};

export type ReferenceDimensionType =
  | "HEIGHT" | "WIDTH" | "DEPTH" | "DISTANCE" | "WORK_SURFACE_HEIGHT"
  | "SHELF_HEIGHT" | "REACH_HEIGHT" | "CUSTOM";

export type CalibrationReference = {
  id: string;
  name: string;
  dimensionType: ReferenceDimensionType;
  valueCm: number;
  unit: "cm";
  start: NormalizedPoint;
  end: NormalizedPoint;
  pixelDistance: number;
  objectId: string | null;
  active: boolean;
  visible: boolean;
  locked: boolean;
  affectsScale: boolean;
  source: "USER_PROVIDED" | "OBJECT_DIMENSION";
};

/** Legacy 1.0 anchor, accepted only by the migration normalizer. */
export type CalibrationAnchor = {
  id: string;
  lower: NormalizedPoint;
  upper: NormalizedPoint;
  pixelDistance: number;
  realDistanceCm: number;
  objectId: string | null;
  source: "USER_PROVIDED";
};

export type CalibrationQuality = "NONE" | "PARTIAL" | "GOOD" | "ATTENTION_REQUIRED";

export type SceneCalibration = {
  status: "UNCALIBRATED" | "PARTIALLY_CALIBRATED" | "CALIBRATED_2D";
  floorBaseline: { start: NormalizedPoint; end: NormalizedPoint } | null;
  horizonY: number | null;
  references: CalibrationReference[];
};

export type HumanProfilePreset = "SHORT" | "MEDIUM" | "TALL" | "CUSTOM";
export type HumanProfile = {
  name: string;
  preset: HumanProfilePreset;
  heightCm: number;
  armSpanCm: number;
  functionalReachCm: number;
  maximumReachCm: number;
  shoulderHeightCm: number | null;
  elbowHeightCm: number | null;
  eyeHeightCm: number | null;
  hipHeightCm: number | null;
  upperArmLengthCm: number | null;
  forearmLengthCm: number | null;
  handLengthCm: number | null;
  thighLengthCm: number | null;
  lowerLegLengthCm: number | null;
  geometrySource: "USER_MEASUREMENTS" | "ANTHROPOMETRIC_ESTIMATE";
};

export type HumanJointName =
  | "head" | "neck" | "leftShoulder" | "rightShoulder" | "leftElbow"
  | "rightElbow" | "leftWrist" | "rightWrist" | "leftHand" | "rightHand"
  | "leftHip" | "rightHip" | "leftKnee" | "rightKnee"
  | "leftAnkle" | "rightAnkle" | "leftFoot" | "rightFoot";

export type HumanPosture =
  | "STANDING" | "SEATED" | "REACHING" | "FORWARD_LEAN"
  | "WORK_SURFACE" | "ONE_HANDED" | "TWO_HANDED" | "CUSTOM";

export type LimbReachState = "NATURAL" | "COMFORT_EXCEEDED" | "OUT_OF_REACH";

export type HumanPose = {
  preset: HumanPosture;
  mirrored: boolean;
  scaleLocked: boolean;
  joints: Record<HumanJointName, NormalizedPoint>;
  reachState: { leftArm: LimbReachState; rightArm: LimbReachState; leftLeg: LimbReachState; rightLeg: LimbReachState };
};

export type SceneHuman = {
  id: string;
  name: string;
  color: string;
  profile: HumanProfile;
  pose: HumanPose;
  placement: {
    contactPoint: NormalizedPoint;
    floorPinned: boolean;
    attachedObjectId: string | null;
    attachmentMode: "NONE" | "WORK_SURFACE" | "SEATED_AT_OBJECT";
  };
  visible: boolean;
  locked: boolean;
};

export type TechnicalInsight = {
  id: string;
  severity: "INFO" | "ATTENTION";
  code: "INSUFFICIENT_CALIBRATION" | "COMFORT_REACH_EXCEEDED" | "NATURAL_REACH_EXCEEDED" | "MISSING_OBJECT_DIMENSION";
  message: string;
  objectId: string | null;
  humanId: string | null;
};

export type SceneStateV11 = {
  schema_version: "1.1";
  objects: SceneObject[];
  calibration: SceneCalibration;
  humans: SceneHuman[];
  viewport: { zoom: number; pan_x: number; pan_y: number };
  selectedObjectId: string | null;
  selectedHumanId: string | null;
  selectedReferenceId: string | null;
  reachVisible: boolean;
  measurementFilter: "ALL" | "ACTIVE" | "SELECTED_OBJECT" | "CALIBRATION";
  technicalInsights: TechnicalInsight[];
};

export type SceneStateV10 = {
  schema_version: "1.0";
  objects: SceneObject[];
  calibration: {
    status: SceneCalibration["status"];
    floorBaseline: SceneCalibration["floorBaseline"];
    anchors: CalibrationAnchor[];
  };
  human: Omit<HumanProfile, "preset" | "maximumReachCm" | "upperArmLengthCm" | "thighLengthCm" | "lowerLegLengthCm"> & {
    upperLimbLengthCm: number | null;
    lowerLimbLengthCm: number | null;
  } | null;
  pose: Omit<HumanPose, "reachState"> | null;
  viewport: SceneStateV11["viewport"];
  selectedObjectId?: string | null;
  reachVisible?: boolean;
};

export type SceneState = SceneStateV11;

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
