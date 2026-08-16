export type AnalysisType = "VIDEO" | "PHOTO_SCENE";
export type NormalizedPoint = { x: number; y: number };
export type NormalizedBox = { x: number; y: number; width: number; height: number };
export type Vector3Cm = { x: number; y: number; z: number };
export type EulerDegrees = { x: number; y: number; z: number };
export type SceneWorkspaceMode = "PHOTO" | "THREE_D" | "SPLIT";
export type CameraMappingStatus = "CAMERA_APPROXIMATE" | "CAMERA_PARTIAL" | "CAMERA_CALIBRATED";
export type Human3DJointName =
  | "root" | "pelvis" | "spineLower" | "spineMid" | "chest" | "neck" | "head" | "headTop"
  | "leftClavicle" | "leftShoulder" | "leftElbow" | "leftWrist" | "leftHand"
  | "rightClavicle" | "rightShoulder" | "rightElbow" | "rightWrist" | "rightHand"
  | "leftHip" | "leftKnee" | "leftAnkle" | "leftFoot" | "rightHip" | "rightKnee" | "rightAnkle" | "rightFoot";
export type FingerName = "thumb" | "index" | "middle" | "ring" | "little";
export type FingerPose = { curl: number; opposition: number };
export type HandPosePreset = "OPEN" | "RELAXED" | "POWER_GRIP" | "CYLINDER_GRIP" | "SPHERE_GRIP" | "PINCH" | "LATERAL_PINCH" | "CLOSED_FIST";
export type HandRigState = { preset: HandPosePreset; fingers: Record<FingerName, FingerPose>; palmRotationDeg: EulerDegrees };
export type Human3DState = {
  modelVersion: "digital-human-3d-v1";
  migrationStatus: "NATIVE_3D" | "MIGRATED_TO_3D";
  rootPositionCm: Vector3Cm; rootRotationDeg: EulerDegrees;
  jointRotationsDeg: Record<Human3DJointName, EulerDegrees>;
  jointPositionsCm: Record<Human3DJointName, Vector3Cm>;
  poleTargetsCm: { leftElbow: Vector3Cm; rightElbow: Vector3Cm; leftKnee: Vector3Cm; rightKnee: Vector3Cm };
  hands: { left: HandRigState; right: HandRigState };
  attachments: { leftObjectId: string | null; rightObjectId: string | null };
  legacy2dBackup: { posePreset: HumanPosture; normalizedRoot: NormalizedPoint } | null;
};
export type Primitive3DType = "BOX" | "CYLINDER" | "SPHERE" | "HANDLE" | "TOOL_GENERIC" | "BOTTLE" | "CONTAINER" | "PANEL" | "CUSTOM" | "PLANE_PROXY";
export type GeometryQuality = "COMPLETE" | "PARTIAL" | "UNKNOWN";
export type ObjectGeometry3D = {
  type: Primitive3DType; positionCm: Vector3Cm; rotationDeg: EulerDegrees;
  dimensionsCm: { width: number | null; height: number | null; depth: number | null; diameter: number | null; length: number | null };
  source: "USER_PROVIDED" | "DERIVED_FROM_CONFIRMED_DIMENSIONS" | "SHAPE_HINT";
  geometryQuality: GeometryQuality; collisionEnabled: boolean; collisionGroup: "STATIC_SCENE" | "HELD_OBJECT" | "NON_COLLIDING_REFERENCE";
  massKg: number | null; massSource: "USER_PROVIDED" | null;
};
export type InteractionPoint3D = { id: string; name: string; type: "GRIP" | "BUTTON" | "WORKING" | "PLACEMENT" | "SUPPORT"; positionCm: Vector3Cm; rotationDeg: EulerDegrees; hand: "LEFT" | "RIGHT" | "BOTH" | null };
export type ReachabilityLevel = "REACHABLE" | "REACHABLE_WITH_BODY_MOVEMENT" | "AT_LIMIT" | "UNREACHABLE" | "UNKNOWN";
export type ReachabilityResult3D = { level: ReachabilityLevel; mode: "ARM_ONLY" | "WHOLE_BODY"; hand: "LEFT" | "RIGHT"; targetId: string | null; reachMarginCm: number | null; reasons: string[] };
export type CollisionLevel3D = "CLEAR" | "CONTACT" | "PENETRATION" | "UNKNOWN_GEOMETRY";
export type CollisionResult3D = { level: CollisionLevel3D; humanPart: string | null; objectId: string | null; contactPointCm: Vector3Cm | null; penetrationDepthCm: number | null; geometryQuality: GeometryQuality };
export type MotionResult3D = { status: "CLEAR" | "COLLISION" | "UNREACHABLE" | "INVALID_GEOMETRY"; hand: "LEFT" | "RIGHT"; startCm: Vector3Cm; targetCm: Vector3Cm; sampleCount: number; firstCollisionProgress: number | null; firstCollision: CollisionResult3D | null };
export type Scene3DState = {
  unit: "cm"; cameraMappingStatus: CameraMappingStatus; workspaceMode: SceneWorkspaceMode;
  snapCm: 1 | 5 | 10; selectedInteractionPointId: string | null;
  collisionBlocking: boolean; lastReachability: ReachabilityResult3D | null;
  lastCollisions: CollisionResult3D[]; motion: MotionResult3D | null;
};

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
export type MeasurementKind =
  | "VERTICAL_HEIGHT" | "HORIZONTAL_WIDTH" | "DEPTH" | "FLOOR_DISTANCE"
  | "OBJECT_HEIGHT" | "OBJECT_WIDTH" | "OBJECT_DEPTH" | "WORK_SURFACE_HEIGHT"
  | "SHELF_HEIGHT" | "SEAT_HEIGHT" | "SCREEN_HEIGHT" | "CUSTOM_DISTANCE";
