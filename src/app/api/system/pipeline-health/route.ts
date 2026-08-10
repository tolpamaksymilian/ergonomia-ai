import { NextResponse } from "next/server";

import { requireUser } from "@/lib/auth/access";
import {
  isLocalRequest,
  localWorkerControlAllowed,
  readPipelineHealth,
  startPipelineSupervisor,
} from "@/lib/pipeline-health";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  if (!isLocalRequest(request) || process.env.VERCEL === "1" || process.env.VERCEL_ENV) {
    return NextResponse.json({ error: "not_found" }, { status: 404 });
  }
  const { supabase, profile } = await requireUser();
  const url = new URL(request.url);
  const analysisId = url.searchParams.get("analysisId");
  const health = await readPipelineHealth();
  let analysis = null;
  if (analysisId) {
    const result = await supabase
      .from("analyses")
      .select("id,status,progress,processing_stage,worker_id,heartbeat_at,updated_at,error_code")
      .eq("id", analysisId)
      .maybeSingle();
    if (result.error) {
      console.error("pipeline_health_analysis_query_failed", { code: result.error.code });
      return NextResponse.json({ error: "health_unavailable" }, { status: 500 });
    }
    analysis = result.data;
  }
  return NextResponse.json(
    { health, analysis, control_allowed: localWorkerControlAllowed() && profile?.role === "admin" },
    { headers: { "Cache-Control": "private, no-store" } },
  );
}

export async function POST(request: Request) {
  if (!isLocalRequest(request) || !localWorkerControlAllowed()) {
    return NextResponse.json({ error: "worker_control_disabled" }, { status: 403 });
  }
  const { profile } = await requireUser();
  if (profile?.role !== "admin") {
    return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }
  const body: unknown = await request.json().catch(() => null);
  const action = body && typeof body === "object" && !Array.isArray(body)
    ? (body as Record<string, unknown>).action
    : null;
  if (action !== "start" && action !== "restart") {
    return NextResponse.json({ error: "invalid_action" }, { status: 400 });
  }
  try {
    const health = await startPipelineSupervisor({ restart: action === "restart" });
    return NextResponse.json({ health }, { headers: { "Cache-Control": "private, no-store" } });
  } catch (error) {
    const code = error instanceof Error ? error.message : "WORKER_CONTROL_FAILED";
    console.error("pipeline_worker_control_failed", { code });
    return NextResponse.json({ error: "worker_control_failed", code }, { status: 503 });
  }
}
