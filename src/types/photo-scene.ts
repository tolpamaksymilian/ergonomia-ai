export type AnalysisType = "VIDEO" | "PHOTO_SCENE";
export type NormalizedPoint = { x: number; y: number };
export type NormalizedBox = { x: number; y: number; width: number; height: number };

export type SceneObjectType =
  | "WORK_SURFACE" | "TABLE" | "SHELF" | "RACK" | "CHAIR" | "STOOL"
  | "CONVEYOR" | "MACHINE" | "CONTROL_PANEL" | "MONITOR" | "CONTAINER"
  | "PALLET" | "WORK_ZONE" | "HANDLE" | "OTHER";
export type SceneObjectStatus = "DETECTED" | "USER_CONFIRMED" | "USER_MODIFIED" | "USER_ADDED" | "USER_REJECTED";
export type ObjectDimensionKey =
  | "heightCm" | "widthCm" | "depthCm" | "workSurfaceHeightCm" | "lowerEdgeHeightCm"
  | "upperEdgeHeightCm" | "seatHeightCm" | "seatWidthCm" | "backrestHeightCm"
  | "seatDepthCm" | "screenCenterHeightCm" | "screenHeightCm" | "userDistanceCm"
  | "keyShelfHeightCm" | "workingWidthCm" | "controlHeightCm";
export type SceneObjectMeasurement = Record<ObjectDimensionKey, number | null>;
export type MeasurementProvenance = "USER_MEASURED" | "WORKER_SUGGESTED" | "SCENE_ESTIMATED" | "USER_CONFIRMED_ESTIMATE" | "UNKNOWN";
export type EvidenceQuality = "UNKNOWN" | "LOW" | "MEDIUM" | "HIGH";
export type MeasurementEstimateStatus = "UNKNOWN" | "SUGGESTED" | "ESTIMATED" | "CONFIRMED" | "MEASURED" | "REJECTED";
export type GeometryOrientation = "VERTICAL" | "HORIZONTAL" | "DEPTH" | "FREE";

export type GeometryMeasurement = {
  id: string;
  objectId: string | null;
  dimensionKey: ObjectDimensionKey | null;
  name: string;
  valueCm: number | null;
  unit: "cm";
  start: NormalizedPoint;
  end: NormalizedPoint;
  orientation: GeometryOrientation;
  source: MeasurementProvenance;
  estimateStatus: MeasurementEstimateStatus;
  evidenceQuality: EvidenceQuality;
  reason: string | null;
  active: boolean;
  visible: boolean;
  locked: boolean;
  affectsScale: boolean;
};

export type ObjectInteractionPointType = "WORKING_POINT" | "GRIP_POINT" | "CONTROL_POINT" | "PLACEMENT_POINT";
export type ObjectInteractionPoint = { id: string; name: string; type: ObjectInteractionPointType; position: NormalizedPoint; visible: boolean };
export type SceneObject = {
  id: string; sourceClass: string | null; type: SceneObjectType; name: string; bbox: NormalizedBox;
  detectorConfidence: number | null; source: "YOLOX_X_COCO" | "USER"; status: SceneObjectStatus;
  visible: boolean; locked: boolean; measurements: SceneObjectMeasurement;
  geometryMeasurements: GeometryMeasurement[]; interactionPoints: ObjectInteractionPoint[];
  referencePoint: (NormalizedPoint & { heightCm: number }) | null;
};

