"use client";

import { ContactShadows, Line, Sparkles } from "@react-three/drei";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";

import { ModelFallback } from "@/components/landing/model-fallback";
import type {
  AnalysisFocusMode,
  AnalysisRegionId,
} from "@/config/analysis-visualization";

type ErgonomicSkeletonProps = {
  activeRegion: AnalysisRegionId;
  focusMode?: AnalysisFocusMode;
  onRegionChange?: (region: AnalysisRegionId) => void;
  reducedMotion?: boolean;
};

type Point3D = [number, number, number];

const joints = {
  crown: [0.08, 2.72, 0.02],
  head: [0.07, 2.42, 0.04],
  neck: [0.03, 1.98, 0.01],
  chest: [0.02, 1.42, 0.03],
  pelvis: [-0.03, 0.42, 0.03],
  leftShoulder: [-0.59, 1.78, -0.01],
  rightShoulder: [0.63, 1.76, 0.04],
  leftElbow: [-0.95, 1.02, 0.2],
  rightElbow: [1.0, 1.08, 0.2],
  leftWrist: [-0.76, 0.29, 0.35],
  rightWrist: [1.22, 0.43, 0.4],
  leftHand: [-0.69, 0.03, 0.38],
  rightHand: [1.32, 0.18, 0.45],
  leftHip: [-0.32, 0.35, 0.01],
  rightHip: [0.28, 0.38, 0.05],
  leftKnee: [-0.39, -0.82, 0.15],
  rightKnee: [0.42, -0.78, -0.02],
  leftAnkle: [-0.42, -1.91, 0.02],
  rightAnkle: [0.48, -1.91, 0.11],
  leftFoot: [-0.36, -2.08, 0.4],
  rightFoot: [0.61, -2.08, 0.48],
} as const satisfies Record<string, Point3D>;

type JointName = keyof typeof joints;

const skeletonSegments: ReadonlyArray<readonly [JointName, JointName]> = [
  ["crown", "head"],
  ["head", "neck"],
  ["neck", "chest"],
  ["chest", "pelvis"],
  ["neck", "leftShoulder"],
  ["neck", "rightShoulder"],
  ["leftShoulder", "leftElbow"],
  ["leftElbow", "leftWrist"],
  ["leftWrist", "leftHand"],
  ["rightShoulder", "rightElbow"],
  ["rightElbow", "rightWrist"],
  ["rightWrist", "rightHand"],
  ["pelvis", "leftHip"],
  ["pelvis", "rightHip"],
  ["leftHip", "rightHip"],
  ["leftHip", "leftKnee"],
  ["leftKnee", "leftAnkle"],
  ["leftAnkle", "leftFoot"],
  ["rightHip", "rightKnee"],
  ["rightKnee", "rightAnkle"],
  ["rightAnkle", "rightFoot"],
];

const bodySegments: ReadonlyArray<{
  start: JointName;
  end: JointName;
  startRadius: number;
  endRadius: number;
  region: AnalysisRegionId;
}> = [
  { start: "neck", end: "leftShoulder", startRadius: 0.16, endRadius: 0.18, region: "shoulders" },
  { start: "neck", end: "rightShoulder", startRadius: 0.16, endRadius: 0.18, region: "shoulders" },
  { start: "leftShoulder", end: "leftElbow", startRadius: 0.16, endRadius: 0.125, region: "shoulders" },
  { start: "leftElbow", end: "leftWrist", startRadius: 0.125, endRadius: 0.09, region: "shoulders" },
  { start: "rightShoulder", end: "rightElbow", startRadius: 0.17, endRadius: 0.13, region: "rightElbow" },
  { start: "rightElbow", end: "rightWrist", startRadius: 0.13, endRadius: 0.09, region: "rightElbow" },
  { start: "leftHip", end: "leftKnee", startRadius: 0.2, endRadius: 0.16, region: "hips" },
  { start: "leftKnee", end: "leftAnkle", startRadius: 0.155, endRadius: 0.105, region: "knees" },
  { start: "rightHip", end: "rightKnee", startRadius: 0.2, endRadius: 0.16, region: "hips" },
  { start: "rightKnee", end: "rightAnkle", startRadius: 0.155, endRadius: 0.105, region: "knees" },
];

