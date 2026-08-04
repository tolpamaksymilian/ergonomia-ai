export type AnalysisFocusMode = "full" | "upper" | "arm";

export type AnalysisRegionId =
  | "neck"
  | "shoulders"
  | "trunk"
  | "rightElbow"
  | "hips"
  | "knees";

export type ModelLandmarkId =
  | "crown"
  | "head"
  | "headBase"
  | "neck"
  | "chest"
  | "pelvis"
  | "leftShoulder"
  | "rightShoulder"
  | "leftElbow"
  | "rightElbow"
  | "leftWrist"
  | "rightWrist"
  | "leftHand"
  | "rightHand"
  | "leftHip"
  | "rightHip"
  | "leftKnee"
  | "rightKnee"
  | "leftAnkle"
  | "rightAnkle"
  | "leftFoot"
  | "rightFoot";

export type ModelSegmentId =
  | "neck"
  | "shoulderGirdle"
  | "torso"
  | "pelvis"
  | "leftUpperArm"
  | "leftForearm"
  | "rightUpperArm"
  | "rightForearm"
  | "leftThigh"
  | "leftShin"
  | "rightThigh"
  | "rightShin";

export type AnalysisGuideId =
  | "neckAngle"
  | "shoulderAxis"
  | "trunkAxis"
  | "elbowAngle"
  | "hipAxis"
  | "kneeAngles";

export type Point3D = readonly [number, number, number];

export type AnalysisRegion = {
  id: AnalysisRegionId;
  label: string;
  metric: string;
  description: string;
  color: string;
  activeLandmarks: readonly ModelLandmarkId[];
  activeSegments: readonly ModelSegmentId[];
  guide: AnalysisGuideId;
};

export type HumanModelProportions = {
  totalHeight: number;
  headHeight: number;
  headWidth: number;
  headDepth: number;
  neckLength: number;
  neckWidth: number;
  shoulderWidth: number;
  chestWidth: number;
  chestDepth: number;
  waistWidth: number;
  pelvisWidth: number;
  pelvisDepth: number;
  torsoLength: number;
  upperArmLength: number;
  forearmLength: number;
  handLength: number;
  palmLength: number;
  palmWidth: number;
  thighLength: number;
  lowerLegLength: number;
  footLength: number;
  footWidth: number;
  segmentRadii: {
    upperArm: readonly [number, number];
    forearm: readonly [number, number];
    thigh: readonly [number, number];
    shin: readonly [number, number];
  };
};

export type CameraPreset = {
  position: Point3D;
  target: Point3D;
};

export const technicalHumanProportions: HumanModelProportions = {
  totalHeight: 5,
  headHeight: 0.65,
  headWidth: 0.43,
  headDepth: 0.48,
  neckLength: 0.3,
  neckWidth: 0.24,
  shoulderWidth: 1.12,
  chestWidth: 0.84,
  chestDepth: 0.48,
  waistWidth: 0.58,
  pelvisWidth: 0.72,
  pelvisDepth: 0.42,
  torsoLength: 1.48,
  upperArmLength: 0.86,
  forearmLength: 0.72,
  handLength: 0.41,
  palmLength: 0.24,
  palmWidth: 0.15,
  thighLength: 1.22,
  lowerLegLength: 1.17,
  footLength: 0.58,
  footWidth: 0.25,
  segmentRadii: {
    upperArm: [0.135, 0.105],
    forearm: [0.115, 0.075],
    thigh: [0.19, 0.145],
    shin: [0.14, 0.09],
  },
};

export const technicalHumanPose = {
  crown: [0, 2.55, 0.02],
  head: [0, 2.23, 0.04],
  headBase: [0, 1.92, 0.01],
  neck: [0, 1.78, 0],
  chest: [0, 1.24, 0.01],
  pelvis: [0, 0.27, 0],
  leftShoulder: [-0.56, 1.64, 0],
  rightShoulder: [0.56, 1.64, 0.02],
  leftElbow: [-0.69, 0.8, 0.08],
  rightElbow: [0.7, 0.81, 0.11],
  leftWrist: [-0.6, 0.1, 0.18],
  rightWrist: [0.62, 0.11, 0.2],
  leftHand: [-0.57, -0.16, 0.21],
  rightHand: [0.59, -0.15, 0.23],
  leftHip: [-0.28, 0.22, 0],
  rightHip: [0.28, 0.22, 0.02],
  leftKnee: [-0.31, -0.98, 0.07],
  rightKnee: [0.31, -0.96, 0.04],
  leftAnkle: [-0.31, -2.13, 0.02],
  rightAnkle: [0.31, -2.12, 0.04],
  leftFoot: [-0.31, -2.35, 0.24],
  rightFoot: [0.31, -2.34, 0.27],
} as const satisfies Record<ModelLandmarkId, Point3D>;

