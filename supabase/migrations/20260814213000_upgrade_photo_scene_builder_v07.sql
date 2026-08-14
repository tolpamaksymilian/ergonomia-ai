-- Ergonomia AI 0.18.0-beta.1 / Photo Scene Builder v0.7
-- Physical 3D state remains inside the existing private scene_state JSON.

alter table public.photo_scenes
  drop constraint if exists photo_scenes_schema_version_check;

alter table public.photo_scenes
  add constraint photo_scenes_schema_version_check
  check (scene_schema_version in ('1.0', '1.1', '1.2', '1.3', '1.4'));

alter table public.photo_scenes
  alter column scene_schema_version set default '1.4',
  alter column scene_builder_version set default 'photo-scene-builder-v0.7-beta.1';

comment on column public.photo_scenes.scene_state is
  'Versioned physical Photo Scene state. Schema 1.4 adds centimeter-based 3D humans, hands, objects, interactions, reachability, collisions, and kinematic motion definitions. Older schemas normalize application-side.';

notify pgrst, 'reload schema';