function segmentTransform(start: Point3D, end: Point3D) {
  const startVector = new THREE.Vector3(...start);
  const endVector = new THREE.Vector3(...end);
  const direction = new THREE.Vector3().subVectors(endVector, startVector);
  const midpoint = new THREE.Vector3().addVectors(startVector, endVector).multiplyScalar(0.5);
  const quaternion = new THREE.Quaternion().setFromUnitVectors(
    new THREE.Vector3(0, 1, 0),
    direction.clone().normalize(),
  );

  return { midpoint, quaternion, length: direction.length() };
}

function CameraRig({
  focusMode,
  reducedMotion,
}: {
  focusMode: AnalysisFocusMode;
  reducedMotion: boolean;
}) {
  const { size } = useThree();
  const targetRef = useRef(new THREE.Vector3(0, 0.35, 0));

  useFrame((state, delta) => {
    const compact = size.width < 520;
    const focusMap: Record<AnalysisFocusMode, { position: Point3D; target: Point3D }> = {
      full: {
        position: [0, compact ? 0.38 : 0.18, compact ? 8.3 : 7.25],
        target: [0, 0.32, 0],
      },
      upper: {
        position: [0.04, 1.22, compact ? 6.15 : 5.05],
        target: [0.02, 1.2, 0.03],
      },
      arm: {
        position: [1.45, 1.05, compact ? 4.9 : 3.75],
        target: [0.86, 0.98, 0.12],
      },
    };
    const current = focusMap[focusMode];
    const pointerX = reducedMotion ? 0 : state.pointer.x * 0.16;
    const pointerY = reducedMotion ? 0 : state.pointer.y * 0.09;
    const desiredPosition = new THREE.Vector3(
      current.position[0] + pointerX,
      current.position[1] - pointerY,
      current.position[2],
    );
    const desiredTarget = new THREE.Vector3(
      current.target[0],
      current.target[1] - pointerY * 0.55,
      current.target[2],
    );

    if (reducedMotion) {
      state.camera.position.copy(desiredPosition);
      targetRef.current.copy(desiredTarget);
    } else {
      const ease = 1 - Math.exp(-delta * 4.2);
      state.camera.position.lerp(desiredPosition, ease);
      targetRef.current.lerp(desiredTarget, ease);
    }
    state.camera.lookAt(targetRef.current);
  });

  return null;
}

function SurfaceMaterial({ active = false, rear = false }: { active?: boolean; rear?: boolean }) {
  return (
    <meshPhysicalMaterial
      color={active ? "#176b78" : rear ? "#082635" : "#0d4558"}
      emissive={active ? "#0891b2" : "#063241"}
      emissiveIntensity={active ? 0.55 : 0.16}
      metalness={0.28}
      roughness={0.38}
      clearcoat={0.42}
      clearcoatRoughness={0.34}
    />
  );
}

function BodyCapsule({
  start,
  end,
  startRadius,
  endRadius,
  region,
  activeRegion,
  onRegionChange,
}: {
  start: Point3D;
  end: Point3D;
  startRadius: number;
  endRadius: number;
  region: AnalysisRegionId;
  activeRegion: AnalysisRegionId;
  onRegionChange: (region: AnalysisRegionId) => void;
}) {
  const transform = useMemo(() => segmentTransform(start, end), [start, end]);
  const active = activeRegion === region;

  return (
    <group position={transform.midpoint} quaternion={transform.quaternion}>
      <mesh
        scale={[1, 1, endRadius / startRadius]}
        onPointerOver={(event) => {
          event.stopPropagation();
          onRegionChange(region);
        }}
      >
        <capsuleGeometry
          args={[
            startRadius,
            Math.max(0.03, transform.length - startRadius * 2),
            8,
            20,
          ]}
        />
        <SurfaceMaterial active={active} />
      </mesh>
      {active && (
        <mesh scale={[1.18, 1.04, 1.18]}>
          <capsuleGeometry
            args={[
              startRadius,
              Math.max(0.03, transform.length - startRadius * 2),
              6,
              18,
            ]}
          />
          <meshBasicMaterial color="#22d3ee" transparent opacity={0.07} depthWrite={false} />
        </mesh>
      )}
    </group>
  );
}

