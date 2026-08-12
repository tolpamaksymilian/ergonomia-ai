"use client";

import { Line, RoundedBox } from "@react-three/drei";
import { useFrame, type ThreeEvent } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";

import {
  getAnalysisRegion,
  technicalHumanPose,
  technicalHumanProportions,
  visualizationPalette,
  type AnalysisRegionId,
  type ModelSegmentId,
  type Point3D,
} from "@/config/analysis-visualization";
import {
  createShellProfile,
  createTaperedProfile,
  interpolatePoint,
  segmentTransform,
} from "@/components/three/human-model/model-geometry";

type ModelPartProps = {
  activeRegion: AnalysisRegionId;
  compact: boolean;
  onRegionHover: (region: AnalysisRegionId | null) => void;
  onRegionSelect: (region: AnalysisRegionId) => void;
};

function ModelMaterial({
  active = false,
  rear = false,
  transparent = false,
}: {
  active?: boolean;
  rear?: boolean;
  transparent?: boolean;
}) {
  return (
    <meshStandardMaterial
      color={
        active
          ? visualizationPalette.bodyActive
          : rear
            ? visualizationPalette.bodyRear
            : visualizationPalette.body
      }
      emissive={
        active
          ? visualizationPalette.activeEmissive
          : visualizationPalette.bodyEmissive
      }
      emissiveIntensity={active ? 0.3 : 0.11}
      metalness={0.12}
      roughness={0.56}
      transparent={transparent}
      opacity={transparent ? 0.22 : 1}
      depthWrite={!transparent}
    />
  );
}

function getRegionHandlers(
  region: AnalysisRegionId,
  onRegionHover?: (region: AnalysisRegionId | null) => void,
  onRegionSelect?: (region: AnalysisRegionId) => void,
) {
  const stopEvent = (event: ThreeEvent<PointerEvent>) => {
    event.stopPropagation();
  };

  return {
    onClick: (event: ThreeEvent<PointerEvent>) => {
      stopEvent(event);
      onRegionSelect?.(region);
    },
    onPointerOut: (event: ThreeEvent<PointerEvent>) => {
      stopEvent(event);
      onRegionHover?.(null);
    },
    onPointerOver: (event: ThreeEvent<PointerEvent>) => {
      stopEvent(event);
      onRegionHover?.(region);
    },
  };
}

function TaperedBodyPart({
  start,
  end,
  startRadius,
  endRadius,
  radialSegments,
  active = false,
  region,
  onRegionHover,
  onRegionSelect,
  muscleBias = 0.06,
}: {
  start: Point3D;
  end: Point3D;
  startRadius: number;
  endRadius: number;
  radialSegments: number;
  active?: boolean;
  region?: AnalysisRegionId;
  onRegionHover?: (region: AnalysisRegionId | null) => void;
  onRegionSelect?: (region: AnalysisRegionId) => void;
  muscleBias?: number;
}) {
  const transform = useMemo(() => segmentTransform(start, end), [end, start]);
  const profile = useMemo(
    () =>
      createTaperedProfile(
        transform.length,
        startRadius,
        endRadius,
        muscleBias,
      ),
    [endRadius, muscleBias, startRadius, transform.length],
  );
  const handlers = region
    ? getRegionHandlers(region, onRegionHover, onRegionSelect)
    : {};

  return (
    <mesh
      position={transform.midpoint}
      quaternion={transform.quaternion}
      {...handlers}
    >
      <latheGeometry args={[profile, radialSegments]} />
      <ModelMaterial active={active} />
    </mesh>
  );
}

function ProfiledShell({
  position,
  profile,
  depthScale,
  radialSegments,
  active,
  region,
  onRegionHover,
  onRegionSelect,
  rear = false,
}: {
  position: Point3D;
  profile: ReadonlyArray<readonly [number, number]>;
  depthScale: number;
  radialSegments: number;
  active: boolean;
  region: AnalysisRegionId;
  onRegionHover: (region: AnalysisRegionId | null) => void;
  onRegionSelect: (region: AnalysisRegionId) => void;
  rear?: boolean;
}) {
  const latheProfile = useMemo(() => createShellProfile(profile), [profile]);

  return (
    <mesh
      position={position}
      scale={[1, 1, depthScale]}
      {...getRegionHandlers(region, onRegionHover, onRegionSelect)}
    >
      <latheGeometry args={[latheProfile, radialSegments]} />
      <ModelMaterial active={active} rear={rear} />
    </mesh>
  );
}

