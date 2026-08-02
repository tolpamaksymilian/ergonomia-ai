import { SiteHeader } from "@/components/layout/site-header";
import { SystemStatusView } from "@/components/status/system-status-view";
import { createClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

export default async function SystemStatusPage() {
  const supabase = await createClient();

  const { data, error } = await supabase
    .from("system_status")
    .select("app_name, status, version, updated_at")
    .eq("id", 1)
    .single();

  const updatedAt = data?.updated_at
    ? new Intl.DateTimeFormat("pl-PL", {
        dateStyle: "long",
        timeStyle: "short",
        timeZone: "Europe/Warsaw",
      }).format(new Date(data.updated_at))
    : "Brak danych";

  return (
    <main className="min-h-screen overflow-hidden bg-[#050b14] text-white">
      <SiteHeader />

      <SystemStatusView
        data={
          data
            ? {
                appName: data.app_name,
                status: data.status,
                version: data.version,
                updatedAt,
              }
            : undefined
        }
        errorMessage={error?.message}
      />
    </main>
  );
}