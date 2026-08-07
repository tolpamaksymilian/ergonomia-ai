"use client";

import dynamic from "next/dynamic";
import { useReducedMotion } from "motion/react";
import { Component, type ErrorInfo, type ReactNode, useEffect, useState } from "react";

import { AuthorModelFallback } from "@/components/three/author-model/author-model-fallback";

const DynamicAuthorModelScene = dynamic(
  () =>
    import("@/components/three/author-model/author-model-scene").then(
      (module) => module.AuthorModelScene,
    ),
  { ssr: false, loading: () => <AuthorModelFallback /> },
);

export function AuthorModelLoader() {
  const [webglSupported, setWebglSupported] = useState<boolean | null>(null);
  const reducedMotion = useReducedMotion() ?? false;

  useEffect(() => {
    const canvas = document.createElement("canvas");
    const context = canvas.getContext("webgl2") ?? canvas.getContext("webgl");
    const timer = window.setTimeout(() => setWebglSupported(Boolean(context)), 0);
    return () => window.clearTimeout(timer);
  }, []);

  if (webglSupported !== true) return <AuthorModelFallback />;

  return (
    <AuthorModelErrorBoundary>
      <DynamicAuthorModelScene reducedMotion={reducedMotion} />
    </AuthorModelErrorBoundary>
  );
}

class AuthorModelErrorBoundary extends Component<
  { children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    if (process.env.NODE_ENV === "development") {
      console.error("Author model WebGL error", error.name, info.componentStack);
    }
  }

  render() {
    return this.state.failed ? <AuthorModelFallback /> : this.props.children;
  }
}
