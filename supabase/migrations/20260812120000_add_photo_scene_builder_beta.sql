-- Ergonomia AI v0.12.0-beta.1
-- Photo Scenario Builder v0.1 beta: separate PHOTO_SCENE flow.

alter table public.analyses
  add column analysis_type text not null default 'VIDEO',
  add column source_image_path text,
  add constraint analyses_analysis_type_check
    check (analysis_type in ('VIDEO', 'PHOTO_SCENE')),
  add constraint analyses_source_image_path_not_blank
    check (source_image_path is null or length(btrim(source_image_path)) > 0),
  add constraint analyses_photo_source_shape
    check (
      (analysis_type = 'VIDEO' and source_video_path is not null and source_image_path is null)
      or
      (analysis_type = 'PHOTO_SCENE' and source_video_path is null and source_image_path is not null)
    );

alter table public.analyses alter column source_video_path drop not null;
alter table public.analyses drop constraint if exists analyses_storage_path_matches_id;
alter table public.analyses add constraint analyses_storage_path_matches_id check (
  (analysis_type = 'VIDEO' and source_video_path like user_id::text || '/' || id::text || '/source/%')
  or
  (analysis_type = 'PHOTO_SCENE' and source_image_path like user_id::text || '/' || id::text || '/source/%')
);

create unique index analyses_source_image_path_uidx
on public.analyses (source_image_path)
where source_image_path is not null;

create index analyses_owner_type_created_idx
on public.analyses (user_id, analysis_type, created_at desc);

create index analyses_photo_scene_claim_idx
on public.analyses (queued_at, created_at)
where analysis_type = 'PHOTO_SCENE'
  and processing_stage = 'ready-for-scene-detection'
  and worker_id is null;

create table public.photo_scenes (
  analysis_id uuid primary key references public.analyses(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  scene_schema_version text not null default '1.0',
  scene_builder_version text not null default 'scene-builder-v0.1-beta.1',
  detection_version text,
  original_image_path text not null,
  preview_image_path text,
  detection_result_path text,
  image_width integer not null check (image_width > 0),
  image_height integer not null check (image_height > 0),
  image_orientation integer not null default 1 check (image_orientation between 1 and 8),
  scene_state jsonb not null default '{"schema_version":"1.0","objects":[],"calibration":{"status":"UNCALIBRATED","anchors":[]},"human":null,"pose":null,"viewport":{"zoom":1,"pan_x":0,"pan_y":0}}'::jsonb,
  detection_result jsonb,
  detection_attempts integer not null default 0 check (detection_attempts >= 0),
  detection_error_code text,
  detection_error_message text,
  detection_completed_at timestamptz,
  last_saved_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint photo_scenes_owner_fk foreign key (analysis_id, user_id)
    references public.analyses(id, user_id) on delete cascade,
  constraint photo_scenes_schema_version_check check (scene_schema_version = '1.0'),
  constraint photo_scenes_state_is_object check (jsonb_typeof(scene_state) = 'object'),
  constraint photo_scenes_detection_is_object check (detection_result is null or jsonb_typeof(detection_result) = 'object'),
  constraint photo_scenes_original_path_matches_owner check (
    original_image_path like user_id::text || '/' || analysis_id::text || '/source/%'
  )
);

create index photo_scenes_owner_updated_idx on public.photo_scenes (user_id, updated_at desc);

create trigger set_photo_scenes_updated_at
before update on public.photo_scenes
for each row execute procedure public.set_analysis_updated_at();

alter table public.photo_scenes enable row level security;
revoke all on table public.photo_scenes from anon, authenticated;
grant select, delete on table public.photo_scenes to authenticated;
grant update (scene_state, last_saved_at) on table public.photo_scenes to authenticated;

create policy "Users can read own photo scenes"
on public.photo_scenes for select to authenticated
using (user_id = (select auth.uid()) or (select public.is_admin()));

create policy "Users can create own photo scenes"
on public.photo_scenes for insert to authenticated
with check (user_id = (select auth.uid()));

create policy "Users can update own photo scenes"
on public.photo_scenes for update to authenticated
using (user_id = (select auth.uid()) or (select public.is_admin()))
with check (user_id = (select auth.uid()) or (select public.is_admin()));

create policy "Users can delete own photo scenes"
on public.photo_scenes for delete to authenticated
using (user_id = (select auth.uid()) or (select public.is_admin()));

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'analysis-scenes', 'analysis-scenes', false, 20971520,
  array['image/jpeg', 'image/png', 'image/webp']
)
on conflict (id) do update set
  public = false,
  file_size_limit = excluded.file_size_limit,
  allowed_mime_types = excluded.allowed_mime_types;