export type MeasurementAxis = "VERTICAL" | "HORIZONTAL" | "GROUND_X" | "GROUND_Y" | "ARBITRARY";
export type MeasurementPlane = "VERTICAL_PLANE" | "GROUND_PLANE" | "OBJECT_FRONT_PLANE" | "OBJECT_TOP_PLANE" | "UNKNOWN_PLANE";
export type MeasurementPurpose = "CALIBRATION" | "OBJECT_DESCRIPTION" | "HUMAN_SCALE_VALIDATION" | "INFORMATION_ONLY";
export type MeasurementSemanticStatus = "CONFIRMED" | "SEMANTICS_REVIEW_REQUIRED";
export type WorldAnchor = {
  id: string; imagePoint: NormalizedPoint; worldHeightCm: number | null;
  role: "BOTTOM" | "TOP" | "GROUND" | "PLANE_POINT";
};

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
  measurementKind: MeasurementKind;
  axis: MeasurementAxis;
  plane: MeasurementPlane;
  purpose: MeasurementPurpose;
  useForCalibration: boolean;
  semanticStatus: MeasurementSemanticStatus;
};

export type ObjectInteractionPointType = "WORKING_POINT" | "GRIP_POINT" | "CONTROL_POINT" | "PLACEMENT_POINT";
export type ObjectInteractionPoint = { id: string; name: string; type: ObjectInteractionPointType; position: NormalizedPoint; visible: boolean };
export type SceneObject = {
  id: string; sourceClass: string | null; type: SceneObjectType; name: string; bbox: NormalizedBox;
  detectorConfidence: number | null; source: "YOLOX_X_COCO" | "USER"; status: SceneObjectStatus;
  visible: boolean; locked: boolean; measurements: SceneObjectMeasurement;
  geometryMeasurements: GeometryMeasurement[]; interactionPoints: ObjectInteractionPoint[];
  referencePoint: (NormalizedPoint & { heightCm: number }) | null;
  geometry3d: ObjectGeometry3D | null; interactionPoints3d: InteractionPoint3D[];
  regionIds: string[]; faceIds: string[]; planeIds: string[];
  shapeAssumptions: SceneShapeAssumption[];
  reconstructionQuality: ObjectReconstructionQuality;
};