function ShoulderGirdle({
  active,
  radialSegments,
  onRegionHover,
  onRegionSelect,
}: {
  active: boolean;
  radialSegments: number;
  onRegionHover: (region: AnalysisRegionId | null) => void;
  onRegionSelect: (region: AnalysisRegionId) => void;
}) {
  const shoulderRoot: Point3D = [0, 1.61, -0.01];

  return (
    <group>
      <TaperedBodyPart
        start={shoulderRoot}
        end={technicalHumanPose.leftShoulder}
        startRadius={0.17}
        endRadius={0.13}
        radialSegments={radialSegments}
        active={active}
        region="shoulders"
        onRegionHover={onRegionHover}
        onRegionSelect={onRegionSelect}
        muscleBias={0.01}
      />
      <TaperedBodyPart
        start={shoulderRoot}
        end={technicalHumanPose.rightShoulder}
        startRadius={0.17}
        endRadius={0.13}
        radialSegments={radialSegments}
        active={active}
        region="shoulders"
        onRegionHover={onRegionHover}
        onRegionSelect={onRegionSelect}
        muscleBias={0.01}
      />
    </group>
  );
}

function Torso({
  activeRegion,
  compact,
  onRegionHover,
  onRegionSelect,
  reducedMotion,
}: ModelPartProps & { reducedMotion: boolean }) {
  const breathingRef = useRef<THREE.Group>(null);
  const activeSegments = getAnalysisRegion(activeRegion).activeSegments;
  const trunkActive = activeSegments.includes("torso");
  const pelvisActive = activeSegments.includes("pelvis");
  const shouldersActive = activeSegments.includes("shoulderGirdle");
  const radialSegments = compact ? 14 : 24;

  useFrame((state) => {
    if (!breathingRef.current || reducedMotion) return;
    const breath = Math.sin(state.clock.elapsedTime * 1.02);
    breathingRef.current.scale.y = 1 + breath * 0.0022;
    breathingRef.current.position.y = breath * 0.002;
  });

  const chestProfile = useMemo(
    () =>
      [
        [0, -0.49],
        [0.3, -0.49],
        [0.37, -0.34],
        [0.42, -0.04],
        [0.4, 0.24],
        [0.31, 0.47],
        [0, 0.47],
      ] as const,
    [],
  );
  const abdomenProfile = useMemo(
    () =>
      [
        [0, -0.29],
        [0.29, -0.29],
        [0.31, -0.12],
        [0.3, 0.14],
        [0.34, 0.29],
        [0, 0.29],
      ] as const,
    [],
  );
  const pelvisProfile = useMemo(
    () =>
      [
        [0, -0.28],
        [0.27, -0.28],
        [0.35, -0.1],
        [0.36, 0.11],
        [0.31, 0.3],
        [0, 0.3],
      ] as const,
    [],
  );

  return (
    <>
      <group ref={breathingRef}>
        <ProfiledShell
          position={[0, 1.2, 0]}
          profile={chestProfile}
          depthScale={
            technicalHumanProportions.chestDepth /
            technicalHumanProportions.chestWidth
          }
          radialSegments={radialSegments}
          active={trunkActive}
          region="trunk"
          onRegionHover={onRegionHover}
          onRegionSelect={onRegionSelect}
        />
        <ShoulderGirdle
          active={shouldersActive || activeRegion === "neck"}
          radialSegments={radialSegments}
          onRegionHover={onRegionHover}
          onRegionSelect={onRegionSelect}
        />
      </group>

      <ProfiledShell
        position={[0, 0.69, 0]}
        profile={abdomenProfile}
        depthScale={0.62}
        radialSegments={radialSegments}
        active={trunkActive}
        region="trunk"
        onRegionHover={onRegionHover}
        onRegionSelect={onRegionSelect}
      />
      <ProfiledShell
        position={[0, 0.28, 0]}
        profile={pelvisProfile}
        depthScale={
          technicalHumanProportions.pelvisDepth /
          technicalHumanProportions.pelvisWidth
        }
        radialSegments={radialSegments}
        active={pelvisActive}
        region="hips"
        onRegionHover={onRegionHover}
        onRegionSelect={onRegionSelect}
      />
    </>
  );
}

