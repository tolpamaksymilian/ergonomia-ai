-- Ergonomia AI 0.20.0-beta.1 / Photo Scene Builder v0.9
-- Isolated CPU Scene Reconstruction queue and schema 1.5 metadata.

alter table public.photo_scenes
  drop constraint if exists photo_scenes_schema_version_check;

alter table public.photo_scenes
  add constraint photo_scenes_schema_version_check
  check (scene_schema_version in ('1.0', '1.1', '1.2', '1.3', '1.4', '1.5'));

alter table public.photo_scenes
  add column if not exists reconstruction_status text not null default 'UNSOLVED',
  add column if not exists reconstruction_version text,
  add column if not exists reconstruction_path text,
  add column if not exists reconstruction_input_path text,
  add column if not exists reconstruction_revision text,
  add column if not exists reconstruction_summary jsonb,
  add column if not exists reconstruction_attempts integer not null default 0,
  add column if not exists reconstruction_worker_id text,
  add column if not exists reconstruction_claimed_at timestamptz,
  add column if not exists reconstruction_heartbeat_at timestamptz,
  add column if not exists reconstruction_completed_at timestamptz,
  add column if not exists reconstruction_error_code text,
  add column if not exists reconstruction_error_message text;

alter table public.photo_scenes
  alter column scene_schema_version set default '1.5',
  alter column scene_builder_version set default 'photo-scene-builder-v0.9-beta.1',
  drop constraint if exists photo_scenes_reconstruction_status_check,
  add constraint photo_scenes_reconstruction_status_check check (
    reconstruction_status in ('UNSOLVED', 'QUEUED', 'SOLVING', 'SOLVED', 'PARTIAL', 'UNDERDETERMINED', 'INCONSISTENT', 'FAILED')
  ),
  drop constraint if exists photo_scenes_reconstruction_attempts_check,
  add constraint photo_scenes_reconstruction_attempts_check check (reconstruction_attempts >= 0),
  drop constraint if exists photo_scenes_reconstruction_path_not_empty,
  add constraint photo_scenes_reconstruction_path_not_empty check (reconstruction_path is null or btrim(reconstruction_path) <> ''),
  drop constraint if exists photo_scenes_reconstruction_input_path_not_empty,
  add constraint photo_scenes_reconstruction_input_path_not_empty check (reconstruction_input_path is null or btrim(reconstruction_input_path) <> ''),
  drop constraint if exists photo_scenes_reconstruction_summary_is_object,
  add constraint photo_scenes_reconstruction_summary_is_object check (reconstruction_summary is null or jsonb_typeof(reconstruction_summary) = 'object');

create index if not exists photo_scenes_reconstruction_queue_idx
  on public.photo_scenes (reconstruction_status, updated_at, analysis_id)
  where reconstruction_status = 'QUEUED';

comment on column public.photo_scenes.scene_state is
  'Versioned Photo Scene document. Schema 1.5 adds regions, planes, object faces, a constraint graph and reconstruction state. Legacy 1.0-1.4 documents normalize application-side without converting arbitrary lines into regions.';
comment on column public.photo_scenes.reconstruction_path is
  'Private analysis-scenes path to scene-reconstruction.json; full geometry stays in Storage.';
comment on column public.photo_scenes.reconstruction_summary is
  'Small Scene Reconstruction summary used to refresh scene_state; no source image or complete artifact.';

