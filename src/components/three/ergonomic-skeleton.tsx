"use client";

import { ContactShadows, Float, Line, Sparkles } from "@react-three/drei";
import { Canvas, useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";

export type FocusMode = "full" | "upper" | "arm";

type ErgonomicSkeletonProps = {
  focusMode?: FocusMode;
};

type Point3D = [number, number, number];

const joints: Record<string, Point3D> = {
  head: [0.06, 2.52, 0],
  neck: [0.02, 1.98, 0],
  chest: [0.03, 1.42, 0.02],
  pelvis: [0.02, 0.42, 0],

  leftShoulder: [-0.62, 1.8, 0],
  rightShoulder: [0.66, 1.8, 0],

  leftElbow: [-1.04, 0.96, 0.14],
  rightElbow: [1.02, 1.04, -0.02],

  leftWrist: [-0.82, 0.12, 0.24],
  rightWrist: [1.32, 0.28, 0.08],

  leftHand: [-0.7, -0.14, 0.28],
  rightHand: [1.48, 0.08, 0.12],

  leftHip: [-0.34, 0.34, 0],
  rightHip: [0.38, 0.34, 0],

  leftKnee: [-0.42, -0.9, 0.08],
  rightKnee: [0.48, -0.84, -0.04],

  leftAnkle: [-0.44, -2.02, 0.02],
  rightAnkle: [0.52, -2.02, 0.04],

  leftFoot: [-0.36, -2.12, 0.34],
  rightFoot: [0.66, -2.12, 0.34],
};

const skeletonSegments: Array<[string, string]> = [
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

const bodySegments: Array<{
  start: string;
  end: string;
  radius: number;
  color: string;
}> = [
  { start: "leftShoulder", end: "leftElbow", radius: 0.14, color: "#0e7490" },
  { start: "leftElbow", end: "leftWrist", radius: 0.11, color: "#0e7490" },
  { start: "rightShoulder", end: "rightElbow", radius: 0.14, color: "#0e7490" },
  { start: "rightElbow", end: "rightWrist", radius: 0.11, color: "#0e7490" },

  { start: "leftHip", end: "leftKnee", radius: 0.18, color: "#155e75" },
  { start: "leftKnee", end: "leftAnkle", radius: 0.145, color: "#155e75" },
  { start: "rightHip", end: "rightKnee", radius: 0.18, color: "#155e75" },
  { start: "rightKnee", end: "rightAnkle", radius: 0.145, color: "#155e75" },
];

function segmentTransform(start: Point3D, end: Point3D) {
  const startVector = new THREE.Vector3(...start);
  const endVector = new THREE.Vector3(...end);

  const direction = new THREE.Vector3().subVectors(endVector, startVector);
  const midpoint = new THREE.Vector3()
    .addVectors(startVector, endVector)
    .multiplyScalar(0.5);

  const quaternion = new THREE.Quaternion().setFromUnitVectors(
    new THREE.Vector3(0, 1, 0),
    direction.clone().normalize(),
  );

  return {
    midpoint,
    quaternion,
    length: direction.length(),
  };
}

function CameraRig({ focusMode }: { focusMode: FocusMode }) {
  const targetRef = useRef(new THREE.Vector3(0, 0.4, 0));

  useFrame((state, delta) => {
    const camera = state.camera as THREE.PerspectiveCamera;

    const focusMap: Record<
      FocusMode,
      { position: Point3D; target: Point3D; pointerFactor: number }
    > = {
      full: {
        position: [0, 0.15, 7.4],
        target: [0, 0.35, 0],
        pointerFactor: 0.18,
      },
      upper: {
        position: [0, 1.15, 5.1],
        target: [0, 1.18, 0],
        pointerFactor: 0.1,
      },
      arm: {
        position: [1.55, 1.0, 3.7],
        target: [0.94, 0.98, 0],
        pointerFactor: 0.06,
      },
    };

    const current = focusMap[focusMode];
    const ease = 1 - Math.exp(-delta * 4);

    const desiredPosition = new THREE.Vector3(
      current.position[0] + state.pointer.x * current.pointerFactor,
      current.position[1] - state.pointer.y * current.pointerFactor * 0.65,
      current.position[2],
    );

    const desiredTarget = new THREE.Vector3(
      current.target[0],
      current.target[1] - state.pointer.y * 0.08,
      current.target[2],
    );

    camera.position.lerp(desiredPosition, ease);
    targetRef.current.lerp(desiredTarget, ease);
    camera.lookAt(targetRef.current);
  });

  return null;
}

function SkeletonTube({
  start,
  end,
}: {
  start: Point3D;
  end: Point3D;
}) {
  const transform = useMemo(() => segmentTransform(start, end), [start, end]);

  return (
    <group position={transform.midpoint} quaternion={transform.quaternion}>
      <mesh>
        <cylinderGeometry args={[0.04, 0.04, transform.length, 18]} />
        <meshStandardMaterial
          color="#7dd3fc"
          emissive="#0891b2"
          emissiveIntensity={1.25}
          metalness={0.35}
          roughness={0.18}
        />
      </mesh>

      <mesh>
        <cylinderGeometry args={[0.072, 0.072, transform.length, 18]} />
        <meshBasicMaterial
          color="#22d3ee"
          transparent
          opacity={0.06}
          depthWrite={false}
        />
      </mesh>
    </group>
  );
}

function BodyTube({
  start,
  end,
  radius,
  color,
}: {
  start: Point3D;
  end: Point3D;
  radius: number;
  color: string;
}) {
  const transform = useMemo(() => segmentTransform(start, end), [start, end]);

  return (
    <mesh position={transform.midpoint} quaternion={transform.quaternion}>
      <cylinderGeometry args={[radius * 0.88, radius, transform.length, 24]} />
      <meshStandardMaterial
        color={color}
        emissive="#0f766e"
        emissiveIntensity={0.18}
        transparent
        opacity={0.24}
        metalness={0.42}
        roughness={0.28}
        side={THREE.DoubleSide}
        depthWrite={false}
      />
    </mesh>
  );
}

function JointNode({
  position,
  active = false,
}: {
  position: Point3D;
  active?: boolean;
}) {
  return (
    <group position={position}>
      {active && (
        <>
          <mesh>
            <sphereGeometry args={[0.19, 24, 24]} />
            <meshBasicMaterial
              color="#fbbf24"
              transparent
              opacity={0.08}
              depthWrite={false}
            />
          </mesh>

          <mesh rotation={[Math.PI / 2, 0, 0]}>
            <torusGeometry args={[0.145, 0.008, 12, 48]} />
            <meshBasicMaterial color="#fbbf24" transparent opacity={0.72} />
          </mesh>
        </>
      )}

      <mesh>
        <sphereGeometry args={[active ? 0.094 : 0.07, 24, 24]} />
        <meshStandardMaterial
          color={active ? "#fde68a" : "#a5f3fc"}
          emissive={active ? "#f59e0b" : "#06b6d4"}
          emissiveIntensity={active ? 1.6 : 0.9}
          metalness={0.32}
          roughness={0.14}
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
  const points = useMemo(() => {
    const segments = 40;

    return Array.from({ length: segments }, (_, index) => {
      const t = index / (segments - 1);
      const angle = startAngle + (endAngle - startAngle) * t;

      return new THREE.Vector3(
        Math.cos(angle) * radius,
        Math.sin(angle) * radius,
        0,
      );
    });
  }, [radius, startAngle, endAngle]);

  return (
    <group position={center} rotation={rotation}>
      <Line points={points} color={color} lineWidth={1.8} transparent opacity={0.92} />
      <mesh
        position={[
          Math.cos(endAngle) * radius,
          Math.sin(endAngle) * radius,
          0,
        ]}
      >
        <sphereGeometry args={[0.03, 16, 16]} />
        <meshBasicMaterial color={color} />
      </mesh>
    </group>
  );
}

function TorsoShell() {
  return (
    <>
      <mesh position={[0.03, 1.08, 0]} rotation={[0, 0, -0.03]} scale={[0.92, 1.18, 0.5]}>
        <capsuleGeometry args={[0.5, 0.95, 14, 28]} />
        <meshStandardMaterial
          color="#164e63"
          emissive="#155e75"
          emissiveIntensity={0.22}
          transparent
          opacity={0.23}
          metalness={0.48}
          roughness={0.25}
          side={THREE.DoubleSide}
          depthWrite={false}
        />
      </mesh>

      <mesh position={[0.02, 0.38, 0]} scale={[0.72, 0.46, 0.44]}>
        <sphereGeometry args={[0.62, 32, 32]} />
        <meshStandardMaterial
          color="#155e75"
          emissive="#164e63"
          emissiveIntensity={0.16}
          transparent
          opacity={0.22}
          metalness={0.38}
          roughness={0.3}
          side={THREE.DoubleSide}
          depthWrite={false}
        />
      </mesh>
    </>
  );
}

function HeadShell() {
  return (
    <group position={joints.head}>
      <mesh scale={[0.82, 1, 0.82]}>
        <sphereGeometry args={[0.31, 32, 32]} />
        <meshStandardMaterial
          color="#164e63"
          emissive="#0891b2"
          emissiveIntensity={0.24}
          transparent
          opacity={0.32}
          metalness={0.35}
          roughness={0.18}
          depthWrite={false}
        />
      </mesh>

      <mesh scale={[0.66, 0.84, 0.66]}>
        <sphereGeometry args={[0.31, 24, 24]} />
        <meshBasicMaterial color="#67e8f9" transparent opacity={0.06} wireframe />
      </mesh>
    </group>
  );
}

function FloorScanner() {
  const ringRef = useRef<THREE.Mesh>(null);

  useFrame((state) => {
    if (!ringRef.current) return;

    const s = 1 + Math.sin(state.clock.getElapsedTime() * 1.35) * 0.06;
    ringRef.current.scale.set(s, s, s);
  });

  return (
    <group position={[0, -2.16, 0]} rotation={[-Math.PI / 2, 0, 0]}>
      <mesh ref={ringRef}>
        <ringGeometry args={[0.9, 0.94, 64]} />
        <meshBasicMaterial color="#22d3ee" transparent opacity={0.5} side={THREE.DoubleSide} />
      </mesh>

      <mesh>
        <ringGeometry args={[1.28, 1.32, 64]} />
        <meshBasicMaterial color="#10b981" transparent opacity={0.18} side={THREE.DoubleSide} />
      </mesh>
    </group>
  );
}

function ScanBeam() {
  const beamRef = useRef<THREE.Mesh>(null);

  useFrame((state) => {
    if (!beamRef.current) return;

    const p = (state.clock.getElapsedTime() * 0.18) % 1;
    beamRef.current.position.y = -2.06 + p * 4.72;
  });

  return (
    <mesh ref={beamRef} position={[0, 0, 0.36]}>
      <boxGeometry args={[3.2, 0.025, 0.04]} />
      <meshBasicMaterial color="#67e8f9" transparent opacity={0.66} />
    </mesh>
  );
}

function FingerFan({ side }: { side: "left" | "right" }) {
  const hand = side === "left" ? joints.leftHand : joints.rightHand;
  const sign = side === "left" ? -1 : 1;

  const lines = [
    [hand, [hand[0] + 0.16 * sign, hand[1] - 0.02, hand[2] + 0.02]],
    [hand, [hand[0] + 0.18 * sign, hand[1] + 0.05, hand[2] + 0.02]],
    [hand, [hand[0] + 0.16 * sign, hand[1] + 0.12, hand[2] + 0.01]],
  ] as Array<[Point3D, Point3D]>;

  return (
    <>
      {lines.map(([start, end], index) => (
        <Line
          key={`${side}-${index}`}
          points={[new THREE.Vector3(...start), new THREE.Vector3(...end)]}
          color="#67e8f9"
          lineWidth={1}
          transparent
          opacity={0.55}
        />
      ))}
    </>
  );
}

function DigitalHuman() {
  const groupRef = useRef<THREE.Group>(null);

  useFrame((state) => {
    if (!groupRef.current) return;

    groupRef.current.rotation.y = THREE.MathUtils.lerp(
      groupRef.current.rotation.y,
      state.pointer.x * 0.18,
      0.04,
    );

    groupRef.current.rotation.x = THREE.MathUtils.lerp(
      groupRef.current.rotation.x,
      -state.pointer.y * 0.05,
      0.04,
    );

    groupRef.current.position.y = Math.sin(state.clock.getElapsedTime() * 1.15) * 0.024;
  });

  return (
    <group ref={groupRef} position={[0, -0.04, 0]} scale={1.03}>
      <TorsoShell />
      <HeadShell />

      {bodySegments.map((segment) => (
        <BodyTube
          key={`${segment.start}-${segment.end}`}
          start={joints[segment.start]}
          end={joints[segment.end]}
          radius={segment.radius}
          color={segment.color}
        />
      ))}

      {skeletonSegments.map(([startName, endName]) => (
        <SkeletonTube
          key={`${startName}-${endName}`}
          start={joints[startName]}
          end={joints[endName]}
        />
      ))}

      {Object.entries(joints).map(([name, position]) => (
        <JointNode
          key={name}
          position={position}
          active={["neck", "rightElbow", "pelvis", "rightKnee"].includes(name)}
        />
      ))}

      <FingerFan side="left" />
      <FingerFan side="right" />

      <AngleArc
        center={joints.rightElbow}
        radius={0.34}
        startAngle={1.85}
        endAngle={4.45}
        color="#fbbf24"
      />

      <AngleArc
        center={joints.neck}
        radius={0.28}
        startAngle={0.08}
        endAngle={1.35}
        color="#34d399"
      />

      <AngleArc
        center={[0.03, 0.74, 0.14]}
        radius={0.38}
        startAngle={1.16}
        endAngle={1.92}
        color="#22d3ee"
      />

      <FloorScanner />
      <ScanBeam />
    </group>
  );
}

export function ErgonomicSkeleton({
  focusMode = "full",
}: ErgonomicSkeletonProps) {
  return (
    <div className="h-[500px] w-full sm:h-[540px]">
      <Canvas
        dpr={[1, 1.6]}
        camera={{
          position: [0, 0.15, 7.4],
          fov: 42,
          near: 0.1,
          far: 100,
        }}
        gl={{
          antialias: true,
          alpha: true,
          powerPreference: "high-performance",
        }}
      >
        <fog attach="fog" args={["#07111f", 7, 13]} />

        <CameraRig focusMode={focusMode} />

        <ambientLight intensity={0.75} />

        <directionalLight
          position={[4, 6, 5]}
          intensity={2.6}
          color="#d8fff7"
        />

        <pointLight
          position={[-3.6, 1.6, 3]}
          intensity={22}
          color="#06b6d4"
          distance={11}
        />

        <pointLight
          position={[3.4, -1, 2.5]}
          intensity={18}
          color="#10b981"
          distance={10}
        />

        <pointLight
          position={[0, 3, -2]}
          intensity={13}
          color="#38bdf8"
          distance={9}
        />

        <Sparkles
          count={46}
          scale={[5, 5.8, 3]}
          size={1.45}
          speed={0.18}
          opacity={0.28}
          color="#67e8f9"
        />

        <gridHelper
          args={[8, 20, "#155e75", "#0f2535"]}
          position={[0, -2.18, 0]}
        />

        <Float
          speed={1.1}
          rotationIntensity={0.02}
          floatIntensity={0.06}
          floatingRange={[-0.03, 0.03]}
        >
          <DigitalHuman />
        </Float>

        <ContactShadows
          position={[0, -2.18, 0]}
          opacity={0.42}
          scale={5.2}
          blur={2.6}
          far={4}
          color="#020617"
        />
      </Canvas>
    </div>
  );
}