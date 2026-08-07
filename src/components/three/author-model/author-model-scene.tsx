"use client";

import { Canvas } from "@react-three/fiber";

import { AuthorBust } from "@/components/three/author-model/author-bust";

export function AuthorModelScene({ reducedMotion }: { reducedMotion: boolean }) {
  return (
    <div className="h-[390px] w-full sm:h-[500px] lg:h-[560px]" aria-hidden="true">
      <Canvas
        camera={{ position: [0, 0.05, 6], fov: 32, near: 0.1, far: 20 }}
        dpr={[1, 1.5]}
        frameloop={reducedMotion ? "demand" : "always"}
        gl={{ antialias: true, alpha: true, powerPreference: "high-performance" }}
        shadows="basic"
      >
        <hemisphereLight args={["#d9fffb", "#020617", 0.85]} />
        <directionalLight
          position={[3.2, 4.5, 5]}
          intensity={2.25}
          color="#f0fffb"
          castShadow
          shadow-mapSize={[1024, 1024]}
        />
        <directionalLight position={[-3, 1.4, 2]} intensity={0.75} color="#9de9ff" />
        <directionalLight position={[2.5, 1, -3]} intensity={1.7} color="#22d3ee" />
        <AuthorBust reducedMotion={reducedMotion} />
      </Canvas>
    </div>
  );
}