export type ReferenceDimensionType = "HEIGHT" | "WIDTH" | "DEPTH" | "DISTANCE" | "WORK_SURFACE_HEIGHT" | "SHELF_HEIGHT" | "REACH_HEIGHT" | "CUSTOM";
export type ReferenceResidualStatus = "UNASSESSED" | "GOOD" | "WEAK" | "OUTLIER";
export type CalibrationReference = {
  id: string; name: string; dimensionType: ReferenceDimensionType; valueCm: number; unit: "cm";
  start: NormalizedPoint; end: NormalizedPoint; pixelDistance: number; objectId: string | null;
  active: boolean; visible: boolean; locked: boolean;
  measurementKind: MeasurementKind; axis: MeasurementAxis; plane: MeasurementPlane;
  purpose: MeasurementPurpose; useForCalibration: boolean; semanticStatus: MeasurementSemanticStatus;
  worldAnchors: { bottom: WorldAnchor | null; top: WorldAnchor | null };
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
  verticalDirectionSource: "DEFAULT_IMAGE_AXIS" | "WORKER_SUGGESTED" | "USER_CONFIRMED";
  verticalDirectionConfirmed: boolean;
  floorPlane: {
    mode: "NONE" | "BASIC" | "QUADRILATERAL";
    points: NormalizedPoint[];
    actualGroundDimensionCm: number | null;
    mappingStatus: "NONE" | "ORIENTATION_ONLY" | "PROJECTIVE";
  };
  references: CalibrationReference[]; scaleField: PerspectiveScaleField;
};

export type SceneGeometryProvenance =
  | "USER_PROVIDED" | "USER_CONFIRMED" | "WORKER_DETECTED" | "WORKER_SUGGESTED"
  | "SOLVER_DERIVED" | "SOLVER_ESTIMATED" | "AUTO_REPAIRED" | "ASSUMED" | "UNKNOWN";
export type SceneRegionType =
  | "FLOOR_REGION" | "WORK_SURFACE" | "OBJECT_TOP_FACE" | "OBJECT_FRONT_FACE"
  | "OBJECT_SIDE_FACE" | "OBJECT_REGION" | "MACHINE_REGION" | "SHELF_REGION"
  | "CONTROL_PANEL_REGION" | "STANDING_ZONE" | "MOVEMENT_ZONE" | "INTERACTION_ZONE"
  | "OBSTACLE_ZONE" | "NO_GO_ZONE" | "CUSTOM_REGION";
export type SceneRegionQuality = "UNKNOWN" | "LOW" | "MEDIUM" | "HIGH" | "INVALID";
export type SceneRegionPoint = {
  raw: NormalizedPoint;
  snapped: NormalizedPoint | null;
  effective: NormalizedPoint;
  snapSourceId: string | null;
  snapDistancePx: number | null;
};
export type SceneRegion = {
  id: string;
  type: SceneRegionType;
  label: string;
  polygonImageNormalized: SceneRegionPoint[];
  associatedObjectId: string | null;
  planeId: string | null;
  source: SceneGeometryProvenance;
  quality: SceneRegionQuality;
  visible: boolean;
  locked: boolean;
  createdAt: string;
  updatedAt: string;
};
export type SceneShapeAssumption = "RECTANGULAR" | "PLANAR" | "PARALLEL_EDGES" | "FREEFORM";
export type ObjectReconstructionQuality = "UNSOLVED" | "HIGH" | "PARTIAL" | "TWO_D_ONLY" | "INVALID";
export type ScenePlaneKind = "GROUND" | "OBJECT_TOP" | "OBJECT_FRONT" | "OBJECT_SIDE" | "SHELF" | "CONTROL_PANEL" | "CUSTOM";
export type ScenePlane = {
  id: string;
  kind: ScenePlaneKind;
  regionId: string | null;
  objectId: string | null;
  normal: Vector3Cm | null;
  offsetCm: number | null;
  homography: number[] | null;
  source: SceneGeometryProvenance;
  quality: SceneRegionQuality;
  locked: boolean;
};
export type SceneObjectFace = {
  id: string;
  objectId: string;
  regionId: string;
  planeId: string | null;
  kind: "TOP" | "FRONT" | "SIDE" | "FOOTPRINT" | "CUSTOM";
};
export type SceneConstraintNodeType =
  | "ImagePoint" | "ImageLine" | "ImageRegion" | "WorldPoint" | "WorldLine"
  | "WorldPlane" | "SceneObject" | "ObjectFace" | "GroundPlane" | "Camera" | "Dimension";
