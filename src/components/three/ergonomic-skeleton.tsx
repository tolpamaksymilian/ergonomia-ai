"use client";

import { ContactShadows, Sparkles } from "@react-three/drei";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";

import { ModelFallback } from "@/components/landing/model-fallback";
import { BodyAnalysisOverlay } from "@/components/three/human-model/body-analysis-overlay";
import { TechnicalHumanModel } from "@/components/three/human-model/technical-human-model";
import {
  visualizationCamera,
  visualizationDetail,
  type AnalysisFocusMode,
  type AnalysisRegionId,
} from "@/config/analysis-visualization";

type ErgonomicSkeletonProps = {
  activeRegion: AnalysisRegionId;
  focusMode?: AnalysisFocusMode;
  onRegionHover?: (region: AnalysisRegionId | null) => void;
  onRegionSelect?: (region: AnalysisRegionId) => void;
  reducedMotion?: boolean;
};

function CameraRig({
  focusMode,
  reducedMotion,
}: {
  focusMode: AnalysisFocusMode;
  reducedMotion: boolean;
}) {
  const { size } = useThree();
  const compact = size.width < 520;
  const preset = useMemo(
    () =>
      (compact ? visualizationCamera.compact : visualizationCamera.desktop)[
        focusMode
      ],
    [compact, focusMode],
  );
  const target = useRef(new THREE.Vector3(...preset.target));
  const desiredPosition = useRef(new THREE.Vector3(...preset.position));
  const desiredTarget = useRef(new THREE.Vector3(...preset.target));

  useFrame((state, delta) => {
    const pointerX = reducedMotion
      ? 0
      : state.pointer.x * visualizationCamera.pointerParallax;
    const pointerY = reducedMotion
      ? 0
      : state.pointer.y * visualizationCamera.pointerParallax * 0.55;

    desiredPosition.current.set(
      preset.position[0] + pointerX,
      preset.position[1] - pointerY,
      preset.position[2],
    );
    desiredTarget.current.set(
      preset.target[0],
      preset.target[1] - pointerY * 0.35,
      preset.target[2],
    );

    if (reducedMotion) {
      state.camera.position.copy(desiredPosition.current);
      target.current.copy(desiredTarget.current);
    } else {
      const ease = 1 - Math.exp(-delta * 3.8);
      state.camera.position.lerp(desiredPosition.current, ease);
      target.current.lerp(desiredTarget.current, ease);
    }
    state.camera.lookAt(target.current);
  });

  return null;
}

function IndustrialEnvironment({ compact }: { compact: boolean }) {
  return (
    <group position={[0, 0, -1.25]}>
      {[-2.05, 2.05].map((x) => (
        <mesh key={x} position={[x, 0.02, 0]}>
          <boxGeometry args={[0.06, 5.2, 0.09]} />
          <meshStandardMaterial
            color="#0c2633"
            metalness={0.28}
            roughness={0.7}
          />
        </mesh>
      ))}
      {[-1.55, 0.05, 1.72].map((y) => (
        <mesh key={y} position={[0, y, 0]}>
          <boxGeometry args={[4.15, 0.045, 0.08]} />
          <meshStandardMaterial
            color="#103341"
            metalness={0.22}
            roughness={0.68}
          />
        </mesh>
      ))}
      {!compact && (
        <group position={[-1.65, 1.05, 0.055]}>
          <mesh>
            <boxGeometry args={[0.46, 0.66, 0.035]} />
            <meshStandardMaterial
              color="#081d28"
              emissive="#0e7490"
              emissiveIntensity={0.06}
              roughness={0.72}
            />
          </mesh>
          {[-0.16, 0, 0.16].map((y) => (
            <mesh key={y} position={[0, y, 0.026]}>
              <boxGeometry args={[0.28, 0.012, 0.008]} />
              <meshBasicMaterial color="#22d3ee" transparent opacity={0.24} />
            </mesh>
          ))}
        </group>
      )}
    </group>
  );
}

