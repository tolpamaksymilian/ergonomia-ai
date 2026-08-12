"use client";

import { useGLTF } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";

const MODEL_PATH = "/models/author/author-head.glb";

export function AuthorBust({
  reducedMotion,
}: {
  reducedMotion: boolean;
}) {
  const group = useRef<THREE.Group>(null);
  const gltf = useGLTF(MODEL_PATH);
  const clayMaterial = useMemo(
    () =>
      new THREE.MeshStandardMaterial({
        color: "#263842",
        roughness: 0.72,
        metalness: 0.04,
      }),
    [],
  );
  const accentMaterial = useMemo(
    () =>
      new THREE.MeshStandardMaterial({
        color: "#f97316",
        emissive: "#0891b2",
        emissiveIntensity: 0.18,
        roughness: 0.5,
        metalness: 0.12,
      }),
    [],
  );
  const head = useMemo(() => {
    const clone = gltf.scene.clone(true);
    clone.traverse((object) => {
      if (object instanceof THREE.Mesh) {
        object.material = clayMaterial;
        object.castShadow = true;
        object.receiveShadow = true;
      }
    });
    return clone;
  }, [clayMaterial, gltf.scene]);

  useEffect(
    () => () => {
      clayMaterial.dispose();
      accentMaterial.dispose();
    }, [accentMaterial, clayMaterial],
  );

  useFrame((state, delta) => {
    if (!group.current || reducedMotion) return;
    const idle = Math.sin(state.clock.elapsedTime * 0.32) * 0.035;
    const targetY = -0.08 + state.pointer.x * 0.12 + idle;
    const targetX = state.pointer.y * -0.035;
    group.current.rotation.y = THREE.MathUtils.damp(group.current.rotation.y, targetY, 2.4, delta);
    group.current.rotation.x = THREE.MathUtils.damp(group.current.rotation.x, targetX, 2.4, delta);
  });

  return (
    <group ref={group} position={[0, -0.04, 0]} rotation={[0, -0.08, 0]}>
      <primitive object={head} position={[0, 0.1, 0.01]} scale={0.38} dispose={null} />
      <mesh position={[0, -1.52, 0]} material={accentMaterial} receiveShadow>
        <cylinderGeometry args={[0.92, 1.02, 0.08, 48]} />
      </mesh>
      <mesh position={[0, -1.58, 0]} receiveShadow>
        <cylinderGeometry args={[1.06, 1.16, 0.11, 48]} />
        <meshStandardMaterial color="#07131c" roughness={0.82} metalness={0.08} />
      </mesh>
    </group>
  );
}

useGLTF.preload(MODEL_PATH);
