import { NextResponse } from "next/server";

import { requireUser } from "@/lib/auth/access";
import { validateSceneState } from "@/lib/photo-scene/schema";

export async function PATCH(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { supabase } = await requireUser();
  if (!/^[0-9a-f]{8}-[0-9a-f-]{27}$/i.test(id)) return NextResponse.json({ error: "Nieprawidłowy identyfikator." }, { status: 400 });
  let body: unknown;
  try { body = await request.json(); } catch { return NextResponse.json({ error: "Nieprawidłowy JSON." }, { status: 400 }); }
  const state = (body as { scene_state?: unknown } | null)?.scene_state;
  if (!validateSceneState(state)) return NextResponse.json({ error: "Nieprawidłowy stan sceny." }, { status: 422 });
  const { error } = await supabase.from("photo_scenes").update({
    scene_state: state,
    scene_schema_version: "1.1",
    scene_builder_version: "photo-scene-builder-v0.2-beta.1",
    last_saved_at: new Date().toISOString(),
  }).eq("analysis_id", id);
  if (error) return NextResponse.json({ error: "Nie udało się zapisać sceny." }, { status: 500 });
  return NextResponse.json({ saved: true, saved_at: new Date().toISOString() });
}

export async function POST(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { supabase } = await requireUser();
  if (!/^[0-9a-f]{8}-[0-9a-f-]{27}$/i.test(id)) return NextResponse.json({ error: "Nieprawidłowy identyfikator." }, { status: 400 });
  const { data, error } = await supabase.rpc("retry_scene_detection", { p_analysis_id: id });
  if (error || data !== true) return NextResponse.json({ error: "Nie można ponowić detekcji w bieżącym stanie." }, { status: 409 });
  return NextResponse.json({ queued: true });
}