function Floor({ compact }: { compact: boolean }) {
  return (
    <group position={[0, visualizationDetail.floorY, 0]}>
      <gridHelper
        args={[7, compact ? 12 : 20, "#155e75", "#0c2531"]}
      />
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.006, 0]}>
        <circleGeometry args={[1.35, compact ? 36 : 64]} />
        <meshBasicMaterial
          color="#0e7490"
          transparent
          opacity={0.045}
          depthWrite={false}
        />
      </mesh>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.012, 0]}>
        <ringGeometry args={[0.72, 0.735, compact ? 36 : 64]} />
        <meshBasicMaterial color="#22d3ee" transparent opacity={0.32} />
      </mesh>
    </group>
  );
}

function Scene({
  activeRegion,
  focusMode,
  onRegionHover,
  onRegionSelect,
  reducedMotion,
}: {
  activeRegion: AnalysisRegionId;
  focusMode: AnalysisFocusMode;
  onRegionHover: (region: AnalysisRegionId | null) => void;
  onRegionSelect: (region: AnalysisRegionId) => void;
  reducedMotion: boolean;
}) {
  const { size } = useThree();
  const compact = size.width < 520;

  return (
    <>
      <fog attach="fog" args={["#06101b", 10.5, 16]} />
      <CameraRig focusMode={focusMode} reducedMotion={reducedMotion} />

      <hemisphereLight args={["#b9f7f0", "#041019", 0.72]} />
      <directionalLight
        position={[3.5, 5.5, 5.5]}
        intensity={2.05}
        color="#d8fff7"
      />
      <directionalLight
        position={[-3.8, 2.2, -2.4]}
        intensity={1.15}
        color="#22d3ee"
      />
      <pointLight
        position={[2.7, 0.4, 3.5]}
        intensity={8}
        color="#10b981"
        distance={9}
      />

      {!reducedMotion && !compact && (
        <Sparkles
          count={visualizationDetail.desktop.particles}
          scale={[4.6, 5.2, 2.4]}
          size={0.72}
          speed={0.08}
          opacity={0.13}
          color="#67e8f9"
        />
      )}

      <IndustrialEnvironment compact={compact} />
      <Floor compact={compact} />
      <TechnicalHumanModel
        activeRegion={activeRegion}
        compact={compact}
        onRegionHover={onRegionHover}
        onRegionSelect={onRegionSelect}
        reducedMotion={reducedMotion}
      />
      <BodyAnalysisOverlay
        activeRegion={activeRegion}
        reducedMotion={reducedMotion}
      />

      {!compact && (
        <ContactShadows
          position={[0, visualizationDetail.floorY + 0.012, 0.12]}
          opacity={0.34}
          scale={3.4}
          blur={2.8}
          far={3.2}
          color="#020617"
        />
      )}
    </>
  );
}

export function ErgonomicSkeleton({
  activeRegion,
  focusMode = "full",
  onRegionHover = () => undefined,
  onRegionSelect = () => undefined,
  reducedMotion = false,
}: ErgonomicSkeletonProps) {
  return (
    <div className="h-[420px] w-full sm:h-[540px]">
      <Canvas
        aria-label="Interaktywna techniczna wizualizacja analizy pozy pracownika"
        role="img"
        dpr={[1, 1.3]}
        frameloop={reducedMotion ? "demand" : "always"}
        camera={{
          position: visualizationCamera.desktop.full.position,
          fov: visualizationCamera.fov,
          near: 0.1,
          far: 100,
        }}
        gl={{
          antialias: true,
          alpha: true,
          powerPreference: "high-performance",
        }}
        fallback={<ModelFallback label="Wizualizacja uproszczona" />}
      >
        <Scene
          activeRegion={activeRegion}
          focusMode={focusMode}
          onRegionHover={onRegionHover}
          onRegionSelect={onRegionSelect}
          reducedMotion={reducedMotion}
        />
      </Canvas>
    </div>
  );
}
