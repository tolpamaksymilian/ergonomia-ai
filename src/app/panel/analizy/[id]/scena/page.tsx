import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { ArrowLeft, Image as ImageIcon } from "lucide-react";

import { PhotoSceneEditor } from "@/components/photo-scene/photo-scene-editor";
import { normalizeSceneState } from "@/lib/photo-scene/schema";
import { requireUser } from "@/lib/auth/access";
import type { SceneDetection, SceneState } from "@/types/photo-scene";

export const dynamic = "force-dynamic";

export default async function PhotoScenePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { supabase } = await requireUser();
  const { data: analysis, error } = await supabase.from("analyses")
    .select("id,title,analysis_type,status,processing_stage,error_message,source_image_path,heartbeat_at,updated_at,workstation:workstations(name),analysis_category_links(category:analysis_categories(name))")
    .eq("id", id).maybeSingle();
  if (error) throw new Error("Nie udało się pobrać projektu sceny.");
  if (!analysis) notFound();
  if ((analysis.analysis_type ?? "VIDEO") !== "PHOTO_SCENE") redirect(`/panel/analizy/${id}`);

  const { data: scene, error: sceneError } = await supabase.from("photo_scenes")
    .select("scene_state,detection_result,image_width,image_height,detection_error_code,detection_error_message,detection_version,detection_completed_at,detection_attempts,scene_builder_version,last_saved_at,reconstruction_status,reconstruction_error_message")
    .eq("analysis_id", id).maybeSingle();
  if (sceneError) throw new Error("Nie udało się pobrać stanu sceny.");
  if (!scene || !analysis.source_image_path) notFound();
  const { data: signed } = await supabase.storage.from("analysis-scenes").createSignedUrl(analysis.source_image_path, 3600);
  if (!signed?.signedUrl) throw new Error("Nie udało się przygotować prywatnego podglądu zdjęcia.");
  const state: SceneState = normalizeSceneState(scene.scene_state);

  return <main className="ui-page min-h-screen px-3 py-4 sm:px-6">
    <div className="mx-auto max-w-[1800px] space-y-4">
      <header className="ui-surface flex flex-wrap items-center justify-between gap-3 p-4">
        <div className="flex items-center gap-3"><Link href="/panel/analizy" className="ui-button-secondary"><ArrowLeft className="size-4" />Historia</Link><div><p className="text-xs font-bold uppercase tracking-wider text-primary">Projekt ze zdjęcia · Beta</p><h1 className="text-xl font-bold sm:text-2xl">{analysis.title}</h1></div></div>
        <div className="flex items-center gap-2"><span className="hidden rounded-full bg-primary/10 px-3 py-1 text-xs font-semibold text-primary sm:inline-flex"><ImageIcon className="mr-2 size-4" />Scene Builder v0.10 Beta</span></div>
      </header>
      <PhotoSceneEditor
        key={`${id}:${scene.detection_completed_at ?? "pending"}`}
        analysisId={id}
        title={analysis.title}
        imageUrl={signed.signedUrl}
        imageWidth={scene.image_width}
        imageHeight={scene.image_height}
        initialState={state}
        detection={(scene.detection_result as SceneDetection | null) ?? null}
        processingStage={analysis.processing_stage}
        detectionError={scene.detection_error_message ?? analysis.error_message}
        detectionErrorCode={scene.detection_error_code}
        lastSavedAt={scene.last_saved_at}
        analysisHeartbeatAt={analysis.heartbeat_at}
        analysisUpdatedAt={analysis.updated_at}
        detectionCompletedAt={scene.detection_completed_at}
        detectionAttempts={scene.detection_attempts}
        detectionVersion={scene.detection_version}
        sceneBuilderVersion={scene.scene_builder_version}
        reconstructionStatus={scene.reconstruction_status}
        reconstructionError={scene.reconstruction_error_message}
      />
    </div>
  </main>;
}
