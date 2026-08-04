"use client";

import { Line } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";

import {
  getAnalysisRegion,
  technicalHumanPose,
  visualizationDetail,
  visualizationPalette,
  type AnalysisRegionId,
  type ModelLandmarkId,
  type Point3D,
} from "@/config/analysis-visualization";

const skeletonSegments: ReadonlyArray<
  readonly [ModelLandmarkId, ModelLandmarkId]
> = [
  ["head", "headBase"],
  ["headBase", "neck"],
  ["neck", "chest"],
  ["chest", "pelvis"],
  ["neck", "leftShoulder"],
  ["neck", "rightShoulder"],
  ["leftShoulder", "leftElbow"],
  ["leftElbow", "leftWrist"],
  ["rightShoulder", "rightElbow"],
  ["rightElbow", "rightWrist"],
  ["pelvis", "leftHip"],
  ["pelvis", "rightHip"],
  ["leftHip", "leftKnee"],
  ["leftKnee", "leftAnkle"],
  ["rightHip", "rightKnee"],
  ["rightKnee", "rightAnkle"],
];

function Landmark({
  id,
  index,
  highlighted,
  reducedMotion,
}: {
  id: ModelLandmarkId;
  index: number;
  highlighted: boolean;
  reducedMotion: boolean;
}) {
  const groupRef = useRef<THREE.Group>(null);

  useFrame((state) => {
    if (!groupRef.current) return;
    const scale = reducedMotion
      ? 1
      : THREE.MathUtils.clamp(
          (state.clock.elapsedTime - index * 0.025) * 3.4,
          0,
          1,
        );
    groupRef.current.scale.setScalar(scale);
  });

  return (
    <group ref={groupRef} position={technicalHumanPose[id]}>
      {highlighted && (
        <mesh rotation={[Math.PI / 2, 0, 0]}>
          <torusGeometry args={[0.085, 0.006, 8, 28]} />
          <meshBasicMaterial
            color={visualizationPalette.angle}
            transparent
            opacity={0.78}
            depthWrite={false}
          />
        </mesh>
      )}
      <mesh>
        <sphereGeometry args={[highlighted ? 0.045 : 0.028, 12, 12]} />
        <meshBasicMaterial
          color={
            highlighted
              ? visualizationPalette.angle
              : visualizationPalette.landmark
          }
          transparent
          opacity={highlighted ? 0.95 : 0.7}
          depthWrite={false}
        />
      </mesh>
    </group>
  );
}

function AngleIndicator({
  center,
  radius,
  startAngle,
  endAngle,
  rotation = [0, 0, 0],
}: {
  center: Point3D;
  radius: number;
  startAngle: number;
  endAngle: number;
  rotation?: Point3D;
}) {
  const points = useMemo(
    () =>
      Array.from({ length: 28 }, (_, index) => {
        const progress = index / 27;
        const angle = THREE.MathUtils.lerp(startAngle, endAngle, progress);
        return new THREE.Vector3(
          Math.cos(angle) * radius,
          Math.sin(angle) * radius,
          0,
        );
      }),
    [endAngle, radius, startAngle],
  );

  return (
    <group position={center} rotation={rotation}>
      <Line
        points={points}
        color={visualizationPalette.angle}
        lineWidth={1.25}
        transparent
        opacity={0.88}
      />
      <mesh
        position={[
          Math.cos(endAngle) * radius,
          Math.sin(endAngle) * radius,
          0,
        ]}
      >
        <sphereGeometry args={[0.018, 10, 10]} />
        <meshBasicMaterial color={visualizationPalette.angle} />
      </mesh>
    </group>
  );
}