function AnatomicalCore({
  activeRegion,
  onRegionChange,
}: {
  activeRegion: AnalysisRegionId;
  onRegionChange: (region: AnalysisRegionId) => void;
}) {
  const interactive = (region: AnalysisRegionId) => ({
    onPointerOver: (event: { stopPropagation: () => void }) => {
      event.stopPropagation();
      onRegionChange(region);
    },
  });

  return (
    <>
      <mesh
        position={[0.01, 1.35, -0.04]}
        scale={[1, 1.08, 0.58]}
        {...interactive("trunk")}
      >
        <sphereGeometry args={[0.62, 28, 28]} />
        <SurfaceMaterial active={activeRegion === "trunk"} rear />
      </mesh>
      <mesh
        position={[0.03, 1.37, 0.06]}
        scale={[0.96, 1.02, 0.49]}
        {...interactive("trunk")}
      >
        <sphereGeometry args={[0.6, 32, 32]} />
        <SurfaceMaterial active={activeRegion === "trunk"} />
      </mesh>
      <mesh
        position={[-0.01, 0.78, 0.015]}
        scale={[0.92, 1.08, 0.58]}
        {...interactive("trunk")}
      >
        <capsuleGeometry args={[0.36, 0.3, 8, 24]} />
        <SurfaceMaterial active={activeRegion === "trunk"} />
      </mesh>
      <mesh
        position={[-0.03, 0.38, 0.02]}
        scale={[1.05, 0.7, 0.67]}
        {...interactive("hips")}
      >
        <sphereGeometry args={[0.46, 28, 28]} />
        <SurfaceMaterial active={activeRegion === "hips"} />
      </mesh>
      <mesh position={[0.04, 1.41, 0.355]} scale={[0.16, 0.76, 0.05]}>
        <capsuleGeometry args={[0.08, 0.42, 6, 16]} />
        <meshStandardMaterial color="#38bdf8" emissive="#0891b2" emissiveIntensity={0.38} roughness={0.3} />
      </mesh>
    </>
  );
}

function HeadAndNeck({
  activeRegion,
  onRegionChange,
}: {
  activeRegion: AnalysisRegionId;
  onRegionChange: (region: AnalysisRegionId) => void;
}) {
  const active = activeRegion === "neck";
  const selectNeck = (event: { stopPropagation: () => void }) => {
    event.stopPropagation();
    onRegionChange("neck");
  };

  return (
    <>
      <mesh position={[0.04, 2.02, 0]} scale={[0.78, 1, 0.76]} onPointerOver={selectNeck}>
        <capsuleGeometry args={[0.15, 0.22, 8, 20]} />
        <SurfaceMaterial active={active} />
      </mesh>
      <group position={joints.head} rotation={[-0.035, 0.04, -0.02]}>
        <mesh scale={[0.84, 1, 0.82]} onPointerOver={selectNeck}>
          <sphereGeometry args={[0.32, 32, 32]} />
          <SurfaceMaterial active={active} rear />
        </mesh>
        <mesh position={[0, -0.09, 0.055]} scale={[0.74, 0.72, 0.72]} onPointerOver={selectNeck}>
          <sphereGeometry args={[0.31, 28, 28]} />
          <SurfaceMaterial active={active} />
        </mesh>
        <mesh position={[0.025, -0.02, 0.27]} rotation={[Math.PI / 2, 0, 0]} scale={[0.5, 0.62, 0.48]}>
          <coneGeometry args={[0.065, 0.16, 18]} />
          <meshStandardMaterial color="#155e75" roughness={0.42} />
        </mesh>
        <mesh position={[0, -0.18, 0.235]} scale={[0.36, 0.04, 0.04]}>
          <sphereGeometry args={[0.22, 18, 18]} />
          <meshBasicMaterial color="#67e8f9" transparent opacity={0.42} />
        </mesh>
      </group>
    </>
  );
}

