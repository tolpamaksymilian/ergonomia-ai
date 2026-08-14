-- Ergonomia AI 0.17.0-beta.1
-- Photo Scene Builder v0.6 stores Measurement Semantics V2 and Calibration V3 in scene_state.
-- Existing 1.0-1.2 documents remain readable and are normalized application-side before the next save.

alter table public.photo_scenes
  drop constraint if exists photo_scenes_schema_version_check;

alter table public.photo_scenes
  add constraint photo_scenes_schema_version_check
  check (scene_schema_version in ('1.0', '1.1', '1.2', '1.3'));

alter table public.photo_scenes
  alter column scene_schema_version set default '1.3',
  alter column scene_builder_version set default 'photo-scene-builder-v0.6-beta.1';

comment on column public.photo_scenes.scene_state is
  'Versioned Photo Scene Builder document. Schemas 1.0-1.2 are normalized application-side to 1.3. Legacy measurements require explicit semantic review before Calibration V3 can use them.';

notify pgrst, 'reload schema';
