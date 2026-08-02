"use client";

import {
  ContactShadows,
  Float,
  Line,
  Sparkles,
} from "@react-three/drei";
import { Canvas, useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";

type Point3D = [number, number, number];

const jointPoints: Record<string, Point3D> = {
  head: [0.1, 2.52, 0],
  neck: [0.02, 1.98, 0],

  leftShoulder: [-0.62, 1.75, 0],
  rightShoulder: [0.66, 1.75, 0],

  leftElbow: [-1.02, 0.92, 0.12],
  rightElbow: [1.04, 1.02, -0.02],

  leftWrist: [-0.8, 0.06, 0.26],
  rightWrist: [1.34, 0.23, 0.1],

  leftHip: [-0.34, 0.35, 0],
  rightHip: [0.36, 0.35, 0],

  leftKnee: [-0.43, -0.9, 0.1],
  rightKnee: [0.47, -0.84, -0.06],

  leftAnkle: [-0.46, -2.08, 0.02],
  rightAnkle: [0.5, -2.08, 0.04],
};

const skeletonSegments: Array<[string, string]> = [
  ["head", "neck"],

  ["neck", "leftShoulder"],
  ["neck", "rightShoulder"],

  ["leftShoulder", "leftElbow"],
  ["leftElbow", "leftWrist"],

  ["rightShoulder", "rightElbow"],
  ["rightElbow", "rightWrist"],

  ["neck", "leftHip"],
  ["neck", "rightHip"],

  ["leftHip", "rightHip"],

  ["leftHip", "leftKnee"],
  ["leftKnee", "leftAnkle"],

  ["rightHip", "rightKnee"],
  ["rightKnee", "rightAnkle"],
];

const bodySegments: Array<{
  start: string;
  end: string;
  radius: number;
}> = [
  {
    start: "leftShoulder",
    end: "leftElbow",
    radius: 0.13,
  },
  {
    start: "leftElbow",
    end: "leftWrist",
    radius: 0.105,
  },
  {
    start: "rightShoulder",
    end: "rightElbow",
    radius: 0.13,
  },
  {
    start: "rightElbow",
    end: "rightWrist",
    radius: 0.105,
  },
  {
    start: "leftHip",
    end: "leftKnee",
    radius: 0.18,
  },
  {
    start: "leftKnee",
    end: "leftAnkle",
    radius: 0.145,
  },
  {
    start: "rightHip",
    end: "rightKnee",
    radius: 0.18,
  },
  {
    start: "rightKnee",
    end: "rightAnkle",
    radius: 0.145,
  },
];

type SegmentTransform = {
  midpoint: THREE.Vector3;
  quaternion: THREE.Quaternion;
  length: number;
};

function calculateSegmentTransform(
  start: Point3D,
  end: Point3D,
): SegmentTransform {
  const startVector = new THREE.Vector3(...start);
  const endVector = new THREE.Vector3(...end);

  const direction = new THREE.Vector3().subVectors(
    endVector,
    startVector,
  );

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

function SkeletonSegment({
  start,
  end,
}: {
  start: Point3D;
  end: Point3D;
}) {
  const transform = useMemo(
    () => calculateSegmentTransform(start, end),
    [start, end],
  );

  return (
    <group
      position={transform.midpoint}
      quaternion={transform.quaternion}
    >
      <mesh>
        <cylinderGeometry
          args={[0.045, 0.045, transform.length, 16]}
        />

        <meshStandardMaterial
          color="#7dd3fc"
          emissive="#0891b2"
          emissiveIntensity={1.1}
          metalness={0.35}
          roughness={0.2}
        />
      </mesh>

      <mesh>
        <cylinderGeometry
          args={[0.075, 0.075, transform.length, 16]}
        />

        <meshBasicMaterial
          color="#22d3ee"
          transparent
          opacity={0.08}
          depthWrite={false}
        />
      </mesh>
    </group>
  );
}

function BodySegment({
  start,
  end,
  radius,
}: {
  start: Point3D;
  end: Point3D;
  radius: number;
}) {
  const transform = useMemo(
    () => calculateSegmentTransform(start, end),
    [start, end],
  );

  return (
    <mesh
      position={transform.midpoint}
      quaternion={transform.quaternion}
    >
      <cylinderGeometry
        args={[
          radius * 0.88,
          radius,
          transform.length,
          24,
        ]}
      />

      <meshStandardMaterial
        color="#164e63"
        emissive="#0e7490"
        emissiveIntensity={0.2}
        transparent
        opacity={0.28}
        metalness={0.4}
        roughness={0.32}
        side={THREE.DoubleSide}
        depthWrite={false}
      />
    </mesh>
  );
}

function Joint({
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

          <mesh>
            <torusGeometry args={[0.15, 0.008, 12, 48]} />

            <meshBasicMaterial
              color="#fbbf24"
              transparent
              opacity={0.72}
            />
          </mesh>
        </>
      )}

      <mesh>
        <sphereGeometry
          args={[active ? 0.095 : 0.072, 24, 24]}
        />

        <meshStandardMaterial
          color={active ? "#fde68a" : "#a5f3fc"}
          emissive={active ? "#f59e0b" : "#06b6d4"}
          emissiveIntensity={active ? 1.6 : 0.8}
          metalness={0.3}
          roughness={0.16}
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
    const segments = 36;

    return Array.from({ length: segments }, (_, index) => {
      const progress = index / (segments - 1);

      const angle =
        startAngle + (endAngle - startAngle) * progress;

      return new THREE.Vector3(
        Math.cos(angle) * radius,
        Math.sin(angle) * radius,
        0,
      );
    });
  }, [radius, startAngle, endAngle]);

  return (
    <group position={center} rotation={rotation}>
      <Line
        points={points}
        color={color}
        lineWidth={1.7}
        transparent
        opacity={0.9}
      />

      <mesh
        position={[
          Math.cos(endAngle) * radius,
          Math.sin(endAngle) * radius,
          0,
        ]}
      >
        <sphereGeometry args={[0.035, 16, 16]} />

        <meshBasicMaterial color={color} />
      </mesh>
    </group>
  );
}