function Foot({ side, active }: { side: "left" | "right"; active: boolean }) {
  const position = side === "left" ? joints.leftFoot : joints.rightFoot;
  const rotationY = side === "left" ? -0.09 : 0.13;

  return (
    <mesh position={position} rotation={[0.04, rotationY, 0]} scale={[0.16, 0.11, 0.36]}>
      <capsuleGeometry args={[0.42, 0.42, 8, 20]} />
      <SurfaceMaterial active={active} />
    </mesh>
  );
}

function Hand({ side }: { side: "left" | "right" }) {
  const palm = side === "left" ? joints.leftHand : joints.rightHand;
  const sign = side === "left" ? -1 : 1;
  const fingerOffsets = [-0.07, -0.025, 0.02, 0.064];

  return (
    <group>
      <mesh position={palm} rotation={[0.05, 0, sign * -0.12]} scale={[0.12, 0.19, 0.07]}>
        <sphereGeometry args={[1, 20, 20]} />
        <SurfaceMaterial />
      </mesh>
      {fingerOffsets.map((offset, index) => {
        const start: Point3D = [palm[0] + offset, palm[1] - 0.1, palm[2] + 0.015];
        const length = 0.16 + (index === 1 || index === 2 ? 0.035 : 0);
        const end: Point3D = [start[0] + sign * 0.018, start[1] - length, start[2] + 0.018];
        const transform = segmentTransform(start, end);

        return (
          <mesh key={offset} position={transform.midpoint} quaternion={transform.quaternion}>
            <capsuleGeometry args={[0.025, Math.max(0.05, transform.length - 0.05), 5, 10]} />
            <SurfaceMaterial />
          </mesh>
        );
      })}
      {(() => {
        const start: Point3D = [palm[0] + sign * 0.08, palm[1] - 0.015, palm[2] + 0.02];
        const end: Point3D = [palm[0] + sign * 0.17, palm[1] - 0.1, palm[2] + 0.07];
        const transform = segmentTransform(start, end);
        return (
          <mesh position={transform.midpoint} quaternion={transform.quaternion}>
            <capsuleGeometry args={[0.028, Math.max(0.05, transform.length - 0.056), 5, 10]} />
            <SurfaceMaterial />
          </mesh>
        );
      })()}
    </group>
  );
}

function SkeletonTube({ start, end }: { start: Point3D; end: Point3D }) {
  const transform = useMemo(() => segmentTransform(start, end), [start, end]);

  return (
    <group position={transform.midpoint} quaternion={transform.quaternion}>
      <mesh>
        <cylinderGeometry args={[0.025, 0.025, transform.length, 12]} />
        <meshBasicMaterial color="#a5f3fc" transparent opacity={0.72} depthWrite={false} />
      </mesh>
      <mesh>
        <cylinderGeometry args={[0.052, 0.052, transform.length, 12]} />
        <meshBasicMaterial color="#22d3ee" transparent opacity={0.045} depthWrite={false} />
      </mesh>
    </group>
  );
}

function JointNode({
  name,
  position,
  index,
  highlighted,
  reducedMotion,
}: {
  name: JointName;
  position: Point3D;
  index: number;
  highlighted: boolean;
  reducedMotion: boolean;
}) {
  const groupRef = useRef<THREE.Group>(null);

  useFrame((state) => {
    if (!groupRef.current) return;
    const target = reducedMotion
      ? 1
      : THREE.MathUtils.clamp((state.clock.elapsedTime - index * 0.035) * 3.2, 0, 1);
    groupRef.current.scale.setScalar(target);
  });

  const major = ["neck", "leftShoulder", "rightShoulder", "rightElbow", "pelvis", "leftKnee", "rightKnee"].includes(name);

  return (
    <group ref={groupRef} position={position}>
      {highlighted && (
        <mesh rotation={[Math.PI / 2, 0, 0]}>
          <torusGeometry args={[major ? 0.13 : 0.1, 0.009, 8, 36]} />
          <meshBasicMaterial color="#fbbf24" transparent opacity={0.8} depthWrite={false} />
        </mesh>
      )}
      <mesh>
        <sphereGeometry args={[major ? 0.064 : 0.048, 16, 16]} />
        <meshStandardMaterial
          color={highlighted ? "#fde68a" : "#cffafe"}
          emissive={highlighted ? "#f59e0b" : "#06b6d4"}
          emissiveIntensity={highlighted ? 1.5 : 0.9}
          roughness={0.2}
        />
      </mesh>
    </group>
  );
}

