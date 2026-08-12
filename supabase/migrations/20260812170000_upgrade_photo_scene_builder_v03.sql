-- Photo Scene Builder v0.3 stores perspective-aware scene documents as schema 1.2.
-- Existing 1.0 and 1.1 JSON remains accepted and is normalized application-side.

alter table public.photo_scenes
  drop constraint if exists photo_scenes_schema_version_check;

alter table public.photo_scenes
  add constraint photo_scenes_schema_version_check
  check (scene_schema_version in ('1.0', '1.1', '1.2'));

alter table public.photo_scenes
  alter column scene_schema_version set default '1.2',
  alter column scene_builder_version set default 'photo-scene-builder-v0.3-beta.1';

comment on column public.photo_scenes.scene_state is
  'Versioned Photo Scene Builder document. Schemas 1.0 and 1.1 are normalized application-side to 1.2 before their next save.';

notify pgrst, 'reload schema';
