import { createHash } from "node:crypto";

import { NextResponse } from "next/server";

import { requireUser } from "@/lib/auth/access";
import { normalizeSceneState, validateSceneState } from "@/lib/photo-scene/schema";

export async function POST(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!/^[0-9a-f]{8}-[0-9a-f-]{27}$/i.test(id)) return NextResponse.json({ error: "Nieprawidłowy identyfikator." }, { status: 400 });
  const { supabase } = await requireUser();
  const { data, error } = await supabase.from("photo_scenes").select("scene_state").eq("analysis_id", id).maybeSingle();
  if (error) return NextResponse.json({ error: "Nie udało się odczytać zapisanej sceny." }, { status: 500 });
  if (!data) return NextResponse.json({ error: "Nie znaleziono sceny." }, { status: 404 });
  const state = normalizeSceneState(data.scene_state);
  if (!validateSceneState(state)) return NextResponse.json({ error: "Stan sceny nie spełnia kontraktu 1.5." }, { status: 422 });
  const hasInput = state.regions.length > 0 || state.constraintGraph.constraints.length > 0 || state.calibration.references.length > 0;
  if (!hasInput) return NextResponse.json({ error: "Najpierw zaznacz obszar albo dodaj rzeczywisty wymiar." }, { status: 422 });
  const geometryInput = {
    schemaVersion: state.schema_version,
    regions: state.regions,
    objects: state.objects,
    objectFaces: state.objectFaces,
    planes: state.planes,
    calibration: state.calibration,
    constraintGraph: state.constraintGraph,
  };
  const revision = createHash("sha256").update(JSON.stringify(geometryInput)).digest("hex");
  const { data: queued, error: rpcError } = await supabase.rpc("request_scene_reconstruction_v1", { p_analysis_id: id, p_scene_revision: revision });
  if (rpcError) return NextResponse.json({ error: "Nie udało się dodać rekonstrukcji do kolejki." }, { status: 500 });
  if (queued !== true) return NextResponse.json({ error: "Scena nie zawiera danych możliwych do obliczenia albo nie jest dostępna." }, { status: 409 });
  return NextResponse.json({ queued: true, scene_revision: revision });
}