function AngleArc({
  center,
  radius,
  startAngle,
  endAngle,
  color,
  rotation = [0, 0, 0],
}: {
  center: Point3D;
  radius: number;
  startAngle: number;
  endAngle: number;
  color: string;
  rotation?: Point3D;
}) {
  const points = useMemo(
    () =>
      Array.from({ length: 34 }, (_, index) => {
        const progress = index / 33;
        const angle = startAngle + (endAngle - startAngle) * progress;
        return new THREE.Vector3(Math.cos(angle) * radius, Math.sin(angle) * radius, 0);
      }),
    [endAngle, radius, startAngle],
  );

  return (
    <group position={center} rotation={rotation}>
      <Line points={points} color={color} lineWidth={1.35} transparent opacity={0.86} />
      <mesh position={[Math.cos(endAngle) * radius, Math.sin(endAngle) * radius, 0]}>
        <sphereGeometry args={[0.024, 12, 12]} />
        <meshBasicMaterial color={color} />
      </mesh>
    </group>
  );
}

function AnalysisGuides({
  activeRegion,
  reducedMotion,
}: {
  activeRegion: AnalysisRegionId;
  reducedMotion: boolean;
}) {
  const boxColor = "#164e63";
  const highlightedJoints: Partial<Record<AnalysisRegionId, JointName[]>> = {
    neck: ["head", "neck", "leftShoulder", "rightShoulder"],
    shoulders: ["leftShoulder", "rightShoulder", "leftElbow", "rightElbow"],
    trunk: ["neck", "chest", "pelvis"],
    rightElbow: ["rightShoulder", "rightElbow", "rightWrist"],
    hips: ["pelvis", "leftHip", "rightHip"],
    knees: ["leftKnee", "rightKnee", "leftAnkle", "rightAnkle"],
  };

  return (
    <>
      <Line points={[[0, -2.16, 0.02], [0.03, 2.9, 0.02]]} color="#34d399" lineWidth={0.8} dashed dashSize={0.08} gapSize={0.06} transparent opacity={0.48} />
      <Line points={[joints.leftShoulder, joints.rightShoulder]} color="#67e8f9" lineWidth={1} transparent opacity={0.55} />
      <Line points={[joints.leftHip, joints.rightHip]} color="#67e8f9" lineWidth={1} transparent opacity={0.5} />
      <Line points={[[-1.3, 1.76, -0.08], [1.38, 1.76, -0.08]]} color="#155e75" lineWidth={0.7} dashed dashSize={0.07} gapSize={0.05} transparent opacity={0.5} />
      <Line points={[[-1.25, 0.4, -0.08], [1.25, 0.4, -0.08]]} color="#155e75" lineWidth={0.7} dashed dashSize={0.07} gapSize={0.05} transparent opacity={0.45} />

      {[
        [[-1.55, -2.14, -0.2], [-1.55, 2.88, -0.2]],
        [[1.58, -2.14, -0.2], [1.58, 2.88, -0.2]],
        [[-1.55, 2.88, -0.2], [1.58, 2.88, -0.2]],
        [[-1.55, -2.14, -0.2], [1.58, -2.14, -0.2]],
      ].map((points, index) => (
        <Line key={index} points={points as [Point3D, Point3D]} color={boxColor} lineWidth={0.8} transparent opacity={0.46} />
      ))}

      <AngleArc center={joints.neck} radius={0.28} startAngle={0.08} endAngle={1.34} color={activeRegion === "neck" ? "#fbbf24" : "#34d399"} />
      <AngleArc center={joints.rightElbow} radius={0.32} startAngle={1.8} endAngle={4.3} color={activeRegion === "rightElbow" ? "#fbbf24" : "#22d3ee"} />
      <AngleArc center={[-0.01, 0.78, 0.3]} radius={0.34} startAngle={1.18} endAngle={1.9} color={activeRegion === "trunk" ? "#fbbf24" : "#22d3ee"} />

      {Object.entries(joints).map(([name, position], index) => (
        <JointNode
          key={name}
          name={name as JointName}
          position={position}
          index={index}
          highlighted={(highlightedJoints[activeRegion] ?? []).includes(name as JointName)}
          reducedMotion={reducedMotion}
        />
      ))}
    </>
  );
}

