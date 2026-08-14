-- Photo Scene Builder v0.8: versioned Scene Ergonomics artifacts remain in the
-- existing private analysis-scenes bucket. Only searchable metadata is stored.

alter table public.photo_scenes
  add column if not exists scene_assessment_path text,
  add column if not exists scene_assessment_version text,
  add column if not exists scene_assessment_revision text,
  add column if not exists scene_assessment_summary jsonb,
  add column if not exists scene_assessed_at timestamptz;

alter table public.photo_scenes
  alter column scene_builder_version set default 'photo-scene-builder-v0.8-beta.1';

alter table public.photo_scenes
  drop constraint if exists photo_scenes_assessment_path_not_empty,
  add constraint photo_scenes_assessment_path_not_empty
    check (scene_assessment_path is null or btrim(scene_assessment_path) <> ''),
  drop constraint if exists photo_scenes_assessment_summary_is_object,
  add constraint photo_scenes_assessment_summary_is_object
    check (scene_assessment_summary is null or jsonb_typeof(scene_assessment_summary) = 'object');

grant update (
  scene_assessment_path,
  scene_assessment_version,
  scene_assessment_revision,
  scene_assessment_summary,
  scene_assessed_at
) on table public.photo_scenes to authenticated;

comment on column public.photo_scenes.scene_assessment_path is
  'Private analysis-scenes Storage path for scene-ergonomic-assessment-v1.0.';
comment on column public.photo_scenes.scene_assessment_summary is
  'Small indexable Scene Ergonomics summary; full evidence remains in Storage.';

notify pgrst, 'reload schema';