create policy "Users can upload own analysis scenes"
on storage.objects for insert to authenticated
with check (
  bucket_id = 'analysis-scenes'
  and (storage.foldername(name))[1] = (select auth.uid())::text
);

create policy "Users can read own analysis scenes"
on storage.objects for select to authenticated
using (
  bucket_id = 'analysis-scenes'
  and ((storage.foldername(name))[1] = (select auth.uid())::text or (select public.is_admin()))
);

create policy "Users can update own analysis scenes"
on storage.objects for update to authenticated
using (
  bucket_id = 'analysis-scenes'
  and ((storage.foldername(name))[1] = (select auth.uid())::text or (select public.is_admin()))
)
with check (
  bucket_id = 'analysis-scenes'
  and ((storage.foldername(name))[1] = (select auth.uid())::text or (select public.is_admin()))
);

create policy "Users can delete own analysis scenes"
on storage.objects for delete to authenticated
using (
  bucket_id = 'analysis-scenes'
  and ((storage.foldername(name))[1] = (select auth.uid())::text or (select public.is_admin()))
);

drop policy if exists "Users can create own uploading analyses" on public.analyses;
create policy "Users can create own uploading analyses"
on public.analyses for insert to authenticated
with check (
  (select auth.uid()) is not null
  and user_id = (select auth.uid())
  and status = 'uploading'::public.analysis_status
  and progress = 0
  and (
    (analysis_type = 'VIDEO' and source_video_path like (select auth.uid())::text || '/' || id::text || '/source/%')
    or
    (analysis_type = 'PHOTO_SCENE' and source_image_path like (select auth.uid())::text || '/' || id::text || '/source/%')
  )
);

create or replace function public.finalize_photo_scene_upload(
  p_analysis_id uuid,
  p_image_width integer,
  p_image_height integer,
  p_image_orientation integer default 1
)
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_analysis public.analyses%rowtype;
begin
  if p_image_width <= 0 or p_image_height <= 0 or p_image_orientation not between 1 and 8 then
    raise exception 'Nieprawidłowe parametry obrazu.';
  end if;

  select * into v_analysis
  from public.analyses
  where id = p_analysis_id
    and user_id = (select auth.uid())
    and analysis_type = 'PHOTO_SCENE'
    and status = 'uploading'::public.analysis_status
  for update;

  if v_analysis.id is null then
    raise exception 'Nie znaleziono projektu oczekującego na ukończenie uploadu.';
  end if;

  if not exists (
    select 1 from storage.objects
    where bucket_id = 'analysis-scenes' and name = v_analysis.source_image_path
  ) then
    raise exception 'Oryginalne zdjęcie nie zostało odnalezione w Storage.';
  end if;

  insert into public.photo_scenes (
    analysis_id, user_id, original_image_path, image_width, image_height, image_orientation
  ) values (
    v_analysis.id, v_analysis.user_id, v_analysis.source_image_path,
    p_image_width, p_image_height, p_image_orientation
  );

  update public.analyses set
    status = 'queued'::public.analysis_status,
    progress = 10,
    processing_stage = 'ready-for-scene-detection',
    queued_at = now(),
    error_code = null,
    error_message = null
  where id = v_analysis.id;
end;
$$;