export type SceneConstraintType =
  | "DISTANCE" | "HEIGHT" | "WIDTH" | "DEPTH" | "COPLANAR" | "PARALLEL"
  | "PERPENDICULAR" | "HORIZONTAL" | "VERTICAL" | "RECTANGULAR" | "SAME_HEIGHT"
  | "ON_FLOOR" | "ON_PLANE" | "SHARED_EDGE" | "FIXED_POINT" | "USER_CONFIRMED";
export type SceneConstraintStatus = "ACTIVE" | "SATISFIED" | "WEAK" | "OUTLIER" | "CONFLICT" | "DISABLED";
export type SceneConstraintNode = { id: string; type: SceneConstraintNodeType; entityId: string; };
export type SceneGeometryConstraint = {
  id: string;
  type: SceneConstraintType;
  nodeIds: string[];
  objectId: string | null;
  regionId: string | null;
  target: { kind: "POINT" | "EDGE" | "REGION" | "OBJECT"; id: string | null; point: NormalizedPoint | null };
  rawValue: number | null;
  effectiveValue: number | null;
  unit: "cm" | "none";
  source: SceneGeometryProvenance;
  weight: number;
  useForSolver: boolean;
  status: SceneConstraintStatus;
  residual: number | null;
  imageSegment: { start: NormalizedPoint; end: NormalizedPoint } | null;
};
export type SceneConstraintGraph = {
  version: "scene-constraint-graph-v1.0";
  nodes: SceneConstraintNode[];
  constraints: SceneGeometryConstraint[];
};
export type CameraModelV2 = {
  version: "camera-model-v2.0";
  status: "UNRESOLVED" | "PARTIAL" | "PROJECTIVE" | "CALIBRATED_APPROXIMATE";
  vanishingDirections: { x: NormalizedPoint | null; y: NormalizedPoint | null; vertical: NormalizedPoint | null };
  evidenceQuality: EvidenceQuality;
  intrinsicsEstimated: boolean;
  diagnostics: string[];
};
export type GeometryReadinessGoal = "HUMAN_PLACEMENT" | "WORK_HEIGHT" | "REACH" | "COLLISION" | "FULL_3D";
export type GeometryReadinessStatus = "READY" | "PARTIAL" | "NEEDS_HEIGHT" | "NEEDS_WIDTH" | "NEEDS_DEPTH" | "INSUFFICIENT" | "INVALID" | "STALE";
export type GeometryReadiness = Record<GeometryReadinessGoal, { status: GeometryReadinessStatus; reasons: string[] }>;
export type GeometryCorrection = {
  id: string;
  type: "POLYGON_ORDER" | "SNAP" | "NEAREST_FEASIBLE" | "NUMERIC_CLAMP";
  entityId: string;
  before: unknown;
  after: unknown;
  delta: number;
  unit: "px" | "cm" | "normalized";
  reason: string;
};
export type GeometryConflict = { id: string; objectId: string | null; constraintIds: string[]; code: string; message: string };
export type NextBestMeasurement = {
  measurementKind: MeasurementKind;
  objectId: string | null;
  suggestedPoints: { start: NormalizedPoint; end: NormalizedPoint } | null;
  reason: string;
  expectedBenefit: string;
};
export type ReconstructionStatus = "UNSOLVED" | "QUEUED" | "SOLVING" | "SOLVED" | "PARTIAL" | "UNDERDETERMINED" | "INCONSISTENT" | "FAILED";
export type SceneReconstructionState = {
  version: "scene-reconstruction-v1.0-beta.1";
  geometryVersion: "scene-geometry-v2.0-beta.1";
  sceneRevision: string | null;
  status: ReconstructionStatus;
  cameraModel: CameraModelV2;
  readiness: GeometryReadiness;
  objectQuality: Record<string, ObjectReconstructionQuality>;
  constraintResiduals: Record<string, number>;
  outlierConstraintIds: string[];
  autoRepairs: GeometryCorrection[];
  conflicts: GeometryConflict[];
  missingConstraints: string[];
  nextBestMeasurements: NextBestMeasurement[];
  derivedDimensions: Record<string, Partial<Record<"heightCm" | "widthCm" | "depthCm", number>>>;
  worldGeometry: Record<string, {
    status: ObjectReconstructionQuality | "PROJECTIVE" | "PARTIAL";
    cornersCm: Vector3Cm[];
    polygonCm?: Vector3Cm[];
    sourcePlaneId?: string | null;
  }>;
  verticalScaleModel: {
    kind: "UNRESOLVED" | "ROBUST_CONSTANT" | "INVERSE_AFFINE_VERTICAL" | "FALLBACK_LOCAL";
    pixelsPerCm: number | null;
    coefficients: [number, number] | null;
    sourceConstraintIds: string[];
    quality: SceneRegionQuality;
  };
  diagnostics: { code: string; message: string }[];
  runtimeMs: number | null;
  completedAt: string | null;
};