function HeadAndNeck({
  activeRegion,
  compact,
  onRegionHover,
  onRegionSelect,
}: ModelPartProps) {
  const active = activeRegion === "neck";
  const radialSegments = compact ? 14 : 24;
  const p = technicalHumanProportions;
  const neckBase: Point3D = [0, 1.62, -0.015];

  return (
    <group>
      <TaperedBodyPart
        start={neckBase}
        end={technicalHumanPose.headBase}
        startRadius={p.neckWidth * 0.64}
        endRadius={p.neckWidth * 0.5}
        radialSegments={radialSegments}
        active={active}
        region="neck"
        onRegionHover={onRegionHover}
        onRegionSelect={onRegionSelect}
        muscleBias={0}
      />

      <group
        position={technicalHumanPose.head}
        rotation={[-0.015, 0.025, 0]}
        {...getRegionHandlers("neck", onRegionHover, onRegionSelect)}
      >
        <mesh scale={[p.headWidth / 2, p.headHeight * 0.46, p.headDepth / 2]}>
          <sphereGeometry args={[1, radialSegments, radialSegments]} />
          <ModelMaterial rear />
        </mesh>
        <mesh
          position={[0, -p.headHeight * 0.27, 0.025]}
          scale={[p.headWidth * 0.39, p.headHeight * 0.23, p.headDepth * 0.42]}
        >
          <sphereGeometry args={[1, radialSegments, radialSegments]} />
          <ModelMaterial active={active} />
        </mesh>
        <RoundedBox
          args={[p.headWidth * 0.62, p.headHeight * 0.44, 0.026]}
          radius={0.035}
          smoothness={compact ? 1 : 2}
          position={[0, -0.055, p.headDepth * 0.48]}
        >
          <meshStandardMaterial
            color={active ? "#c2410c" : "#303030"}
            emissive={visualizationPalette.activeEmissive}
            emissiveIntensity={active ? 0.22 : 0.07}
            roughness={0.48}
            metalness={0.1}
          />
        </RoundedBox>
        <mesh position={[0, -0.05, p.headDepth * 0.5 + 0.016]}>
          <boxGeometry args={[0.014, p.headHeight * 0.31, 0.008]} />
          <meshBasicMaterial color="#f97316" transparent opacity={0.55} />
        </mesh>
        <Line
          points={[
            [-p.headWidth * 0.22, -p.headHeight * 0.2, p.headDepth * 0.51],
            [0, -p.headHeight * 0.3, p.headDepth * 0.52],
            [p.headWidth * 0.22, -p.headHeight * 0.2, p.headDepth * 0.51],
          ]}
          color="#f97316"
          lineWidth={0.75}
          transparent
          opacity={0.48}
        />
      </group>
    </group>
  );
}

function Arm({
  side,
  activeRegion,
  compact,
  onRegionHover,
  onRegionSelect,
}: ModelPartProps & { side: "left" | "right" }) {
  const p = technicalHumanProportions;
  const activeSegments = getAnalysisRegion(activeRegion).activeSegments;
  const upperSegment: ModelSegmentId =
    side === "left" ? "leftUpperArm" : "rightUpperArm";
  const forearmSegment: ModelSegmentId =
    side === "left" ? "leftForearm" : "rightForearm";
  const shoulder =
    side === "left"
      ? technicalHumanPose.leftShoulder
      : technicalHumanPose.rightShoulder;
  const elbow =
    side === "left" ? technicalHumanPose.leftElbow : technicalHumanPose.rightElbow;
  const wrist =
    side === "left" ? technicalHumanPose.leftWrist : technicalHumanPose.rightWrist;
  const hand =
    side === "left" ? technicalHumanPose.leftHand : technicalHumanPose.rightHand;
  const forearmRegion: AnalysisRegionId =
    side === "right" ? "rightElbow" : "shoulders";
  const radialSegments = compact ? 12 : 20;

  return (
    <group>
      <TaperedBodyPart
        start={shoulder}
        end={elbow}
        startRadius={p.segmentRadii.upperArm[0]}
        endRadius={p.segmentRadii.upperArm[1]}
        radialSegments={radialSegments}
        active={activeSegments.includes(upperSegment)}
        region="shoulders"
        onRegionHover={onRegionHover}
        onRegionSelect={onRegionSelect}
        muscleBias={0.075}
      />
      <TaperedBodyPart
        start={elbow}
        end={wrist}
        startRadius={p.segmentRadii.forearm[0]}
        endRadius={p.segmentRadii.forearm[1]}
        radialSegments={radialSegments}
        active={activeSegments.includes(forearmSegment)}
        region={forearmRegion}
        onRegionHover={onRegionHover}
        onRegionSelect={onRegionSelect}
        muscleBias={0.12}
      />
      <TaperedBodyPart
        start={wrist}
        end={[hand[0], hand[1] + p.palmLength * 0.5, hand[2]]}
        startRadius={p.segmentRadii.forearm[1] * 0.9}
        endRadius={p.palmWidth * 0.38}
        radialSegments={radialSegments}
        active={activeSegments.includes(forearmSegment)}
        region={forearmRegion}
        onRegionHover={onRegionHover}
        onRegionSelect={onRegionSelect}
        muscleBias={0}
      />
      <Hand side={side} compact={compact} />
    </group>
  );
}