function RegionGuide({ activeRegion }: { activeRegion: AnalysisRegionId }) {
  const guide = getAnalysisRegion(activeRegion).guide;

  if (guide === "neckAngle") {
    return (
      <AngleIndicator
        center={[0, 1.9, 0.29]}
        radius={0.23}
        startAngle={0.18}
        endAngle={1.42}
      />
    );
  }

  if (guide === "shoulderAxis") {
    return (
      <Line
        points={[
          technicalHumanPose.leftShoulder,
          technicalHumanPose.rightShoulder,
        ]}
        color={visualizationPalette.skeleton}
        lineWidth={1.25}
        transparent
        opacity={0.88}
      />
    );
  }

  if (guide === "trunkAxis") {
    return (
      <>
        <Line
          points={[
            [0, visualizationDetail.floorY, 0.03],
            [0, 2.02, 0.03],
          ]}
          color={visualizationPalette.reference}
          lineWidth={0.8}
          dashed
          dashSize={0.07}
          gapSize={0.055}
          transparent
          opacity={0.62}
        />
        <AngleIndicator
          center={[0, 0.62, 0.27]}
          radius={0.28}
          startAngle={1.22}
          endAngle={1.83}
        />
      </>
    );
  }

  if (guide === "elbowAngle") {
    return (
      <AngleIndicator
        center={[
          technicalHumanPose.rightElbow[0],
          technicalHumanPose.rightElbow[1],
          0.3,
        ]}
        radius={0.25}
        startAngle={1.78}
        endAngle={4.18}
      />
    );
  }

  if (guide === "hipAxis") {
    return (
      <Line
        points={[technicalHumanPose.leftHip, technicalHumanPose.rightHip]}
        color={visualizationPalette.skeleton}
        lineWidth={1.25}
        transparent
        opacity={0.88}
      />
    );
  }

  return (
    <>
      <AngleIndicator
        center={[
          technicalHumanPose.leftKnee[0],
          technicalHumanPose.leftKnee[1],
          0.25,
        ]}
        radius={0.21}
        startAngle={1.45}
        endAngle={2.35}
      />
      <AngleIndicator
        center={[
          technicalHumanPose.rightKnee[0],
          technicalHumanPose.rightKnee[1],
          0.25,
        ]}
        radius={0.21}
        startAngle={0.78}
        endAngle={1.67}
      />
    </>
  );
}

function Scanner({ reducedMotion }: { reducedMotion: boolean }) {
  const beamRef = useRef<THREE.Mesh>(null);

  useFrame((state) => {
    if (!beamRef.current || reducedMotion) return;
    beamRef.current.position.y =
      visualizationDetail.floorY +
      ((state.clock.elapsedTime * 0.1) % 1) *
        (technicalHumanPose.crown[1] - visualizationDetail.floorY);
  });

  return (
    <mesh
      ref={beamRef}
      position={[0, reducedMotion ? 0.48 : visualizationDetail.floorY, 0.43]}
    >
      <boxGeometry args={[2.05, 0.012, 0.012]} />
      <meshBasicMaterial
        color={visualizationPalette.skeleton}
        transparent
        opacity={0.2}
        depthWrite={false}
      />
    </mesh>
  );
}

export function BodyAnalysisOverlay({
  activeRegion,
  reducedMotion,
}: {
  activeRegion: AnalysisRegionId;
  reducedMotion: boolean;
}) {
  const activeLandmarks = getAnalysisRegion(activeRegion).activeLandmarks;

  return (
    <group>
      {skeletonSegments.map(([start, end]) => (
        <Line
          key={`${start}-${end}`}
          points={[technicalHumanPose[start], technicalHumanPose[end]]}
          color={visualizationPalette.skeleton}
          lineWidth={0.72}
          transparent
          opacity={0.44}
          depthTest={false}
        />
      ))}

      {Object.keys(technicalHumanPose).map((id, index) => (
        <Landmark
          key={id}
          id={id as ModelLandmarkId}
          index={index}
          highlighted={activeLandmarks.includes(id as ModelLandmarkId)}
          reducedMotion={reducedMotion}
        />
      ))}

      <RegionGuide activeRegion={activeRegion} />
      <Scanner reducedMotion={reducedMotion} />
    </group>
  );
}