create or replace function public.claim_next_scene_analysis(p_worker_id text)
returns table (
  id uuid, user_id uuid, title text, source_image_path text,
  source_file_name text, source_mime_type text, source_size_bytes bigint,
  image_width integer, image_height integer, attempts integer, worker_id text
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
  with next_analysis as (
    select a.id
    from public.analyses a
    where a.analysis_type = 'PHOTO_SCENE'
      and a.status = 'queued'::public.analysis_status
      and a.processing_stage = 'ready-for-scene-detection'
      and a.source_image_path is not null
      and a.worker_id is null
    order by coalesce(a.queued_at, a.created_at), a.id
    for update skip locked
    limit 1
  )
  update public.analyses a set
    status = 'processing'::public.analysis_status,
    progress = 20,
    processing_stage = 'scene-detection-processing',
    worker_id = v_worker_id,
    attempts = coalesce(a.attempts, 0) + 1,
    claimed_at = now(),
    heartbeat_at = now(),
    started_at = coalesce(a.started_at, now()),
    error_code = null,
    error_message = null
  from next_analysis, public.photo_scenes s
  where a.id = next_analysis.id and s.analysis_id = a.id
  returning
    a.id::uuid, a.user_id::uuid, a.title::text, a.source_image_path::text,
    a.source_file_name::text, a.source_mime_type::text, a.source_size_bytes::bigint,
    s.image_width::integer, s.image_height::integer, a.attempts::integer, a.worker_id::text;
end;
$$;

create or replace function public.complete_scene_detection_v1(
  p_analysis_id uuid,
  p_worker_id text,
  p_detection_result_path text,
  p_preview_image_path text,
  p_detection_result jsonb,
  p_detection_version text
)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
begin
  if jsonb_typeof(p_detection_result) <> 'object' then raise exception 'Detection result musi być obiektem JSON.'; end if;
  update public.photo_scenes s set
    detection_result_path = nullif(btrim(p_detection_result_path), ''),
    preview_image_path = nullif(btrim(p_preview_image_path), ''),
    detection_result = p_detection_result,
    detection_version = nullif(btrim(p_detection_version), ''),
    detection_attempts = detection_attempts + 1,
    detection_error_code = null,
    detection_error_message = null,
    detection_completed_at = now()
  from public.analyses a
  where s.analysis_id = p_analysis_id and a.id = s.analysis_id
    and a.analysis_type = 'PHOTO_SCENE'
    and a.processing_stage = 'scene-detection-processing'
    and a.worker_id = btrim(p_worker_id);
  if not found then return false; end if;
  update public.analyses set
    status = 'completed'::public.analysis_status,
    progress = 100,
    processing_stage = 'scene-ready',
    worker_id = null,
    heartbeat_at = null,
    processing_completed_at = now(),
    thumbnail_path = nullif(btrim(p_preview_image_path), ''),
    error_code = null,
    error_message = null
  where id = p_analysis_id and worker_id = btrim(p_worker_id)
    and processing_stage = 'scene-detection-processing';
  return found;
end;
$$;

create or replace function public.fail_scene_detection(
  p_analysis_id uuid, p_worker_id text, p_error_code text, p_error_message text
)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
begin
  update public.analyses set
    status = 'failed'::public.analysis_status,
    progress = 20,
    processing_stage = 'scene-detection-failed',
    worker_id = null,
    heartbeat_at = null,
    error_code = left(coalesce(nullif(btrim(p_error_code), ''), 'SCENE_DETECTION_FAILED'), 120),
    error_message = left(coalesce(nullif(btrim(p_error_message), ''), 'Detekcja elementów nie powiodła się.'), 2000)
  where id = p_analysis_id and analysis_type = 'PHOTO_SCENE'
    and processing_stage = 'scene-detection-processing' and worker_id = btrim(p_worker_id);
  if found then
    update public.photo_scenes set
      detection_attempts = detection_attempts + 1,
      detection_error_code = left(coalesce(nullif(btrim(p_error_code), ''), 'SCENE_DETECTION_FAILED'), 120),
      detection_error_message = left(coalesce(nullif(btrim(p_error_message), ''), 'Detekcja elementów nie powiodła się.'), 2000)
    where analysis_id = p_analysis_id;
  end if;
  return found;
end;
$$;

create or replace function public.retry_scene_detection(p_analysis_id uuid)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
begin
  update public.analyses set
    status = 'queued'::public.analysis_status,
    progress = 10,
    processing_stage = 'ready-for-scene-detection',
    worker_id = null,
    claimed_at = null,
    heartbeat_at = null,
    queued_at = now(),
    error_code = null,
    error_message = null
  where id = p_analysis_id and analysis_type = 'PHOTO_SCENE'
    and (user_id = (select auth.uid()) or (select public.is_admin()))
    and processing_stage = 'scene-detection-failed';
  return found;
end;
$$;

-- Video preprocessing remains an independent queue and cannot claim PHOTO_SCENE.
create or replace function public.claim_next_analysis(p_worker_id text)
returns table (
  id uuid, user_id uuid, title text, status public.analysis_status,
  progress integer, source_video_path text, source_file_name text,
  source_mime_type text, source_size_bytes bigint, attempts integer, worker_id text
)
language plpgsql
security definer
set search_path = ''
as $$
declare v_worker_id text := btrim(coalesce(p_worker_id, ''));
begin
  if v_worker_id = '' then raise exception 'Worker ID nie może być pusty.'; end if;
  return query
  with next_analysis as (
    select a.id from public.analyses a
    where a.analysis_type = 'VIDEO'
      and a.status = 'queued'::public.analysis_status
      and coalesce(a.processing_stage, 'queued') in ('queued', 'retry')
    order by coalesce(a.queued_at, a.created_at), a.created_at, a.id
    for update skip locked limit 1
  )
  update public.analyses a set
    status = 'processing'::public.analysis_status,
    progress = 1, worker_id = v_worker_id,
    attempts = coalesce(a.attempts, 0) + 1,
    claimed_at = now(), heartbeat_at = now(),
    started_at = coalesce(a.started_at, now()),
    processing_stage = 'claimed-for-preprocessing',
    error_code = null, error_message = null
  from next_analysis
  where a.id = next_analysis.id and a.analysis_type = 'VIDEO'
  returning a.id::uuid, a.user_id::uuid, a.title::text,
    a.status::public.analysis_status, a.progress::integer,
    a.source_video_path::text, a.source_file_name::text,
    a.source_mime_type::text, a.source_size_bytes::bigint,
    a.attempts::integer, a.worker_id::text;
end;
$$;

revoke all on function public.finalize_photo_scene_upload(uuid, integer, integer, integer) from public, anon;
grant execute on function public.finalize_photo_scene_upload(uuid, integer, integer, integer) to authenticated;
revoke all on function public.retry_scene_detection(uuid) from public, anon;
grant execute on function public.retry_scene_detection(uuid) to authenticated;

revoke all on function public.claim_next_scene_analysis(text) from public, anon, authenticated;
revoke all on function public.complete_scene_detection_v1(uuid, text, text, text, jsonb, text) from public, anon, authenticated;
revoke all on function public.fail_scene_detection(uuid, text, text, text) from public, anon, authenticated;
grant execute on function public.claim_next_scene_analysis(text) to service_role;
grant execute on function public.complete_scene_detection_v1(uuid, text, text, text, jsonb, text) to service_role;
grant execute on function public.fail_scene_detection(uuid, text, text, text) to service_role;

revoke all on function public.claim_next_analysis(text) from public, anon, authenticated;
grant execute on function public.claim_next_analysis(text) to service_role;

create or replace function public.check_photo_scene_readiness_v01()
returns jsonb
language sql
security definer
set search_path = ''
as $$
  select jsonb_build_object(
    'ready',
      to_regclass('public.photo_scenes') is not null
      and exists (select 1 from storage.buckets where id = 'analysis-scenes' and public = false)
      and to_regprocedure('public.claim_next_scene_analysis(text)') is not null
      and to_regprocedure('public.complete_scene_detection_v1(uuid,text,text,text,jsonb,text)') is not null,
    'bucket_private', exists (select 1 from storage.buckets where id = 'analysis-scenes' and public = false),
    'table_ready', to_regclass('public.photo_scenes') is not null,
    'claim_ready', to_regprocedure('public.claim_next_scene_analysis(text)') is not null
  );
$$;

revoke all on function public.check_photo_scene_readiness_v01() from public, anon, authenticated;
grant execute on function public.check_photo_scene_readiness_v01() to service_role;

notify pgrst, 'reload schema';