function FingerSegment({
  start,
  end,
  radius,
  radialSegments,
}: {
  start: Point3D;
  end: Point3D;
  radius: number;
  radialSegments: number;
}) {
  return (
    <TaperedBodyPart
      start={start}
      end={end}
      startRadius={radius}
      endRadius={radius * 0.72}
      radialSegments={radialSegments}
      muscleBias={0}
    />
  );
}

function Hand({ side, compact }: { side: "left" | "right"; compact: boolean }) {
  const p = technicalHumanProportions;
  const palm =
    side === "left" ? technicalHumanPose.leftHand : technicalHumanPose.rightHand;
  const sign = side === "left" ? -1 : 1;
  const fingerLengths = [0.15, 0.175, 0.16, 0.13] as const;
  const fingerOffsets = [-0.052, -0.017, 0.018, 0.052] as const;
  const radialSegments = compact ? 7 : 10;

  return (
    <group position={palm} rotation={[0.035, sign * -0.05, sign * -0.035]}>
      <RoundedBox
        args={[p.palmWidth, p.palmLength, 0.075]}
        radius={0.035}
        smoothness={compact ? 1 : 2}
      >
        <ModelMaterial />
      </RoundedBox>

      {fingerLengths.map((length, index) => {
        const x = fingerOffsets[index];
        const baseY = -p.palmLength * 0.5;
        const middleY = baseY - length * 0.54;
        const tipY = baseY - length;
        const middle: Point3D = [x, middleY, 0.012];
        const tip: Point3D = [x + sign * 0.006, tipY, 0.035];

        if (compact) {
          return (
            <FingerSegment
              key={x}
              start={[x, baseY, 0]}
              end={tip}
              radius={index === 3 ? 0.018 : 0.021}
              radialSegments={radialSegments}
            />
          );
        }

        return (
          <group key={x}>
            <FingerSegment
              start={[x, baseY, 0]}
              end={middle}
              radius={index === 3 ? 0.018 : 0.021}
              radialSegments={radialSegments}
            />
            <FingerSegment
              start={middle}
              end={tip}
              radius={index === 3 ? 0.016 : 0.0185}
              radialSegments={radialSegments}
            />
          </group>
        );
      })}

      <FingerSegment
        start={[sign * p.palmWidth * 0.46, 0.025, 0.012]}
        end={[sign * (p.palmWidth * 0.82), -0.045, 0.045]}
        radius={0.025}
        radialSegments={radialSegments}
      />
      {!compact && (
        <FingerSegment
          start={[sign * (p.palmWidth * 0.82), -0.045, 0.045]}
          end={[sign * (p.palmWidth * 0.98), -0.105, 0.065]}
          radius={0.021}
          radialSegments={radialSegments}
        />
      )}
    </group>
  );
}

