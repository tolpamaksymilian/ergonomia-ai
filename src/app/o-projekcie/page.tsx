import type { Metadata } from "next";

import { SiteHeader } from "@/components/layout/site-header";
import { ProjectOverview } from "@/components/project/project-overview";

export const metadata: Metadata = {
  title: { absolute: "O projekcie — Ergonomia AI" },
  description:
    "Zobacz, jak Ergonomia AI analizuje ruch i jakie są obecne możliwości systemu.",
};

export default function AboutProjectPage() {
  return (
    <main className="min-h-screen overflow-hidden bg-[#050b14] text-white">
      <SiteHeader />
      <ProjectOverview />
    </main>
  );
}