export type HumanProfilePreset = "SHORT" | "MEDIUM" | "TALL" | "CUSTOM";
export type SegmentProvenance = "USER_PROVIDED" | "DERIVED_DISPLAY_APPROXIMATION";
export type HumanPhysicalDimensions = {
  statureCm: number; headHeightCm: number; neckLengthCm: number; shoulderWidthCm: number;
  chestWidthCm: number; waistWidthCm: number; pelvisWidthCm: number; torsoLengthCm: number;
  upperArmLengthCm: number; forearmLengthCm: number; handLengthCm: number;
  thighLengthCm: number; lowerLegLengthCm: number; footLengthCm: number;
  chestDepthCm: number; pelvisDepthCm: number; upperArmThicknessCm: number; forearmThicknessCm: number;
  thighThicknessCm: number; calfThicknessCm: number; handWidthCm: number; maxGripDiameterCm: number; pinchSpanCm: number;
};
export type HumanSegmentKey = "headNeck" | "torso" | "shoulderGirdle" | "pelvis" | "upperArm" | "forearm" | "hand" | "thigh" | "lowerLeg" | "foot";
export type HumanProfile = {
  name: string; preset: HumanProfilePreset; heightCm: number; armSpanCm: number;
  functionalReachCm: number; maximumReachCm: number; shoulderHeightCm: number | null;
  elbowHeightCm: number | null; eyeHeightCm: number | null; hipHeightCm: number | null;
  upperArmLengthCm: number | null; forearmLengthCm: number | null; handLengthCm: number | null;
  thighLengthCm: number | null; lowerLegLengthCm: number | null;
  geometrySource: "USER_MEASUREMENTS" | "ANTHROPOMETRIC_ESTIMATE";
  segmentProvenance: Record<HumanSegmentKey, SegmentProvenance>;
  physicalDimensions: HumanPhysicalDimensions;
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
export type HumanFacingPreset = "FRONT" | "BACK" | "LEFT" | "RIGHT" | "TOWARD_OBJECT" | "CUSTOM";
export type HumanPositionMode = "FREE" | "WORKING_AT_OBJECT" | "SEATED_AT_OBJECT";
export type HumanHandTarget = { interactionPointId: string; objectId: string; status: "REACHABLE" | "OUT_OF_REACH" } | null;
export type SceneHuman = {
  id: string; name: string; color: string; profile: HumanProfile; constraints: HumanConstraintGraph; pose: HumanPose;
  placement: {
    root: NormalizedPoint; leftFootContact: NormalizedPoint; rightFootContact: NormalizedPoint;
    contactPoint: NormalizedPoint; floorPinned: boolean; attachedObjectId: string | null;
    positionMode: HumanPositionMode; orientationDeg: number; facingPreset: HumanFacingPreset;
    lastScalePxPerCm: number | null; scaleStatus: PerspectiveScaleStatus;
    projectionStatus: "VALID" | "UNVERIFIED" | "PROJECTION_INVALID";
    projectionError: "VERTICAL_SCALE_MISSING" | "CALIBRATION_COVERAGE_UNKNOWN" | "PROJECTED_HEIGHT_OUT_OF_RANGE" | null;
    scaleReferences: string[]; calibrationCoverage: "GOOD" | "PARTIAL" | "UNKNOWN";
    backConvertedHeightCm: number | null;
  };
  handTargets: { left: HumanHandTarget; right: HumanHandTarget };
  modelVersion: "digital-human-v1";
  human3d: Human3DState;
  visible: boolean; locked: boolean;
};

export type TechnicalInsight = {
  id: string; severity: "INFO" | "ATTENTION";
  code: "INSUFFICIENT_CALIBRATION" | "COMFORT_REACH_EXCEEDED" | "NATURAL_REACH_EXCEEDED" | "MISSING_OBJECT_DIMENSION" | "CALIBRATION_REGION_MISSING" | "PERSPECTIVE_DETECTED";
  message: string; objectId: string | null; humanId: string | null;
};
export type SceneLayerKey = "OBJECTS" | "SURFACES" | "SOLVER" | "FLOOR" | "CALIBRATION" | "OBJECT_DIMENSIONS" | "USER_MEASUREMENTS" | "HUMAN_REACH" | "SUGGESTIONS" | "DEBUG";
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
  schema_version: "1.5"; objects: SceneObject[]; calibration: SceneCalibration; humans: SceneHuman[];
  regions: SceneRegion[]; planes: ScenePlane[]; objectFaces: SceneObjectFace[];
  constraintGraph: SceneConstraintGraph; reconstructionState: SceneReconstructionState;
  geometryMeasurements: GeometryMeasurement[]; workerSuggestions: WorkerDimensionSuggestion[];
  viewport: { zoom: number; pan_x: number; pan_y: number };
  selectedObjectId: string | null; selectedHumanId: string | null; selectedReferenceId: string | null; selectedRegionId: string | null;
  reachVisible: boolean; measurementFilter: "ALL" | "ACTIVE" | "SELECTED_OBJECT" | "CALIBRATION";
  view: SceneViewState; autoSuggestDimensions: boolean; technicalInsights: TechnicalInsight[];
  scene3d: Scene3DState;
};

export type SceneDetectionCandidate = { id: string; source_class: string; suggested_scene_type: SceneObjectType; bounding_box: NormalizedBox; confidence: number | null; source: "YOLOX_X_COCO"; status: "DETECTED" };
export type GeometryCandidate = { id: string; start: NormalizedPoint; end: NormalizedPoint; orientation: GeometryOrientation; evidence_quality: EvidenceQuality };
export type SceneDetection = {
  schema_version: "1.0"; detection_version: "scene-detection-v0.1-beta.1" | "scene-detection-v0.2-beta.1";
  result_status?: "SUCCESS" | "SUCCESS_NO_OBJECTS";
  analysis_id: string; source_image: { width: number; height: number }; candidates: SceneDetectionCandidate[];
  geometry_candidates?: GeometryCandidate[]; dimension_suggestions?: WorkerDimensionSuggestion[];
  perspective_evidence?: PerspectiveEvidence; floor_candidates?: GeometryCandidate[]; surface_candidates?: GeometryCandidate[];
  limitations: string[];
};