function Leg({
  side,
  activeRegion,
  compact,
  onRegionHover,
  onRegionSelect,
}: ModelPartProps & { side: "left" | "right" }) {
  const p = technicalHumanProportions;
  const activeSegments = getAnalysisRegion(activeRegion).activeSegments;
  const thighSegment: ModelSegmentId =
    side === "left" ? "leftThigh" : "rightThigh";
  const hip =
    side === "left" ? technicalHumanPose.leftHip : technicalHumanPose.rightHip;
  const knee =
    side === "left" ? technicalHumanPose.leftKnee : technicalHumanPose.rightKnee;
  const ankle =
    side === "left" ? technicalHumanPose.leftAnkle : technicalHumanPose.rightAnkle;
  const radialSegments = compact ? 12 : 20;
  const kneesActive = activeRegion === "knees";
  const lowerThigh = interpolatePoint(hip, knee, 0.74);
  const upperShin = interpolatePoint(knee, ankle, 0.25);

  return (
    <group>
      <TaperedBodyPart
        start={hip}
        end={knee}
        startRadius={p.segmentRadii.thigh[0]}
        endRadius={p.segmentRadii.thigh[1]}
        radialSegments={radialSegments}
        active={activeRegion === "hips" && activeSegments.includes(thighSegment)}
        region="hips"
        onRegionHover={onRegionHover}
        onRegionSelect={onRegionSelect}
        muscleBias={0.08}
      />
      <TaperedBodyPart
        start={knee}
        end={ankle}
        startRadius={p.segmentRadii.shin[0]}
        endRadius={p.segmentRadii.shin[1]}
        radialSegments={radialSegments}
        active={false}
        region="knees"
        onRegionHover={onRegionHover}
        onRegionSelect={onRegionSelect}
        muscleBias={0.1}
      />
      {kneesActive && (
        <>
          <TaperedBodyPart
            start={lowerThigh}
            end={knee}
            startRadius={p.segmentRadii.thigh[1] * 1.03}
            endRadius={p.segmentRadii.thigh[1] * 1.04}
            radialSegments={radialSegments}
            active
            muscleBias={0}
          />
          <TaperedBodyPart
            start={knee}
            end={upperShin}
            startRadius={p.segmentRadii.shin[0] * 1.04}
            endRadius={p.segmentRadii.shin[0] * 0.96}
            radialSegments={radialSegments}
            active
            muscleBias={0}
          />
        </>
      )}
      <Foot side={side} compact={compact} />
    </group>
  );
}

function Foot({ side, compact }: { side: "left" | "right"; compact: boolean }) {
  const p = technicalHumanProportions;
  const position =
    side === "left" ? technicalHumanPose.leftFoot : technicalHumanPose.rightFoot;
  const turn = side === "left" ? -0.11 : 0.11;
  const smoothness = compact ? 1 : 2;

  return (
    <group position={position} rotation={[0, turn, 0]}>
      <RoundedBox
        args={[p.footWidth * 0.72, 0.15, p.footLength * 0.27]}
        radius={0.045}
        smoothness={smoothness}
        position={[0, 0.015, -p.footLength * 0.2]}
      >
        <ModelMaterial />
      </RoundedBox>
      <RoundedBox
        args={[p.footWidth * 0.84, 0.13, p.footLength * 0.42]}
        radius={0.04}
        smoothness={smoothness}
        position={[0, -0.005, 0.015]}
      >
        <ModelMaterial />
      </RoundedBox>
      <RoundedBox
        args={[p.footWidth, 0.105, p.footLength * 0.42]}
        radius={0.045}
        smoothness={smoothness}
        position={[0, -0.018, p.footLength * 0.23]}
      >
        <ModelMaterial />
      </RoundedBox>
    </group>
  );
}

export function TechnicalHumanModel({
  activeRegion,
  compact,
  onRegionHover,
  onRegionSelect,
  reducedMotion,
}: ModelPartProps & { reducedMotion: boolean }) {
  const modelRef = useRef<THREE.Group>(null);

  useFrame((state, delta) => {
    if (!modelRef.current || reducedMotion) return;
    modelRef.current.rotation.y = THREE.MathUtils.damp(
      modelRef.current.rotation.y,
      state.pointer.x * 0.038,
      4,
      delta,
    );
  });

  return (
    <group ref={modelRef}>
      <Torso
        activeRegion={activeRegion}
        compact={compact}
        onRegionHover={onRegionHover}
        onRegionSelect={onRegionSelect}
        reducedMotion={reducedMotion}
      />
      <HeadAndNeck
        activeRegion={activeRegion}
        compact={compact}
        onRegionHover={onRegionHover}
        onRegionSelect={onRegionSelect}
      />
      <Arm
        side="left"
        activeRegion={activeRegion}
        compact={compact}
        onRegionHover={onRegionHover}
        onRegionSelect={onRegionSelect}
      />
      <Arm
        side="right"
        activeRegion={activeRegion}
        compact={compact}
        onRegionHover={onRegionHover}
        onRegionSelect={onRegionSelect}
      />
      <Leg
        side="left"
        activeRegion={activeRegion}
        compact={compact}
        onRegionHover={onRegionHover}
        onRegionSelect={onRegionSelect}
      />
      <Leg
        side="right"
        activeRegion={activeRegion}
        compact={compact}
        onRegionHover={onRegionHover}
        onRegionSelect={onRegionSelect}
      />
    </group>
  );
}
