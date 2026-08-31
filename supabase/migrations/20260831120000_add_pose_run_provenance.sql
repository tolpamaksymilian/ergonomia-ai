-- Pose V6.8: immutable production-run provenance for claim, artifacts and UI.

alter table public.analyses
  add column if not exists pose_analysis_run_id uuid,
  add column if not exists pose_artifact_generation_id uuid,
  add column if not exists actual_worker_version text,
  add column if not exists actual_pose_version text,
  add column if not exists actual_pose_schema text,
  add column if not exists actual_quality_profile text,
  add column if not exists actual_worker_instance_id text,
  add column if not exists pose_worker_started_at timestamptz,
  add column if not exists pose_processing_started_at timestamptz,
  add column if not exists pose_processing_finished_at timestamptz,
  add column if not exists actual_build_id text,
  add column if not exists primary_pose_model text,
  add column if not exists temporal_pose_expert text,
  add column if not exists trajectory_expert text,
  add column if not exists actual_hand_model text,
  add column if not exists temporal_experts_enabled boolean,
  add column if not exists temporal_experts_actually_used boolean,
  add column if not exists temporal_expert_frames_count integer,
  add column if not exists pose_model_usage jsonb;

alter table public.analyses
  drop constraint if exists analyses_temporal_expert_frames_count_check,
  add constraint analyses_temporal_expert_frames_count_check
    check (temporal_expert_frames_count is null or temporal_expert_frames_count >= 0),
  drop constraint if exists analyses_pose_model_usage_object_check,
  add constraint analyses_pose_model_usage_object_check
    check (pose_model_usage is null or jsonb_typeof(pose_model_usage) = 'object');