create or replace function public.request_scene_reconstruction_v1(
  p_analysis_id uuid,
  p_scene_revision text
)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_revision text := btrim(coalesce(p_scene_revision, ''));
begin
  if v_revision = '' then
    raise exception 'Scene revision nie może być pusta.';
  end if;

  update public.photo_scenes s set
    reconstruction_status = 'QUEUED',
    reconstruction_revision = v_revision,
    reconstruction_summary = null,
    reconstruction_worker_id = null,
    reconstruction_claimed_at = null,
    reconstruction_heartbeat_at = null,
    reconstruction_completed_at = null,
    reconstruction_error_code = null,
    reconstruction_error_message = null,
    scene_state = jsonb_set(s.scene_state, '{reconstructionState,status}', '"QUEUED"'::jsonb, true)
  from public.analyses a
  where s.analysis_id = p_analysis_id
    and a.id = s.analysis_id
    and a.analysis_type = 'PHOTO_SCENE'
    and (a.user_id = (select auth.uid()) or (select public.is_admin()))
    and jsonb_typeof(s.scene_state) = 'object'
    and (
      coalesce(jsonb_array_length(s.scene_state -> 'regions'), 0) > 0
      or coalesce(jsonb_array_length(s.scene_state #> '{constraintGraph,constraints}'), 0) > 0
      or coalesce(jsonb_array_length(s.scene_state #> '{calibration,references}'), 0) > 0
    );
  return found;
end;
$$;

create or replace function public.claim_next_scene_reconstruction(
  p_worker_id text
)
returns table (
  id uuid,
  user_id uuid,
  title text,
  scene_state jsonb,
  detection_result jsonb,
  image_width integer,
  image_height integer,
  scene_revision text,
  attempts integer,
  worker_id text
)
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_worker_id text := btrim(coalesce(p_worker_id, ''));
begin
  if v_worker_id = '' then raise exception 'Worker ID nie może być pusty.'; end if;
  return query
  with next_scene as (
    select s.analysis_id
    from public.photo_scenes s
    join public.analyses a on a.id = s.analysis_id
    where a.analysis_type = 'PHOTO_SCENE'
      and s.reconstruction_status = 'QUEUED'
      and s.reconstruction_worker_id is null
      and s.reconstruction_revision is not null
      and jsonb_typeof(s.scene_state) = 'object'
    order by s.updated_at, s.analysis_id
    for update of s skip locked
    limit 1
  )
  update public.photo_scenes s set
    reconstruction_status = 'SOLVING',
    reconstruction_worker_id = v_worker_id,
    reconstruction_attempts = s.reconstruction_attempts + 1,
    reconstruction_claimed_at = now(),
    reconstruction_heartbeat_at = now(),
    reconstruction_error_code = null,
    reconstruction_error_message = null,
    scene_state = jsonb_set(s.scene_state, '{reconstructionState,status}', '"SOLVING"'::jsonb, true)
  from next_scene, public.analyses a
  where s.analysis_id = next_scene.analysis_id and a.id = s.analysis_id
  returning
    s.analysis_id::uuid,
    s.user_id::uuid,
    a.title::text,
    s.scene_state::jsonb,
    s.detection_result::jsonb,
    s.image_width::integer,
    s.image_height::integer,
    s.reconstruction_revision::text,
    s.reconstruction_attempts::integer,
    s.reconstruction_worker_id::text;
end;
$$;

create or replace function public.complete_scene_reconstruction_v1(
  p_analysis_id uuid,
  p_worker_id text,
  p_input_path text,
  p_result_path text,
  p_reconstruction_version text,
  p_scene_revision text,
  p_result_status text,
  p_reconstruction_summary jsonb
)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_status text := upper(btrim(coalesce(p_result_status, '')));
begin
  if v_status not in ('SOLVED', 'PARTIAL', 'UNDERDETERMINED', 'INCONSISTENT') then
    raise exception 'Nieprawidłowy końcowy status rekonstrukcji.';
  end if;
  if jsonb_typeof(p_reconstruction_summary) <> 'object'
     or jsonb_typeof(p_reconstruction_summary -> 'reconstructionState') <> 'object' then
    raise exception 'Reconstruction summary musi zawierać reconstructionState.';
  end if;

  update public.photo_scenes s set
    reconstruction_status = v_status,
    reconstruction_version = nullif(btrim(p_reconstruction_version), ''),
    reconstruction_input_path = nullif(btrim(p_input_path), ''),
    reconstruction_path = nullif(btrim(p_result_path), ''),
    reconstruction_revision = btrim(p_scene_revision),
    reconstruction_summary = p_reconstruction_summary,
    reconstruction_completed_at = now(),
    reconstruction_worker_id = null,
    reconstruction_claimed_at = null,
    reconstruction_heartbeat_at = null,
    reconstruction_error_code = null,
    reconstruction_error_message = null,
    scene_schema_version = '1.5',
    scene_builder_version = 'photo-scene-builder-v0.9-beta.1',
    scene_state = s.scene_state
      || jsonb_build_object(
        'schema_version', '1.5',
        'reconstructionState', p_reconstruction_summary -> 'reconstructionState',
        'planes', coalesce(p_reconstruction_summary -> 'planes', '[]'::jsonb)
      )
  where s.analysis_id = p_analysis_id
    and s.reconstruction_status = 'SOLVING'
    and s.reconstruction_worker_id = btrim(p_worker_id)
    and s.reconstruction_revision = btrim(p_scene_revision);
  return found;
end;
$$;

create or replace function public.heartbeat_scene_reconstruction(
  p_analysis_id uuid,
  p_worker_id text
)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
begin
  update public.photo_scenes s set reconstruction_heartbeat_at = now()
  where s.analysis_id = p_analysis_id
    and s.reconstruction_status = 'SOLVING'
    and s.reconstruction_worker_id = btrim(p_worker_id);
  return found;
end;
$$;

create or replace function public.fail_scene_reconstruction(
  p_analysis_id uuid,
  p_worker_id text,
  p_error_code text,
  p_error_message text
)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
begin
  update public.photo_scenes s set
    reconstruction_status = 'FAILED',
    reconstruction_worker_id = null,
    reconstruction_claimed_at = null,
    reconstruction_heartbeat_at = null,
    reconstruction_error_code = left(coalesce(nullif(btrim(p_error_code), ''), 'SCENE_RECONSTRUCTION_FAILED'), 120),
    reconstruction_error_message = left(coalesce(nullif(btrim(p_error_message), ''), 'Nie udało się obliczyć geometrii sceny.'), 2000),
    scene_state = jsonb_set(s.scene_state, '{reconstructionState,status}', '"FAILED"'::jsonb, true)
  where s.analysis_id = p_analysis_id
    and s.reconstruction_status = 'SOLVING'
    and s.reconstruction_worker_id = btrim(p_worker_id);
  return found;
end;
$$;

create or replace function public.retry_scene_reconstruction_v1(
  p_analysis_id uuid
)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
begin
  update public.photo_scenes s set
    reconstruction_status = 'QUEUED',
    reconstruction_worker_id = null,
    reconstruction_claimed_at = null,
    reconstruction_heartbeat_at = null,
    reconstruction_error_code = null,
    reconstruction_error_message = null,
    scene_state = jsonb_set(s.scene_state, '{reconstructionState,status}', '"QUEUED"'::jsonb, true)
  from public.analyses a
  where s.analysis_id = p_analysis_id
    and a.id = s.analysis_id
    and (a.user_id = (select auth.uid()) or (select public.is_admin()))
    and s.reconstruction_status in ('FAILED', 'PARTIAL', 'UNDERDETERMINED', 'INCONSISTENT', 'SOLVED');
  return found;
end;
$$;

create or replace function public.check_scene_reconstruction_readiness_v1()
returns jsonb
language sql
security definer
set search_path = ''
as $$
  select jsonb_build_object(
    'ready',
      to_regprocedure('public.claim_next_scene_reconstruction(text)') is not null
      and to_regprocedure('public.complete_scene_reconstruction_v1(uuid,text,text,text,text,text,text,jsonb)') is not null
      and to_regprocedure('public.fail_scene_reconstruction(uuid,text,text,text)') is not null
      and (select count(*) = 14 from information_schema.columns where table_schema = 'public' and table_name = 'photo_scenes' and column_name in (
        'reconstruction_status', 'reconstruction_version', 'reconstruction_path', 'reconstruction_input_path',
        'reconstruction_revision', 'reconstruction_summary', 'reconstruction_attempts', 'reconstruction_worker_id',
        'reconstruction_claimed_at', 'reconstruction_heartbeat_at', 'reconstruction_completed_at',
        'reconstruction_error_code', 'reconstruction_error_message', 'scene_schema_version'
      ))
      and exists (select 1 from storage.buckets where id = 'analysis-scenes' and public = false),
    'schema_version', '1.5',
    'bucket_private', exists (select 1 from storage.buckets where id = 'analysis-scenes' and public = false)
  );
$$;

revoke all on function public.request_scene_reconstruction_v1(uuid, text) from public, anon;
revoke all on function public.request_scene_reconstruction_v1(uuid, text) from authenticated;
grant execute on function public.request_scene_reconstruction_v1(uuid, text) to authenticated;

revoke all on function public.retry_scene_reconstruction_v1(uuid) from public, anon;
revoke all on function public.retry_scene_reconstruction_v1(uuid) from authenticated;
grant execute on function public.retry_scene_reconstruction_v1(uuid) to authenticated;

revoke all on function public.claim_next_scene_reconstruction(text) from public, anon, authenticated;
revoke all on function public.complete_scene_reconstruction_v1(uuid, text, text, text, text, text, text, jsonb) from public, anon, authenticated;
revoke all on function public.fail_scene_reconstruction(uuid, text, text, text) from public, anon, authenticated;
revoke all on function public.heartbeat_scene_reconstruction(uuid, text) from public, anon, authenticated;
revoke all on function public.check_scene_reconstruction_readiness_v1() from public, anon, authenticated;
grant execute on function public.claim_next_scene_reconstruction(text) to service_role;
grant execute on function public.complete_scene_reconstruction_v1(uuid, text, text, text, text, text, text, jsonb) to service_role;
grant execute on function public.fail_scene_reconstruction(uuid, text, text, text) to service_role;
grant execute on function public.heartbeat_scene_reconstruction(uuid, text) to service_role;
grant execute on function public.check_scene_reconstruction_readiness_v1() to service_role;

notify pgrst, 'reload schema';
