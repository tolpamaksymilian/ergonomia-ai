import { createHash } from "node:crypto";

import { NextResponse } from "next/server";

import { requireUser } from "@/lib/auth/access";
import { buildGuidedWorkerContext, deriveGuidedSetupStatus } from "@/lib/photo-scene/guided-setup";
import { normalizeSceneState, validateSceneState } from "@/lib/photo-scene/schema";

export async function POST(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!/^[0-9a-f]{8}-[0-9a-f-]{27}$/i.test(id)) return NextResponse.json({ error: "Nieprawidłowy identyfikator." }, { status: 400 });
  const { supabase } = await requireUser();
  const { data, error } = await supabase.from("photo_scenes")
    .select("scene_state,original_image_path,image_width,image_height")
    .eq("analysis_id", id)
    .maybeSingle();
  if (error) return NextResponse.json({ error: "Nie udało się odczytać zapisanej sceny." }, { status: 500 });
  if (!data) return NextResponse.json({ error: "Nie znaleziono sceny." }, { status: 404 });
  const state = normalizeSceneState(data.scene_state);
  if (!validateSceneState(state)) return NextResponse.json({ error: "Stan sceny nie spełnia kontraktu 1.5." }, { status: 422 });
  const readiness = deriveGuidedSetupStatus(state);
  if (!readiness.canBuild) return NextResponse.json({ error: "Dodaj podłogę, pole pracy i minimum dwie poprawne wysokości." }, { status: 422 });

  const contextWithoutRevision = buildGuidedWorkerContext(state, {
    width: data.image_width,
    height: data.image_height,
    storagePath: data.original_image_path,
  }, null);
  const revision = createHash("sha256").update(JSON.stringify(contextWithoutRevision)).digest("hex");
  const { data: queued, error: rpcError } = await supabase.rpc("request_guided_scene_build_v1", {
    p_analysis_id: id,
    p_scene_revision: revision,
  });
  if (rpcError) return NextResponse.json({ error: "Nie udało się dodać budowania sceny do kolejki." }, { status: 500 });
  if (queued !== true) return NextResponse.json({ error: "Scena zmieniła stan albo nie spełnia minimalnych wymagań." }, { status: 409 });
  return NextResponse.json({ queued: true, scene_revision: revision });
}
