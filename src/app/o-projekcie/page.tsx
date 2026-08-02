import { SiteHeader } from "@/components/layout/site-header";
import { ProjectOverview } from "@/components/project/project-overview";

export default function AboutProjectPage() {
  return (
    <main className="min-h-screen overflow-hidden bg-[#050b14] text-white">
      <SiteHeader />
      <ProjectOverview />
    </main>
  );
}