function TorsoShell() {
  return (
    <>
      <mesh
        position={[0.03, 1.05, -0.01]}
        rotation={[0, 0, -0.035]}
        scale={[0.88, 1.08, 0.48]}
      >
        <capsuleGeometry args={[0.48, 0.82, 12, 28]} />

        <meshStandardMaterial
          color="#155e75"
          emissive="#164e63"
          emissiveIntensity={0.28}
          transparent
          opacity={0.22}
          metalness={0.45}
          roughness={0.28}
          side={THREE.DoubleSide}
          depthWrite={false}
        />
      </mesh>

      <mesh
        position={[0.02, 0.34, 0]}
        scale={[0.68, 0.42, 0.42]}
      >
        <sphereGeometry args={[0.62, 32, 32]} />

        <meshStandardMaterial
          color="#0e7490"
          emissive="#164e63"
          emissiveIntensity={0.16}
          transparent
          opacity={0.24}
          metalness={0.35}
          roughness={0.32}
          depthWrite={false}
        />
      </mesh>
    </>
  );
}

function HeadModel() {
  return (
    <group position={jointPoints.head}>
      <mesh scale={[0.82, 1, 0.82]}>
        <sphereGeometry args={[0.31, 32, 32]} />

        <meshStandardMaterial
          color="#164e63"
          emissive="#0891b2"
          emissiveIntensity={0.28}
          transparent
          opacity={0.36}
          metalness={0.35}
          roughness={0.2}
          depthWrite={false}
        />
      </mesh>

      <mesh
        position={[0.02, 0.01, 0.02]}
        scale={[0.66, 0.82, 0.66]}
      >
        <sphereGeometry args={[0.31, 24, 24]} />

        <meshBasicMaterial
          color="#67e8f9"
          transparent
          opacity={0.07}
          wireframe
        />
      </mesh>
    </group>
  );
}

function ScanBeam() {
  const beamRef = useRef<THREE.Mesh>(null);

  useFrame((state) => {
    const beam = beamRef.current;

    if (!beam) {
      return;
    }

    const progress =
      (state.clock.getElapsedTime() * 0.18) % 1;

    beam.position.y = -2.05 + progress * 4.7;
  });

  return (
    <mesh ref={beamRef} position={[0, 0, 0.35]}>
      <boxGeometry args={[3.25, 0.025, 0.04]} />

      <meshBasicMaterial
        color="#67e8f9"
        transparent
        opacity={0.68}
      />
    </mesh>
  );
}