export type ReferenceDimensionType = "HEIGHT" | "WIDTH" | "DEPTH" | "DISTANCE" | "WORK_SURFACE_HEIGHT" | "SHELF_HEIGHT" | "REACH_HEIGHT" | "CUSTOM";
export type ReferenceResidualStatus = "UNASSESSED" | "GOOD" | "WEAK" | "OUTLIER";
export type CalibrationReference = {
  id: string; name: string; dimensionType: ReferenceDimensionType; valueCm: number; unit: "cm";
  start: NormalizedPoint; end: NormalizedPoint; pixelDistance: number; objectId: string | null;
  active: boolean; visible: boolean; locked: boolean; affectsScale: boolean;
  source: "USER_PROVIDED" | "OBJECT_DIMENSION" | "USER_CONFIRMED_ESTIMATE";
  residual: number | null; residualStatus: ReferenceResidualStatus; manualOverride: boolean;
};
export type CalibrationAnchor = { id: string; lower: NormalizedPoint; upper: NormalizedPoint; pixelDistance: number; realDistanceCm: number; objectId: string | null; source: "USER_PROVIDED" };
export type CalibrationQuality = "NONE" | "PARTIAL" | "GOOD" | "ATTENTION_REQUIRED";
export type PerspectiveScaleStatus = "NO_SCALE" | "LOCAL_ONLY" | "PERSPECTIVE_PARTIAL" | "PERSPECTIVE_GOOD" | "INCONSISTENT";
export type PerspectiveScaleField = {
  status: PerspectiveScaleStatus;
  coefficients: [number, number, number] | null;
  model: "NONE" | "LOCAL" | "INVERSE_AFFINE_2D";
  anchorCount: number; inlierCount: number; residualRms: number | null; uncertainty: number | null;
  generatedAt: string | null;
};
export type SceneCalibration = {
  status: "UNCALIBRATED" | "PARTIALLY_CALIBRATED" | "CALIBRATED_2D";
  floorBaseline: { start: NormalizedPoint; end: NormalizedPoint } | null;
  horizonY: number | null; verticalDirection: NormalizedPoint | null;
  references: CalibrationReference[]; scaleField: PerspectiveScaleField;
};

export type HumanProfilePreset = "SHORT" | "MEDIUM" | "TALL" | "CUSTOM";
export type SegmentProvenance = "USER_PROVIDED" | "DERIVED_APPROXIMATION";
export type HumanSegmentKey = "headNeck" | "torso" | "shoulderGirdle" | "pelvis" | "upperArm" | "forearm" | "hand" | "thigh" | "lowerLeg" | "foot";
export type HumanProfile = {
  name: string; preset: HumanProfilePreset; heightCm: number; armSpanCm: number;
  functionalReachCm: number; maximumReachCm: number; shoulderHeightCm: number | null;
  elbowHeightCm: number | null; eyeHeightCm: number | null; hipHeightCm: number | null;
  upperArmLengthCm: number | null; forearmLengthCm: number | null; handLengthCm: number | null;
  thighLengthCm: number | null; lowerLegLengthCm: number | null;
  geometrySource: "USER_MEASUREMENTS" | "ANTHROPOMETRIC_ESTIMATE";
  segmentProvenance: Record<HumanSegmentKey, SegmentProvenance>;
};
export type HumanJointName =
  | "head" | "neck" | "leftShoulder" | "rightShoulder" | "leftElbow" | "rightElbow"
  | "leftWrist" | "rightWrist" | "leftHand" | "rightHand" | "pelvisRoot"
  | "leftHip" | "rightHip" | "leftKnee" | "rightKnee" | "leftAnkle" | "rightAnkle"
  | "leftFoot" | "rightFoot";
export type HumanPosture = "STANDING" | "SEATED" | "REACHING" | "FORWARD_LEAN" | "WORK_SURFACE" | "ONE_HANDED" | "TWO_HANDED" | "CUSTOM";
export type LimbReachState = "NATURAL" | "COMFORT_EXCEEDED" | "OUT_OF_REACH" | "SOFT_LIMIT";
export type HumanSegmentConstraint = {
  id: HumanSegmentKey; parentJoint: HumanJointName; childJoint: HumanJointName;
  fixedLengthCm: number; proximalWidthCm: number; distalWidthCm: number;
  preferredOrientationDeg: number; minimumJointAngleDeg: number; maximumJointAngleDeg: number;
  provenance: SegmentProvenance;
};
export type HumanConstraintGraph = Record<HumanSegmentKey, HumanSegmentConstraint>;
export type HumanPose = {
  preset: HumanPosture; mirrored: boolean; scaleLocked: boolean;
  joints: Record<HumanJointName, NormalizedPoint>;
  reachState: { leftArm: LimbReachState; rightArm: LimbReachState; leftLeg: LimbReachState; rightLeg: LimbReachState };
  bendPreference: { leftArm: 1 | -1; rightArm: 1 | -1; leftLeg: 1 | -1; rightLeg: 1 | -1 };
};
export type HumanFacingPreset = "FRONT" | "LEFT" | "RIGHT" | "TOWARD_OBJECT" | "CUSTOM";
export type HumanPositionMode = "FREE" | "WORKING_AT_OBJECT" | "SEATED_AT_OBJECT";
export type HumanHandTarget = { interactionPointId: string; objectId: string; status: "REACHABLE" | "OUT_OF_REACH" } | null;
export type SceneHuman = {
  id: string; name: string; color: string; profile: HumanProfile; constraints: HumanConstraintGraph; pose: HumanPose;
  placement: {
    root: NormalizedPoint; leftFootContact: NormalizedPoint; rightFootContact: NormalizedPoint;
    contactPoint: NormalizedPoint; floorPinned: boolean; attachedObjectId: string | null;
    positionMode: HumanPositionMode; orientationDeg: number; facingPreset: HumanFacingPreset;
    lastScalePxPerCm: number | null; scaleStatus: PerspectiveScaleStatus;
  };
  handTargets: { left: HumanHandTarget; right: HumanHandTarget };
  visible: boolean; locked: boolean;
};