export const visualizationCamera = {
  fov: 35,
  pointerParallax: 0.055,
  desktop: {
    full: { position: [0.08, 0.04, 9.15], target: [0, 0.04, 0] },
    upper: { position: [0.03, 1.18, 6.15], target: [0, 1.18, 0] },
    arm: { position: [1.05, 0.92, 4.55], target: [0.5, 0.9, 0.08] },
  },
  compact: {
    full: { position: [0.02, 0.06, 9.65], target: [0, 0.03, 0] },
    upper: { position: [0.02, 1.2, 6.85], target: [0, 1.18, 0] },
    arm: { position: [0.9, 0.92, 5.25], target: [0.5, 0.9, 0.08] },
  },
} as const satisfies {
  fov: number;
  pointerParallax: number;
  desktop: Record<AnalysisFocusMode, CameraPreset>;
  compact: Record<AnalysisFocusMode, CameraPreset>;
};

export const visualizationPalette = {
  body: "#16434f",
  bodyRear: "#0b2b36",
  bodyActive: "#176171",
  bodyEmissive: "#0a3a45",
  activeEmissive: "#0e7490",
  landmark: "#a5f3fc",
  skeleton: "#67e8f9",
  reference: "#34d399",
  angle: "#fbbf24",
} as const;

export const visualizationDetail = {
  desktop: { radialSegments: 20, handSegments: 2, particles: 12, shadows: true },
  compact: { radialSegments: 12, handSegments: 1, particles: 0, shadows: false },
  floorY: -2.45,
  sceneHeight: { compact: 420, desktop: 540 },
} as const;

export const analysisRegions = [
  {
    id: "neck",
    label: "Szyja",
    metric: "Oś szyi i tułowia",
    description: "Punkty głowy, szyi i barków wyznaczają geometrię pomiaru 2D.",
    color: "#34d399",
    activeLandmarks: ["headBase", "neck", "leftShoulder", "rightShoulder"],
    activeSegments: ["neck", "shoulderGirdle"],
    guide: "neckAngle",
  },
  {
    id: "shoulders",
    label: "Barki",
    metric: "Elewacja ramion",
    description: "Położenie barków jest analizowane osobno dla lewej i prawej strony.",
    color: "#22d3ee",
    activeLandmarks: ["leftShoulder", "rightShoulder", "leftElbow", "rightElbow"],
    activeSegments: ["shoulderGirdle", "leftUpperArm", "rightUpperArm"],
    guide: "shoulderAxis",
  },
  {
    id: "trunk",
    label: "Tułów",
    metric: "Pochylenie względem pionu",
    description: "Oś biodra–barki tworzy techniczną linię odniesienia dla tułowia.",
    color: "#34d399",
    activeLandmarks: ["neck", "chest", "pelvis"],
    activeSegments: ["torso", "pelvis"],
    guide: "trunkAxis",
  },
  {
    id: "rightElbow",
    label: "Łokieć",
    metric: "Kąt zgięcia",
    description: "Kąt powstaje wyłącznie z dostępnych punktów barku, łokcia i nadgarstka.",
    color: "#fbbf24",
    activeLandmarks: ["rightShoulder", "rightElbow", "rightWrist"],
    activeSegments: ["rightUpperArm", "rightForearm"],
    guide: "elbowAngle",
  },
  {
    id: "hips",
    label: "Biodra",
    metric: "Oś centralna ciała",
    description: "Środek bioder stabilizuje główną oś geometryczną sylwetki.",
    color: "#22d3ee",
    activeLandmarks: ["pelvis", "leftHip", "rightHip"],
    activeSegments: ["pelvis", "leftThigh", "rightThigh"],
    guide: "hipAxis",
  },
  {
    id: "knees",
    label: "Kolana",
    metric: "Punkty podporu",
    description: "Kolana i kostki pomagają opisać ustawienie dolnej części ciała.",
    color: "#fbbf24",
    activeLandmarks: ["leftKnee", "rightKnee", "leftAnkle", "rightAnkle"],
    activeSegments: ["leftThigh", "leftShin", "rightThigh", "rightShin"],
    guide: "kneeAngles",
  },
] as const satisfies readonly AnalysisRegion[];

export function getAnalysisRegion(id: AnalysisRegionId): AnalysisRegion {
  return analysisRegions.find((region) => region.id === id) ?? analysisRegions[2];
}
