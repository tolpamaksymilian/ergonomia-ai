import type { Metadata } from "next";

import { HeroSection } from "@/components/landing/hero-section";
import { HomeProjectSections } from "@/components/project/home-project-sections";
import { SiteHeader } from "@/components/layout/site-header";
import { SiteFooter } from "@/components/layout/site-footer";
import { createClient } from "@/lib/supabase/server";

export const metadata: Metadata = {
  description:
    "System wspierający analizę ergonomii stanowiska pracy na podstawie krótkiego nagrania wideo.",
};

export default async function HomePage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  return (
    <main className="min-h-screen overflow-hidden bg-[#050b14] text-white">
      <SiteHeader />
      <HeroSection isAuthenticated={Boolean(user)} />
      <HomeProjectSections isAuthenticated={Boolean(user)} />
      <SiteFooter />
    </main>
  );
}