export type TechnicalInsight = {
  id: string; severity: "INFO" | "ATTENTION";
  code: "INSUFFICIENT_CALIBRATION" | "COMFORT_REACH_EXCEEDED" | "NATURAL_REACH_EXCEEDED" | "MISSING_OBJECT_DIMENSION" | "CALIBRATION_REGION_MISSING" | "PERSPECTIVE_DETECTED";
  message: string; objectId: string | null; humanId: string | null;
};
export type SceneLayerKey = "CALIBRATION" | "OBJECT_DIMENSIONS" | "USER_MEASUREMENTS" | "HUMAN_REACH" | "SUGGESTIONS" | "DEBUG";
export type SceneViewPreset = "CLEAN" | "DIMENSIONS" | "CALIBRATION" | "HUMAN";
export type ReachDisplayMode = "COMFORT" | "FUNCTIONAL" | "MAXIMUM";
export type SceneViewState = { layers: Record<SceneLayerKey, boolean>; preset: SceneViewPreset; focusMode: boolean; reachMode: ReachDisplayMode };
export type WorkerDimensionSuggestion = {
  id: string; object_id: string; dimension_type: ObjectDimensionKey; endpoints: { start: NormalizedPoint; end: NormalizedPoint };
  source: "WORKER_GEOMETRY_HEURISTIC"; estimated_value_cm: number | null;
  estimate_status: "UNKNOWN" | "ESTIMATED_FROM_SCENE"; evidence_quality: EvidenceQuality; reason: string;
  status?: "PENDING" | "ACCEPTED" | "REJECTED";
};
export type PerspectiveEvidence = { dominant_vertical_angle_deg: number | null; dominant_horizontal_angle_deg: number | null; vanishing_point: NormalizedPoint | null; evidence_quality: EvidenceQuality };

export type SceneState = {
  schema_version: "1.2"; objects: SceneObject[]; calibration: SceneCalibration; humans: SceneHuman[];
  geometryMeasurements: GeometryMeasurement[]; workerSuggestions: WorkerDimensionSuggestion[];
  viewport: { zoom: number; pan_x: number; pan_y: number };
  selectedObjectId: string | null; selectedHumanId: string | null; selectedReferenceId: string | null;
  reachVisible: boolean; measurementFilter: "ALL" | "ACTIVE" | "SELECTED_OBJECT" | "CALIBRATION";
  view: SceneViewState; autoSuggestDimensions: boolean; technicalInsights: TechnicalInsight[];
};

export type SceneDetectionCandidate = { id: string; source_class: string; suggested_scene_type: SceneObjectType; bounding_box: NormalizedBox; confidence: number | null; source: "YOLOX_X_COCO"; status: "DETECTED" };
export type GeometryCandidate = { id: string; start: NormalizedPoint; end: NormalizedPoint; orientation: GeometryOrientation; evidence_quality: EvidenceQuality };
export type SceneDetection = {
  schema_version: "1.0"; detection_version: "scene-detection-v0.1-beta.1" | "scene-detection-v0.2-beta.1";
  analysis_id: string; source_image: { width: number; height: number }; candidates: SceneDetectionCandidate[];
  geometry_candidates?: GeometryCandidate[]; dimension_suggestions?: WorkerDimensionSuggestion[];
  perspective_evidence?: PerspectiveEvidence; floor_candidates?: GeometryCandidate[]; surface_candidates?: GeometryCandidate[];
  limitations: string[];
};
