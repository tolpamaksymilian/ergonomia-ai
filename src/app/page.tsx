import type { Metadata } from "next";

import { HeroSection } from "@/components/landing/hero-section";
import { HomeProjectSections } from "@/components/project/home-project-sections";
import { SiteHeader } from "@/components/layout/site-header";
import { SiteFooter } from "@/components/layout/site-footer";
import { createClient } from "@/lib/supabase/server";

export const metadata: Metadata = {
  title: { absolute: "Ergonomia AI — analiza ergonomii na podstawie filmu" },
  description:
    "Analiza ruchu, metryki postawy i raport ergonomiczny na podstawie krótkiego nagrania.",
};

export default async function HomePage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  return (
    <main className="ui-page">
      <SiteHeader />
      <HeroSection isAuthenticated={Boolean(user)} />
      <HomeProjectSections isAuthenticated={Boolean(user)} />
      <SiteFooter />
    </main>
  );
}
