-- Photo Scene Builder v0.2: versioned evolution without rewriting existing user JSON.
-- Scene 1.0 remains readable and is normalized to 1.1 by the application on load.

alter table public.photo_scenes
  drop constraint if exists photo_scenes_schema_version_check;

alter table public.photo_scenes
  add constraint photo_scenes_schema_version_check
  check (scene_schema_version in ('1.0', '1.1'));

alter table public.photo_scenes
  alter column scene_schema_version set default '1.1',
  alter column scene_builder_version set default 'photo-scene-builder-v0.2-beta.1';

grant update (scene_state, scene_schema_version, scene_builder_version, last_saved_at)
on table public.photo_scenes to authenticated;

comment on column public.photo_scenes.scene_state is
  'Versioned Photo Scene Builder document. Schema 1.0 is normalized application-side to 1.1 before its next save.';

notify pgrst, 'reload schema';