function Scanner({ reducedMotion }: { reducedMotion: boolean }) {
  const beamRef = useRef<THREE.Mesh>(null);
  const ringRef = useRef<THREE.Mesh>(null);

  useFrame((state) => {
    if (reducedMotion) return;
    const elapsed = state.clock.elapsedTime;
    if (beamRef.current) beamRef.current.position.y = -2.02 + ((elapsed * 0.15) % 1) * 4.8;
    if (ringRef.current) {
      const scale = 1 + Math.sin(elapsed * 1.1) * 0.035;
      ringRef.current.scale.setScalar(scale);
    }
  });

  return (
    <>
      <mesh ref={beamRef} position={[0, reducedMotion ? 0.45 : -2.02, 0.55]}>
        <boxGeometry args={[3.18, 0.018, 0.018]} />
        <meshBasicMaterial color="#67e8f9" transparent opacity={0.55} depthWrite={false} />
      </mesh>
      <group position={[0, -2.14, 0.08]} rotation={[-Math.PI / 2, 0, 0]}>
        <mesh ref={ringRef}>
          <ringGeometry args={[0.92, 0.95, 56]} />
          <meshBasicMaterial color="#22d3ee" transparent opacity={0.38} side={THREE.DoubleSide} />
        </mesh>
        <mesh>
          <ringGeometry args={[1.3, 1.32, 56]} />
          <meshBasicMaterial color="#10b981" transparent opacity={0.15} side={THREE.DoubleSide} />
        </mesh>
      </group>
    </>
  );
}

function IndustrialEnvironment({ compact }: { compact: boolean }) {
  return (
    <group position={[0, 0, -1.15]}>
      <mesh position={[-2.25, 0.25, 0]}>
        <boxGeometry args={[0.08, 5.25, 0.12]} />
        <meshStandardMaterial color="#102635" metalness={0.55} roughness={0.5} />
      </mesh>
      <mesh position={[2.25, 0.25, 0]}>
        <boxGeometry args={[0.08, 5.25, 0.12]} />
        <meshStandardMaterial color="#102635" metalness={0.55} roughness={0.5} />
      </mesh>
      {[-1.45, 0.2, 1.85].map((height) => (
        <mesh key={height} position={[0, height, 0]}>
          <boxGeometry args={[4.55, 0.055, 0.1]} />
          <meshStandardMaterial color="#123244" metalness={0.5} roughness={0.48} />
        </mesh>
      ))}
      {!compact && (
        <>
          <mesh position={[-1.75, 1.14, 0.08]}>
            <boxGeometry args={[0.54, 0.78, 0.05]} />
            <meshStandardMaterial color="#0a1d2a" emissive="#0e7490" emissiveIntensity={0.12} />
          </mesh>
          {[0.98, 1.14, 1.3].map((height) => (
            <mesh key={height} position={[-1.75, height, 0.12]}>
              <boxGeometry args={[0.36, 0.018, 0.02]} />
              <meshBasicMaterial color="#22d3ee" transparent opacity={0.38} />
            </mesh>
          ))}
        </>
      )}
    </group>
  );
}

