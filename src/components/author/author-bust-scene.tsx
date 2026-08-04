"use client";

import { Line } from "@react-three/drei";
import { Canvas, useFrame } from "@react-three/fiber";
import { useRef } from "react";
import * as THREE from "three";

export function AuthorBustScene({ reducedMotion }: { reducedMotion: boolean }) {
  return (
    <div className="h-[360px] w-full sm:h-[460px]">
      <Canvas
        aria-label="Symboliczne, techniczne popiersie autora"
        role="img"
        camera={{ position: [0, 0.15, 5.2], fov: 34, near: 0.1, far: 30 }}
        dpr={[1, 1.4]}
        frameloop={reducedMotion ? "demand" : "always"}
        gl={{ antialias: true, alpha: true, powerPreference: "high-performance" }}
      >
        <hemisphereLight args={["#d8fff7", "#020617", 1.15]} />
        <directionalLight position={[3, 4, 5]} intensity={2.4} color="#d8fff7" />
        <directionalLight position={[-3, 1, -2]} intensity={1.5} color="#22d3ee" />
        <pointLight position={[2.2, -0.2, 3]} intensity={7} color="#10b981" distance={8} />
        <TechnicalBust reducedMotion={reducedMotion} />
      </Canvas>
    </div>
  );
}

function TechnicalBust({ reducedMotion }: { reducedMotion: boolean }) {
  const group = useRef<THREE.Group>(null);

  useFrame(({ clock }, delta) => {
    if (reducedMotion || !group.current) return;
    const target = Math.sin(clock.elapsedTime * 0.28) * 0.12;
    group.current.rotation.y = THREE.MathUtils.damp(group.current.rotation.y, target, 2.2, delta);
    group.current.position.y = Math.sin(clock.elapsedTime * 0.45) * 0.012;
  });

  return (
    <group ref={group} position={[0, -0.18, 0]} rotation={[0.02, -0.08, 0]}>
      <BustBase />
      <Neck />
      <Head />
      <FaceGuides />
    </group>
  );
}

const bodyMaterial = {
  color: "#102f3a",
  roughness: 0.48,
  metalness: 0.2,
} as const;

function BustBase() {
  return (
    <group position={[0, -1.35, 0]}>
      <mesh scale={[1.58, 0.48, 0.62]}>
        <sphereGeometry args={[1, 40, 24]} />
        <meshStandardMaterial {...bodyMaterial} />
      </mesh>
      <mesh position={[0, -0.34, -0.04]} scale={[1.18, 0.36, 0.5]}>
        <sphereGeometry args={[1, 32, 18]} />
        <meshStandardMaterial color="#081923" roughness={0.62} metalness={0.12} />
      </mesh>
      <mesh position={[0, 0.22, 0.37]} scale={[1.26, 0.16, 0.14]}>
        <sphereGeometry args={[1, 32, 12]} />
        <meshStandardMaterial color="#155e75" emissive="#0e7490" emissiveIntensity={0.18} roughness={0.4} />
      </mesh>
    </group>
  );
}

function Neck() {
  return (
    <group position={[0, -0.72, 0]}>
      <mesh scale={[0.48, 0.72, 0.42]}>
        <capsuleGeometry args={[0.46, 0.52, 8, 20]} />
        <meshStandardMaterial {...bodyMaterial} />
      </mesh>
      <mesh position={[0, 0.18, 0.37]} scale={[0.32, 0.48, 0.1]}>
        <sphereGeometry args={[1, 24, 16]} />
        <meshStandardMaterial color="#164e63" roughness={0.45} />
      </mesh>
    </group>
  );
}

function Head() {
  return (
    <group position={[0, 0.55, 0]}>
      <mesh scale={[0.78, 1.03, 0.76]}>
        <icosahedronGeometry args={[1, 4]} />
        <meshStandardMaterial {...bodyMaterial} />
      </mesh>
      <mesh position={[0, -0.48, 0.1]} scale={[0.66, 0.58, 0.64]}>
        <icosahedronGeometry args={[1, 3]} />
        <meshStandardMaterial color="#0d2833" roughness={0.55} metalness={0.16} />
      </mesh>
      <mesh position={[0, 0.05, 0.69]} scale={[0.61, 0.66, 0.075]}>
        <sphereGeometry args={[1, 28, 18]} />
        <meshStandardMaterial color="#164e63" emissive="#0e7490" emissiveIntensity={0.12} roughness={0.38} transparent opacity={0.9} />
      </mesh>
      <mesh scale={[0.792, 1.045, 0.772]}>
        <icosahedronGeometry args={[1, 2]} />
        <meshBasicMaterial color="#67e8f9" wireframe transparent opacity={0.13} depthWrite={false} />
      </mesh>
    </group>
  );
}

function FaceGuides() {
  const points: ReadonlyArray<readonly [number, number, number]> = [
    [0, 1.23, 0.72],
    [-0.47, 0.72, 0.76],
    [0.47, 0.72, 0.76],
    [0, 0.2, 0.76],
    [-0.42, -0.64, 0.34],
    [0.42, -0.64, 0.34],
  ];

  return (
    <group>
      <Line points={[[0, 1.22, 0.74], [0, 0.18, 0.79]]} color="#67e8f9" transparent opacity={0.35} lineWidth={0.7} />
      <Line points={[[-0.48, 0.72, 0.78], [0.48, 0.72, 0.78]]} color="#34d399" transparent opacity={0.32} lineWidth={0.7} />
      {points.map((point) => (
        <mesh key={point.join(":")} position={point}>
          <sphereGeometry args={[0.035, 10, 8]} />
          <meshBasicMaterial color="#a7f3d0" />
        </mesh>
      ))}
    </group>
  );
}