function GroundScanner() {
  const ringRef = useRef<THREE.Mesh>(null);

  useFrame((state) => {
    const ring = ringRef.current;

    if (!ring) {
      return;
    }

    const scale =
      1 + Math.sin(state.clock.getElapsedTime() * 1.4) * 0.08;

    ring.scale.set(scale, scale, scale);
  });

  return (
    <group
      position={[0, -2.14, 0]}
      rotation={[-Math.PI / 2, 0, 0]}
    >
      <mesh ref={ringRef}>
        <ringGeometry args={[0.86, 0.9, 64]} />

        <meshBasicMaterial
          color="#22d3ee"
          transparent
          opacity={0.55}
          side={THREE.DoubleSide}
        />
      </mesh>

      <mesh>
        <ringGeometry args={[1.28, 1.3, 64]} />

        <meshBasicMaterial
          color="#10b981"
          transparent
          opacity={0.2}
          side={THREE.DoubleSide}
        />
      </mesh>
    </group>
  );
}

function DigitalHuman() {
  const groupRef = useRef<THREE.Group>(null);

  useFrame((state) => {
    const group = groupRef.current;

    if (!group) {
      return;
    }

    const targetRotationY = state.pointer.x * 0.2;
    const targetRotationX = -state.pointer.y * 0.06;

    group.rotation.y = THREE.MathUtils.lerp(
      group.rotation.y,
      targetRotationY,
      0.04,
    );

    group.rotation.x = THREE.MathUtils.lerp(
      group.rotation.x,
      targetRotationX,
      0.04,
    );

    group.position.y =
      Math.sin(state.clock.getElapsedTime() * 1.1) * 0.025;
  });

  return (
    <group
      ref={groupRef}
      position={[0, -0.05, 0]}
      scale={1.02}
    >
      <TorsoShell />
      <HeadModel />

      {bodySegments.map((segment) => (
        <BodySegment
          key={`${segment.start}-${segment.end}`}
          start={jointPoints[segment.start]}
          end={jointPoints[segment.end]}
          radius={segment.radius}
        />
      ))}

      {skeletonSegments.map(([startName, endName]) => (
        <SkeletonSegment
          key={`${startName}-${endName}`}
          start={jointPoints[startName]}
          end={jointPoints[endName]}
        />
      ))}

      {Object.entries(jointPoints).map(
        ([jointName, position]) => (
          <Joint
            key={jointName}
            position={position}
            active={[
              "neck",
              "rightElbow",
              "leftHip",
              "rightKnee",
            ].includes(jointName)}
          />
        ),
      )}

      <AngleArc
        center={jointPoints.rightElbow}
        radius={0.34}
        startAngle={1.8}
        endAngle={4.45}
        color="#fbbf24"
      />

      <AngleArc
        center={jointPoints.neck}
        radius={0.29}
        startAngle={0.1}
        endAngle={1.4}
        color="#34d399"
      />

      <AngleArc
        center={[0.02, 0.72, 0.14]}
        radius={0.38}
        startAngle={1.15}
        endAngle={1.9}
        color="#22d3ee"
      />

      <ScanBeam />
      <GroundScanner />
    </group>
  );
}

export function ErgonomicSkeleton() {
  return (
    <div className="h-[470px] w-full sm:h-[500px]">
      <Canvas
        dpr={[1, 1.6]}
        camera={{
          position: [0, 0.15, 7.5],
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

        <ambientLight intensity={0.75} />

        <directionalLight
          position={[4, 6, 5]}
          intensity={2.5}
          color="#d5fff7"
        />

        <pointLight
          position={[-3.5, 1.5, 3]}
          intensity={22}
          color="#06b6d4"
          distance={11}
        />

        <pointLight
          position={[3.5, -1, 2.5]}
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
          scale={[5, 5.6, 3]}
          size={1.5}
          speed={0.18}
          opacity={0.3}
          color="#67e8f9"
        />

        <gridHelper
          args={[8, 20, "#155e75", "#0f2535"]}
          position={[0, -2.16, 0]}
        />

        <Float
          speed={1.15}
          rotationIntensity={0.025}
          floatIntensity={0.08}
          floatingRange={[-0.035, 0.035]}
        >
          <DigitalHuman />
        </Float>

        <ContactShadows
          position={[0, -2.18, 0]}
          opacity={0.4}
          scale={5}
          blur={2.6}
          far={4}
          color="#020617"
        />
      </Canvas>
    </div>
  );
}