function DigitalHuman({
  activeRegion,
  onRegionChange,
  reducedMotion,
}: {
  activeRegion: AnalysisRegionId;
  onRegionChange: (region: AnalysisRegionId) => void;
  reducedMotion: boolean;
}) {
  const groupRef = useRef<THREE.Group>(null);

  useFrame((state, delta) => {
    if (!groupRef.current || reducedMotion) return;
    const elapsed = state.clock.elapsedTime;
    groupRef.current.rotation.y = THREE.MathUtils.damp(groupRef.current.rotation.y, state.pointer.x * 0.1, 4.2, delta);
    groupRef.current.rotation.x = THREE.MathUtils.damp(groupRef.current.rotation.x, -state.pointer.y * 0.025, 4.2, delta);
    groupRef.current.position.y = Math.sin(elapsed * 1.08) * 0.008;
    groupRef.current.scale.y = 1 + Math.sin(elapsed * 1.08) * 0.0025;
  });

  return (
    <group ref={groupRef} position={[0, 0, 0]}>
      <AnatomicalCore activeRegion={activeRegion} onRegionChange={onRegionChange} />
      <HeadAndNeck activeRegion={activeRegion} onRegionChange={onRegionChange} />
      {bodySegments.map((segment) => (
        <BodyCapsule
          key={`${segment.start}-${segment.end}`}
          start={joints[segment.start]}
          end={joints[segment.end]}
          startRadius={segment.startRadius}
          endRadius={segment.endRadius}
          region={segment.region}
          activeRegion={activeRegion}
          onRegionChange={onRegionChange}
        />
      ))}
      <Hand side="left" />
      <Hand side="right" />
      <Foot side="left" active={activeRegion === "knees"} />
      <Foot side="right" active={activeRegion === "knees"} />

      {skeletonSegments.map(([start, end]) => (
        <SkeletonTube key={`${start}-${end}`} start={joints[start]} end={joints[end]} />
      ))}
      <AnalysisGuides activeRegion={activeRegion} reducedMotion={reducedMotion} />
      <Scanner reducedMotion={reducedMotion} />
    </group>
  );
}

function Scene({
  activeRegion,
  focusMode,
  onRegionChange,
  reducedMotion,
}: {
  activeRegion: AnalysisRegionId;
  focusMode: AnalysisFocusMode;
  onRegionChange: (region: AnalysisRegionId) => void;
  reducedMotion: boolean;
}) {
  const { size } = useThree();
  const compact = size.width < 520;

  return (
    <>
      <fog attach="fog" args={["#07111f", 7, 13]} />
      <CameraRig focusMode={focusMode} reducedMotion={reducedMotion} />
      <ambientLight intensity={0.78} />
      <directionalLight position={[4, 6, 5]} intensity={2.7} color="#d8fff7" />
      <pointLight position={[-3.4, 1.8, 3]} intensity={20} color="#06b6d4" distance={11} />
      <pointLight position={[3.2, -0.7, 2.8]} intensity={15} color="#10b981" distance={10} />
      <pointLight position={[0, 3.1, -1]} intensity={10} color="#38bdf8" distance={8} />
      {!reducedMotion && (
        <Sparkles
          count={compact ? 14 : 32}
          scale={[5, 5.6, 3]}
          size={compact ? 0.9 : 1.25}
          speed={0.12}
          opacity={0.2}
          color="#67e8f9"
        />
      )}
      <IndustrialEnvironment compact={compact} />
      <gridHelper args={[8, compact ? 14 : 22, "#155e75", "#0f2535"]} position={[0, -2.16, 0]} />
      <DigitalHuman activeRegion={activeRegion} onRegionChange={onRegionChange} reducedMotion={reducedMotion} />
      <ContactShadows position={[0, -2.15, 0]} opacity={0.48} scale={5} blur={2.4} far={4} color="#020617" />
    </>
  );
}

export function ErgonomicSkeleton({
  activeRegion,
  focusMode = "full",
  onRegionChange = () => undefined,
  reducedMotion = false,
}: ErgonomicSkeletonProps) {
  return (
    <div className="h-[430px] w-full sm:h-[540px]">
      <Canvas
        aria-label="Interaktywna techniczna wizualizacja analizy pozy pracownika"
        role="img"
        dpr={[1, 1.35]}
        frameloop={reducedMotion ? "demand" : "always"}
        camera={{ position: [0, 0.18, 7.25], fov: 41, near: 0.1, far: 100 }}
        gl={{ antialias: true, alpha: true, powerPreference: "high-performance" }}
        fallback={<ModelFallback label="Wizualizacja uproszczona" />}
      >
        <Scene
          activeRegion={activeRegion}
          focusMode={focusMode}
          onRegionChange={onRegionChange}
          reducedMotion={reducedMotion}
        />
      </Canvas>
    </div>
  );
}
