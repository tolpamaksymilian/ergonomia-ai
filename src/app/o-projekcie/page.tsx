import type { Metadata } from "next";

import { SiteHeader } from "@/components/layout/site-header";
import { ProjectOverview } from "@/components/project/project-overview";

export const metadata: Metadata = {
  title: "O projekcie",
  description:
    "Poznaj architekturę Ergonomia AI, aktualny pipeline analizy pozy oraz ograniczenia pomiarów opartych na krótkim nagraniu wideo.",
};

export default function AboutProjectPage() {
  return (
    <main className="min-h-screen overflow-hidden bg-[#050b14] text-white">
      <SiteHeader />
      <ProjectOverview />
    </main>
  );
}
