"use client";

import dynamic from "next/dynamic";
import { useReducedMotion } from "motion/react";
import { Component, type ErrorInfo, type ReactNode, useEffect, useState } from "react";

import { AuthorPortraitFallback } from "@/components/author/author-portrait-fallback";

const AuthorBustScene = dynamic(
  () => import("@/components/author/author-bust-scene").then((module) => module.AuthorBustScene),
  { ssr: false, loading: () => <AuthorPortraitFallback /> },
);

export function AuthorPortrait() {
  const [webglSupported, setWebglSupported] = useState<boolean | null>(null);
  const reducedMotion = useReducedMotion() ?? false;

  useEffect(() => {
    const canvas = document.createElement("canvas");
    const context = canvas.getContext("webgl2") ?? canvas.getContext("webgl");
    const timer = window.setTimeout(() => {
      setWebglSupported(Boolean(context));
    }, 0);

    return () => window.clearTimeout(timer);
  }, []);

  if (webglSupported !== true) {
    return <AuthorPortraitFallback />;
  }

  return (
    <PortraitErrorBoundary>
      <AuthorBustScene reducedMotion={reducedMotion} />
    </PortraitErrorBoundary>
  );
}

class PortraitErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    if (process.env.NODE_ENV === "development") {
      console.error("Author portrait WebGL error", error.name, info.componentStack);
    }
  }

  render() {
    return this.state.failed ? <AuthorPortraitFallback label="Awatar autora — tryb uproszczony" /> : this.props.children;
  }
}
