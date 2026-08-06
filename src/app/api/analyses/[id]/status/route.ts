import { NextResponse } from "next/server";

import { createClient } from "@/lib/supabase/server";

type RouteContext = {
  params: Promise<{ id: string }>;
};

export async function GET(_request: Request, context: RouteContext) {
  const { id } = await context.params;
  const supabase = await createClient();
  const { data: authData, error: authError } = await supabase.auth.getUser();
  if (authError || !authData.user) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  const { data, error } = await supabase
    .from("analyses")
    .select("status, progress, processing_stage, report_path, updated_at")
    .eq("id", id)
    .maybeSingle();

  if (error) {
    console.error("analysis_status_query_failed", { code: error.code });
    return NextResponse.json({ error: "status_unavailable" }, { status: 500 });
  }
  if (!data) {
    return NextResponse.json({ error: "not_found" }, { status: 404 });
  }

  return NextResponse.json(data, {
    headers: { "Cache-Control": "private, no-store" },
  });
}