create or replace function public.claim_next_pose_analysis_v2(
  p_worker_id text,
  p_worker_version text,
  p_pose_version text,
  p_pose_schema text,
  p_quality_profile text,
  p_worker_started_at timestamptz,
  p_build_id text,
  p_analysis_run_id uuid,
  p_artifact_generation_id uuid,
  p_primary_pose_model text,
  p_temporal_pose_expert text,
  p_trajectory_expert text,
  p_hand_model text,
  p_temporal_experts_enabled boolean
)
returns table (
  id uuid,
  user_id uuid,
  title text,
  status public.analysis_status,
  progress integer,
  source_video_path text,
  source_file_name text,
  source_mime_type text,
  source_size_bytes bigint,
  source_width integer,
  source_height integer,
  source_fps numeric,
  source_frame_count integer,
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
  if v_worker_id = '' then
    raise exception 'Worker ID nie może być pusty.';
  end if;
  if p_analysis_run_id is null or p_artifact_generation_id is null then
    raise exception 'Run ID i artifact generation ID są wymagane.';
  end if;

  return query
  with next_analysis as (
    select a.id
    from public.analyses as a
    where a.status = 'queued'::public.analysis_status
      and a.processing_stage = 'ready-for-ai'
    order by coalesce(a.queued_at, a.created_at), a.created_at, a.id
    for update skip locked
    limit 1
  )
  update public.analyses as a
  set
    status = 'processing'::public.analysis_status,
    progress = 20,
    worker_id = v_worker_id,
    attempts = coalesce(a.attempts, 0) + 1,
    claimed_at = now(),
    heartbeat_at = now(),
    started_at = coalesce(a.started_at, now()),
    processing_stage = 'pose-claimed',
    error_code = null,
    error_message = null,
    pose_analysis_run_id = p_analysis_run_id,
    pose_artifact_generation_id = p_artifact_generation_id,
    actual_worker_version = nullif(btrim(coalesce(p_worker_version, '')), ''),
    actual_pose_version = nullif(btrim(coalesce(p_pose_version, '')), ''),
    actual_pose_schema = nullif(btrim(coalesce(p_pose_schema, '')), ''),
    actual_quality_profile = nullif(btrim(coalesce(p_quality_profile, '')), ''),
    actual_worker_instance_id = v_worker_id,
    pose_worker_started_at = p_worker_started_at,
    pose_processing_started_at = now(),
    pose_processing_finished_at = null,
    actual_build_id = nullif(btrim(coalesce(p_build_id, '')), ''),
    primary_pose_model = nullif(btrim(coalesce(p_primary_pose_model, '')), ''),
    temporal_pose_expert = nullif(btrim(coalesce(p_temporal_pose_expert, '')), ''),
    trajectory_expert = nullif(btrim(coalesce(p_trajectory_expert, '')), ''),
    actual_hand_model = nullif(btrim(coalesce(p_hand_model, '')), ''),
    temporal_experts_enabled = coalesce(p_temporal_experts_enabled, false),
    temporal_experts_actually_used = null,
    temporal_expert_frames_count = null,
    pose_model_usage = null
  from next_analysis
  where a.id = next_analysis.id
    and a.status = 'queued'::public.analysis_status
    and a.processing_stage = 'ready-for-ai'
  returning
    a.id::uuid,
    a.user_id::uuid,
    a.title::text,
    a.status::public.analysis_status,
    a.progress::integer,
    a.source_video_path::text,
    a.source_file_name::text,
    a.source_mime_type::text,
    a.source_size_bytes::bigint,
    a.source_width::integer,
    a.source_height::integer,
    a.source_fps::numeric,
    a.source_frame_count::integer,
    a.attempts::integer,
    a.worker_id::text;
end;
$$;

create or replace function public.complete_pose_inference_v4(
  p_analysis_id uuid,
  p_worker_id text,
  p_result_video_path text,
  p_result_json_path text,
  p_thumbnail_path text,
  p_pose_model text,
  p_sample_stride integer,
  p_processed_frames integer,
  p_detected_frames integer,
  p_average_confidence numeric,
  p_active_start_frame integer,
  p_active_end_frame integer,
  p_active_start_seconds numeric,
  p_active_end_seconds numeric,
  p_active_duration_seconds numeric,
  p_presence_ratio numeric,
  p_tracking_method text,
  p_smoothing_method text,
  p_quality_version text,
  p_hand_model text,
  p_left_hand_valid_ratio numeric,
  p_right_hand_valid_ratio numeric,
  p_left_hand_rejected_frames integer,
  p_right_hand_rejected_frames integer,
  p_analysis_run_id uuid,
  p_artifact_generation_id uuid,
  p_temporal_experts_actually_used boolean,
  p_temporal_expert_frames_count integer,
  p_model_usage jsonb
)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_completed boolean;
begin
  if p_temporal_expert_frames_count < 0 then
    raise exception 'Liczba klatek temporal expert nie może być ujemna.';
  end if;
  if p_model_usage is not null and jsonb_typeof(p_model_usage) <> 'object' then
    raise exception 'Model usage musi być obiektem JSON.';
  end if;
  if not exists (
    select 1 from public.analyses as a
    where a.id = p_analysis_id
      and a.worker_id = btrim(coalesce(p_worker_id, ''))
      and a.pose_analysis_run_id = p_analysis_run_id
      and a.pose_artifact_generation_id = p_artifact_generation_id
      and a.processing_stage like 'pose-%'
  ) then
    raise exception 'Niezgodny worker lub provenance finalizowanego runu.';
  end if;

  v_completed := public.complete_pose_inference_v3(
    p_analysis_id, p_worker_id, p_result_video_path, p_result_json_path,
    p_thumbnail_path, p_pose_model, p_sample_stride, p_processed_frames,
    p_detected_frames, p_average_confidence, p_active_start_frame,
    p_active_end_frame, p_active_start_seconds, p_active_end_seconds,
    p_active_duration_seconds, p_presence_ratio, p_tracking_method,
    p_smoothing_method, p_quality_version, p_hand_model,
    p_left_hand_valid_ratio, p_right_hand_valid_ratio,
    p_left_hand_rejected_frames, p_right_hand_rejected_frames
  );
  if not coalesce(v_completed, false) then
    return false;
  end if;

  update public.analyses as a
  set
    pose_processing_finished_at = now(),
    temporal_experts_actually_used = coalesce(p_temporal_experts_actually_used, false),
    temporal_expert_frames_count = coalesce(p_temporal_expert_frames_count, 0),
    pose_model_usage = coalesce(p_model_usage, '{}'::jsonb)
  where a.id = p_analysis_id
    and a.pose_analysis_run_id = p_analysis_run_id
    and a.pose_artifact_generation_id = p_artifact_generation_id;
  return found;
end;
$$;

revoke all on function public.claim_next_pose_analysis_v2(text, text, text, text, text, timestamptz, text, uuid, uuid, text, text, text, text, boolean) from public, anon, authenticated;
grant execute on function public.claim_next_pose_analysis_v2(text, text, text, text, text, timestamptz, text, uuid, uuid, text, text, text, text, boolean) to service_role;

revoke all on function public.complete_pose_inference_v4(uuid, text, text, text, text, text, integer, integer, integer, numeric, integer, integer, numeric, numeric, numeric, numeric, text, text, text, text, numeric, numeric, integer, integer, uuid, uuid, boolean, integer, jsonb) from public, anon, authenticated;
grant execute on function public.complete_pose_inference_v4(uuid, text, text, text, text, text, integer, integer, integer, numeric, integer, integer, numeric, numeric, numeric, numeric, text, text, text, text, numeric, numeric, integer, integer, uuid, uuid, boolean, integer, jsonb) to service_role;

notify pgrst, 'reload schema';
