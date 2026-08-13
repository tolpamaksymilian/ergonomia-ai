import type {
  HumanPhysicalDimensions, HumanProfile, HumanProfilePreset, HumanSegmentKey,
  SegmentProvenance,
} from "../../types/photo-scene";

export type CanonicalPointCm = { x: number; y: number; z: number };
export type CanonicalHuman = {
  unit: "cm";
  profile: HumanProfile;
  dimensions: HumanPhysicalDimensions;
  provenance: Record<HumanSegmentKey, SegmentProvenance>;
};

const DERIVED = "DERIVED_DISPLAY_APPROXIMATION" as const;

export function derivePhysicalDimensions(heightCm: number, overrides: Partial<HumanPhysicalDimensions> = {}): HumanPhysicalDimensions {
  const h = clamp(heightCm, 120, 220);
  const derived: HumanPhysicalDimensions = {
    statureCm: h,
    headHeightCm: h * 0.125,
    neckLengthCm: h * 0.037,
    shoulderWidthCm: h * 0.245,
    chestWidthCm: h * 0.205,
    waistWidthCm: h * 0.155,
    pelvisWidthCm: h * 0.175,
    torsoLengthCm: h * 0.288,
    upperArmLengthCm: h * 0.186,
    forearmLengthCm: h * 0.157,
    handLengthCm: h * 0.108,
    thighLengthCm: h * 0.245,
    lowerLegLengthCm: h * 0.246,
    footLengthCm: h * 0.152,
  };
  return Object.fromEntries(Object.entries(derived).map(([key, value]) => {
    const override = overrides[key as keyof HumanPhysicalDimensions];
    return [key, finitePositive(override) ? override : value];
  })) as HumanPhysicalDimensions;
}

export function createAnthropometricProfile(name: string, heightCm: number, preset: HumanProfilePreset = "CUSTOM"): HumanProfile {
  const dimensions = derivePhysicalDimensions(heightCm);
  const h = dimensions.statureCm;
  const provenance = derivedProvenance();
  return {
    name,
    preset,
    heightCm: h,
    armSpanCm: h,
    functionalReachCm: h * 0.40,
    maximumReachCm: h * 0.47,
    shoulderHeightCm: h * 0.818,
    elbowHeightCm: h * 0.63,
    eyeHeightCm: h * 0.936,
    hipHeightCm: h * 0.53,
    upperArmLengthCm: dimensions.upperArmLengthCm,
    forearmLengthCm: dimensions.forearmLengthCm,
    handLengthCm: dimensions.handLengthCm,
    thighLengthCm: dimensions.thighLengthCm,
    lowerLegLengthCm: dimensions.lowerLegLengthCm,
    geometrySource: "ANTHROPOMETRIC_ESTIMATE",
    segmentProvenance: provenance,
    physicalDimensions: dimensions,
  };
}

export function normalizePhysicalProfile(profile: HumanProfile): HumanProfile {
  const physicalDimensions = derivePhysicalDimensions(profile.heightCm, {
    ...profile.physicalDimensions,
    upperArmLengthCm: profile.upperArmLengthCm ?? undefined,
    forearmLengthCm: profile.forearmLengthCm ?? undefined,
    handLengthCm: profile.handLengthCm ?? undefined,
    thighLengthCm: profile.thighLengthCm ?? undefined,
    lowerLegLengthCm: profile.lowerLegLengthCm ?? undefined,
  });
  const provenance = Object.fromEntries(Object.entries(profile.segmentProvenance).map(([key, value]) => [
    key,
    value === "USER_PROVIDED" ? value : DERIVED,
  ])) as Record<HumanSegmentKey, SegmentProvenance>;
  return { ...profile, heightCm: physicalDimensions.statureCm, physicalDimensions, segmentProvenance: provenance };
}

export function getCanonicalHuman(profile: HumanProfile): CanonicalHuman {
  const normalized = normalizePhysicalProfile(profile);
  return { unit: "cm", profile: normalized, dimensions: normalized.physicalDimensions, provenance: normalized.segmentProvenance };
}

export function derivedProvenance(): Record<HumanSegmentKey, SegmentProvenance> {
  return {
    headNeck: DERIVED, torso: DERIVED, shoulderGirdle: DERIVED, pelvis: DERIVED,
    upperArm: DERIVED, forearm: DERIVED, hand: DERIVED, thigh: DERIVED,
    lowerLeg: DERIVED, foot: DERIVED,
  };
}

function finitePositive(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value > 0;
}
function clamp(value: number, minimum: number, maximum: number) {
  return Math.max(minimum, Math.min(maximum, Number.isFinite(value) ? value : 175));
}
