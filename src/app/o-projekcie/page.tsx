import type { Metadata } from "next";

import { SiteHeader } from "@/components/layout/site-header";
import { SiteFooter } from "@/components/layout/site-footer";
import { ProjectOverview } from "@/components/project/project-overview";

export const metadata: Metadata = {
  title: { absolute: "O projekcie — Ergonomia AI" },
  description:
    "Zobacz, jak działa system analizy ergonomii i jaki jest aktualny etap jego rozwoju.",
};

export default function AboutProjectPage() {
  return (
    <main className="ui-page">
      <SiteHeader />
      <ProjectOverview />
      <SiteFooter />
    </main>
  );
}
