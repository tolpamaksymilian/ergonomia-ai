-- Ergonomia AI 0.21.0-beta.1 / Guided Scene Setup v1.
-- New PHOTO_SCENE uploads wait for user annotations. A single authenticated request
-- atomically queues detection; successful detection then queues existing reconstruction.

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
    analysis_id, user_id, original_image_path, image_width, image_height, image_orientation,
    scene_schema_version, scene_builder_version
  ) values (
    v_analysis.id, v_analysis.user_id, v_analysis.source_image_path,
    p_image_width, p_image_height, p_image_orientation,
    '1.5', 'photo-scene-builder-v0.10-beta.1'
  );

  update public.analyses set
    status = 'draft'::public.analysis_status,
    progress = 10,
    processing_stage = 'photo-scene-setup',
    queued_at = null,
    error_code = null,
    error_message = null
  where id = v_analysis.id;
end;
$$;

create or replace function public.request_guided_scene_build_v1(
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
  v_state jsonb;
  v_height_count integer := 0;
  v_has_floor boolean := false;
  v_has_movement boolean := false;
begin
  if v_revision = '' then raise exception 'Scene revision nie może być pusta.'; end if;

  select s.scene_state into v_state
  from public.photo_scenes s
  join public.analyses a on a.id = s.analysis_id
  where s.analysis_id = p_analysis_id
    and a.analysis_type = 'PHOTO_SCENE'
    and a.source_image_path is not null
    and (a.user_id = (select auth.uid()) or (select public.is_admin()))
    and a.worker_id is null
    and coalesce(a.processing_stage, 'photo-scene-setup') not in ('scene-detection-processing')
    and s.reconstruction_status not in ('QUEUED', 'SOLVING')
  for update of a, s;

  if v_state is null or jsonb_typeof(v_state) <> 'object' then return false; end if;

  select exists (
    select 1 from jsonb_array_elements(coalesce(v_state -> 'regions', '[]'::jsonb)) region
    where region ->> 'type' = 'FLOOR_REGION'
      and region ->> 'quality' <> 'INVALID'
      and jsonb_array_length(coalesce(region -> 'polygonImageNormalized', '[]'::jsonb)) >= 3
  ) into v_has_floor;
  select exists (
    select 1 from jsonb_array_elements(coalesce(v_state -> 'regions', '[]'::jsonb)) region
    where region ->> 'type' = 'MOVEMENT_ZONE'
      and region ->> 'quality' <> 'INVALID'
      and jsonb_array_length(coalesce(region -> 'polygonImageNormalized', '[]'::jsonb)) >= 3
  ) into v_has_movement;
  select count(*)::integer into v_height_count
  from jsonb_array_elements(coalesce(v_state #> '{calibration,references}', '[]'::jsonb)) reference
  where reference ->> 'axis' = 'VERTICAL'
    and coalesce((reference ->> 'active')::boolean, false)
    and coalesce((reference ->> 'useForCalibration')::boolean, false)
    and reference ->> 'semanticStatus' = 'CONFIRMED'
    and coalesce((reference ->> 'valueCm')::numeric, 0) between 10 and 600;

  if not v_has_floor or not v_has_movement or v_height_count < 2 then return false; end if;

  update public.photo_scenes set
    reconstruction_status = 'UNSOLVED',
    reconstruction_revision = v_revision,
    reconstruction_summary = null,
    reconstruction_worker_id = null,
    reconstruction_claimed_at = null,
    reconstruction_heartbeat_at = null,
    reconstruction_completed_at = null,
    reconstruction_error_code = null,
    reconstruction_error_message = null,
    scene_builder_version = 'photo-scene-builder-v0.10-beta.1',
    scene_state = jsonb_set(
      jsonb_set(v_state, '{reconstructionState,status}', '"UNSOLVED"'::jsonb, true),
      '{reconstructionState,reviewStatus}', '"UNREVIEWED"'::jsonb, true
    )
  where analysis_id = p_analysis_id;

  update public.analyses set
    status = 'queued'::public.analysis_status,
    progress = 20,
    processing_stage = 'ready-for-scene-detection',
    worker_id = null,
    claimed_at = null,
    heartbeat_at = null,
    queued_at = now(),
    error_code = null,
    error_message = null
  where id = p_analysis_id;
  return found;
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
    detection_completed_at = now(),
    reconstruction_status = case
      when s.reconstruction_status = 'UNSOLVED' and s.reconstruction_revision is not null then 'QUEUED'
      else s.reconstruction_status
    end,
    scene_state = case
      when s.reconstruction_status = 'UNSOLVED' and s.reconstruction_revision is not null
        then jsonb_set(s.scene_state, '{reconstructionState,status}', '"QUEUED"'::jsonb, true)
      else s.scene_state
    end
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

create or replace function public.retry_scene_detection(p_analysis_id uuid)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_requeued boolean := false;
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
  where id = p_analysis_id
    and analysis_type = 'PHOTO_SCENE'
    and source_image_path is not null
    and (user_id = (select auth.uid()) or (select public.is_admin()))
    and (
      processing_stage in ('photo-scene-setup', 'scene-detection-failed', 'scene-ready')
      or processing_stage is null
      or (processing_stage = 'ready-for-scene-detection' and coalesce(updated_at, queued_at, created_at) < now() - interval '2 minutes')
      or (processing_stage = 'scene-detection-processing' and coalesce(heartbeat_at, claimed_at, updated_at, created_at) < now() - interval '2 minutes')
    );
  v_requeued := found;
  if v_requeued then
    update public.photo_scenes set detection_error_code = null, detection_error_message = null
    where analysis_id = p_analysis_id;
  end if;
  return v_requeued;
end;
$$;

revoke all on function public.finalize_photo_scene_upload(uuid, integer, integer, integer) from public, anon;
revoke all on function public.finalize_photo_scene_upload(uuid, integer, integer, integer) from authenticated;
grant execute on function public.finalize_photo_scene_upload(uuid, integer, integer, integer) to authenticated;

revoke all on function public.request_guided_scene_build_v1(uuid, text) from public, anon;
revoke all on function public.request_guided_scene_build_v1(uuid, text) from authenticated;
grant execute on function public.request_guided_scene_build_v1(uuid, text) to authenticated;

revoke all on function public.complete_scene_detection_v1(uuid, text, text, text, jsonb, text) from public, anon, authenticated;
grant execute on function public.complete_scene_detection_v1(uuid, text, text, text, jsonb, text) to service_role;

revoke all on function public.retry_scene_detection(uuid) from public, anon;
revoke all on function public.retry_scene_detection(uuid) from authenticated;
grant execute on function public.retry_scene_detection(uuid) to authenticated;

notify pgrst, 'reload schema';
