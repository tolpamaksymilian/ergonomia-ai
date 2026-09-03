-- Repair the production Pose late-stage contract without changing Pose inference.

alter table public.analyses
  add column if not exists requested_quality_profile text not null default 'ACCURATE',
  add column if not exists effective_quality_profile text,
  add column if not exists quality_profile_degraded boolean not null default false,
  add column if not exists quality_profile_degradation_reason text,
  add column if not exists failure_stage text,
  add column if not exists failure_code text,
  add column if not exists failure_message text,
  add column if not exists failure_component text,
  add column if not exists failure_timestamp timestamptz,
  add column if not exists failure_retryable boolean,
  add column if not exists failure_http_status integer,
  add column if not exists failure_upstream_error_code text;

alter table public.analyses
  drop constraint if exists analyses_requested_quality_profile_check,
  add constraint analyses_requested_quality_profile_check
    check (requested_quality_profile in ('PERFORMANCE', 'ACCURATE', 'ULTRA')),
  drop constraint if exists analyses_effective_quality_profile_check,
  add constraint analyses_effective_quality_profile_check
    check (effective_quality_profile is null or effective_quality_profile in ('PERFORMANCE', 'ACCURATE', 'ULTRA')),
  drop constraint if exists analyses_failure_http_status_check,
  add constraint analyses_failure_http_status_check
    check (failure_http_status is null or failure_http_status between 100 and 599),
  drop constraint if exists analyses_quality_degradation_reason_check,
  add constraint analyses_quality_degradation_reason_check
    check (
      (quality_profile_degraded = false and quality_profile_degradation_reason is null)
      or (quality_profile_degraded = true and nullif(btrim(quality_profile_degradation_reason), '') is not null)
    );

create or replace function public.claim_next_pose_analysis_v3(
  p_worker_id text,
  p_worker_version text,
  p_pose_version text,
  p_pose_schema text,
  p_quality_profile text,
  p_effective_quality_profile text,
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
  id uuid, user_id uuid, title text, status public.analysis_status,
  progress integer, source_video_path text, source_file_name text,
  source_mime_type text, source_size_bytes bigint, source_width integer,
  source_height integer, source_fps numeric, source_frame_count integer,
  attempts integer, worker_id text
)
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_worker_id text := btrim(coalesce(p_worker_id, ''));
  v_effective_profile text := upper(btrim(coalesce(p_effective_quality_profile, p_quality_profile, '')));
begin
  if v_worker_id = '' then raise exception 'Worker ID nie może być pusty.'; end if;
  if v_effective_profile not in ('PERFORMANCE', 'ACCURATE', 'ULTRA') then
    raise exception 'Nieprawidłowy effective quality profile.';
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
      and a.analysis_type = 'VIDEO'
      and upper(coalesce(a.requested_quality_profile, 'ACCURATE')) = v_effective_profile
    order by coalesce(a.queued_at, a.created_at), a.created_at, a.id
    for update skip locked
    limit 1
  )
  update public.analyses as a
  set status = 'processing'::public.analysis_status,
      progress = 20,
      worker_id = v_worker_id,
      attempts = coalesce(a.attempts, 0) + 1,
      claimed_at = now(), heartbeat_at = now(),
      started_at = coalesce(a.started_at, now()),
      processing_stage = 'pose-claimed',
      error_code = null, error_message = null,
      failure_stage = null, failure_code = null, failure_message = null,
      failure_component = null, failure_timestamp = null,
      failure_retryable = null, failure_http_status = null,
      failure_upstream_error_code = null,
      pose_analysis_run_id = p_analysis_run_id,
      pose_artifact_generation_id = p_artifact_generation_id,
      actual_worker_version = nullif(btrim(coalesce(p_worker_version, '')), ''),
      actual_pose_version = nullif(btrim(coalesce(p_pose_version, '')), ''),
      actual_pose_schema = nullif(btrim(coalesce(p_pose_schema, '')), ''),
      actual_quality_profile = v_effective_profile,
      effective_quality_profile = v_effective_profile,
      quality_profile_degraded = false,
      quality_profile_degradation_reason = null,
      actual_worker_instance_id = v_worker_id,
      pose_worker_started_at = p_worker_started_at,
      pose_processing_started_at = now(), pose_processing_finished_at = null,
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
  returning
    a.id::uuid, a.user_id::uuid, a.title::text,
    a.status::public.analysis_status, a.progress::integer,
    a.source_video_path::text, a.source_file_name::text,
    a.source_mime_type::text, a.source_size_bytes::bigint,
    a.source_width::integer, a.source_height::integer,
    a.source_fps::numeric, a.source_frame_count::integer,
    a.attempts::integer, a.worker_id::text;
end;
$$;

create or replace function public.fail_pose_processing_v2(
  p_analysis_id uuid, p_worker_id text, p_failure_stage text,
  p_failure_code text, p_failure_message text, p_failure_component text,
  p_failure_timestamp timestamptz, p_retryable boolean,
  p_http_status integer, p_upstream_error_code text
)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_failed_stage text;
begin
  v_failed_stage := case p_failure_stage
    when 'artifact-upload' then 'pose-artifact-upload-failed'
    when 'artifact-compression' then 'pose-artifact-upload-failed'
    when 'database-finalization' then 'pose-database-finalization-failed'
    else 'processing-failed'
  end;
  update public.analyses as a
  set status = 'failed'::public.analysis_status,
      worker_id = null,
      processing_stage = v_failed_stage,
      heartbeat_at = now(), completed_at = now(),
      error_code = left(coalesce(nullif(btrim(p_failure_code), ''), 'POSE_INFERENCE_ERROR'), 100),
      error_message = left(coalesce(nullif(btrim(p_failure_message), ''), 'Nieznany błąd Pose Workera.'), 2000),
      failure_stage = left(nullif(btrim(p_failure_stage), ''), 120),
      failure_code = left(nullif(btrim(p_failure_code), ''), 100),
      failure_message = left(nullif(btrim(p_failure_message), ''), 2000),
      failure_component = left(nullif(btrim(p_failure_component), ''), 120),
      failure_timestamp = coalesce(p_failure_timestamp, now()),
      failure_retryable = coalesce(p_retryable, false),
      failure_http_status = p_http_status,
      failure_upstream_error_code = left(nullif(btrim(p_upstream_error_code), ''), 100)
  where a.id = p_analysis_id
    and a.status = 'processing'::public.analysis_status
    and a.worker_id = btrim(coalesce(p_worker_id, ''));
  return found;
end;
$$;

create or replace function public.claim_next_pose_late_retry(p_worker_id text)
returns table (
  id uuid, user_id uuid, title text, retry_kind text,
  pose_analysis_run_id uuid, pose_artifact_generation_id uuid
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
    select a.id
    from public.analyses as a
    where a.status = 'queued'::public.analysis_status
      and a.processing_stage in ('ready-for-pose-artifact-upload', 'ready-for-pose-finalization')
      and a.pose_analysis_run_id is not null
      and a.pose_artifact_generation_id is not null
    order by coalesce(a.queued_at, a.created_at), a.id
    for update skip locked limit 1
  )
  update public.analyses as a
  set status = 'processing'::public.analysis_status,
      worker_id = v_worker_id,
      attempts = coalesce(a.attempts, 0) + 1,
      claimed_at = now(), heartbeat_at = now(),
      processing_stage = case a.processing_stage
        when 'ready-for-pose-artifact-upload' then 'pose-artifact-upload-retry'
        else 'pose-database-finalization-retry' end,
      error_code = null, error_message = null
  from next_analysis
  where a.id = next_analysis.id
  returning a.id::uuid, a.user_id::uuid, a.title::text,
    (case a.processing_stage
      when 'pose-artifact-upload-retry' then 'artifact-upload'
      else 'database-finalization' end)::text,
    a.pose_analysis_run_id::uuid, a.pose_artifact_generation_id::uuid;
end;
$$;

-- The V4 completion call previously rejected the legitimate
-- `saving-pose-results-v6`/`database-finalization` stage via LIKE 'pose-%'.
create or replace function public.complete_pose_inference_v4(
  p_analysis_id uuid, p_worker_id text, p_result_video_path text,
  p_result_json_path text, p_thumbnail_path text, p_pose_model text,
  p_sample_stride integer, p_processed_frames integer, p_detected_frames integer,
  p_average_confidence numeric, p_active_start_frame integer,
  p_active_end_frame integer, p_active_start_seconds numeric,
  p_active_end_seconds numeric, p_active_duration_seconds numeric,
  p_presence_ratio numeric, p_tracking_method text, p_smoothing_method text,
  p_quality_version text, p_hand_model text, p_left_hand_valid_ratio numeric,
  p_right_hand_valid_ratio numeric, p_left_hand_rejected_frames integer,
  p_right_hand_rejected_frames integer, p_analysis_run_id uuid,
  p_artifact_generation_id uuid, p_temporal_experts_actually_used boolean,
  p_temporal_expert_frames_count integer, p_model_usage jsonb
)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare v_completed boolean;
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
      and a.status = 'processing'::public.analysis_status
      and a.worker_id = btrim(coalesce(p_worker_id, ''))
      and a.pose_analysis_run_id = p_analysis_run_id
      and a.pose_artifact_generation_id = p_artifact_generation_id
      and a.processing_stage in (
        'saving-pose-results-v6', 'database-finalization',
        'pose-database-finalization-retry', 'pose-artifact-upload-retry'
      )
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
  if not coalesce(v_completed, false) then return false; end if;
  update public.analyses as a
  set pose_processing_finished_at = now(),
      temporal_experts_actually_used = coalesce(p_temporal_experts_actually_used, false),
      temporal_expert_frames_count = coalesce(p_temporal_expert_frames_count, 0),
      pose_model_usage = coalesce(p_model_usage, '{}'::jsonb),
      failure_stage = null, failure_code = null, failure_message = null,
      failure_component = null, failure_timestamp = null,
      failure_retryable = null, failure_http_status = null,
      failure_upstream_error_code = null
  where a.id = p_analysis_id
    and a.pose_analysis_run_id = p_analysis_run_id
    and a.pose_artifact_generation_id = p_artifact_generation_id;
  return found;
end;
$$;

create or replace function public.retry_failed_analysis_stage(p_analysis_id uuid)
returns boolean
language plpgsql security definer set search_path = ''
as $$
declare v_analysis public.analyses%rowtype; v_next_stage text; v_next_progress integer;
begin
  if p_analysis_id is null then return false; end if;
  if coalesce((select auth.role()), '') <> 'service_role'
    and not exists (select 1 from public.profiles p where p.id = (select auth.uid()) and p.role = 'admin')
  then
    raise exception 'Administrator privileges are required.' using errcode = '42501';
  end if;
  select a.* into v_analysis from public.analyses a
  where a.id = p_analysis_id and a.status = 'failed'::public.analysis_status for update;
  if not found then return false; end if;
  case v_analysis.processing_stage
    when 'pose-artifact-upload-failed' then
      if not coalesce(v_analysis.failure_retryable, false) then return false; end if;
      v_next_stage := 'ready-for-pose-artifact-upload'; v_next_progress := 91;
    when 'pose-database-finalization-failed' then
      if not coalesce(v_analysis.failure_retryable, false) then return false; end if;
      v_next_stage := 'ready-for-pose-finalization'; v_next_progress := 97;
    when 'processing-failed' then
      if v_analysis.source_width is not null and v_analysis.source_height is not null
        and v_analysis.source_fps is not null and v_analysis.source_frame_count is not null
      then v_next_stage := 'ready-for-ai'; v_next_progress := 20;
      else v_next_stage := 'queued'; v_next_progress := 0; end if;
    when 'ergonomics-failed' then
      if coalesce(btrim(v_analysis.result_json_path), '') = '' then return false; end if;
      v_next_stage := 'ready-for-ergonomics'; v_next_progress := 75;
    when 'risk-failed' then
      if coalesce(btrim(v_analysis.ergonomics_metrics_path), '') = '' then return false; end if;
      v_next_stage := 'ready-for-risk-assessment'; v_next_progress := 90;
    when 'report-failed' then
      if coalesce(btrim(v_analysis.risk_assessment_path), '') = '' then return false; end if;
      v_next_stage := 'ready-for-report'; v_next_progress := 97;
    else return false;
  end case;
  update public.analyses
  set status = 'queued'::public.analysis_status, progress = v_next_progress,
      processing_stage = v_next_stage, worker_id = null, claimed_at = null,
      heartbeat_at = null, queued_at = now(), completed_at = null,
      processing_completed_at = null, error_code = null, error_message = null
  where id = p_analysis_id and status = 'failed'::public.analysis_status
    and processing_stage = v_analysis.processing_stage;
  return found;
end;
$$;

-- Recover only records produced by the exact deployed V4 stage-contract bug.
update public.analyses
set processing_stage = 'pose-database-finalization-failed',
    error_code = 'POSE_DATABASE_FINALIZATION_ERROR',
    failure_stage = 'database-finalization',
    failure_code = 'POSE_DATABASE_FINALIZATION_ERROR',
    failure_message = error_message,
    failure_component = 'supabase-rpc',
    failure_timestamp = coalesce(completed_at, now()),
    failure_retryable = true,
    failure_upstream_error_code = 'P0001',
    requested_quality_profile = 'ACCURATE',
    effective_quality_profile = 'ACCURATE',
    actual_quality_profile = 'ACCURATE',
    quality_profile_degraded = false,
    quality_profile_degradation_reason = null
where status = 'failed'::public.analysis_status
  and processing_stage = 'processing-failed'
  and pose_analysis_run_id is not null
  and error_message like '%Niezgodny worker lub provenance finalizowanego runu.%';

revoke all on function public.claim_next_pose_analysis_v3(text,text,text,text,text,text,timestamptz,text,uuid,uuid,text,text,text,text,boolean) from public, anon, authenticated;
grant execute on function public.claim_next_pose_analysis_v3(text,text,text,text,text,text,timestamptz,text,uuid,uuid,text,text,text,text,boolean) to service_role;
revoke all on function public.fail_pose_processing_v2(uuid,text,text,text,text,text,timestamptz,boolean,integer,text) from public, anon, authenticated;
grant execute on function public.fail_pose_processing_v2(uuid,text,text,text,text,text,timestamptz,boolean,integer,text) to service_role;
revoke all on function public.claim_next_pose_late_retry(text) from public, anon, authenticated;
grant execute on function public.claim_next_pose_late_retry(text) to service_role;
revoke all on function public.complete_pose_inference_v4(uuid,text,text,text,text,text,integer,integer,integer,numeric,integer,integer,numeric,numeric,numeric,numeric,text,text,text,text,numeric,numeric,integer,integer,uuid,uuid,boolean,integer,jsonb) from public, anon, authenticated;
grant execute on function public.complete_pose_inference_v4(uuid,text,text,text,text,text,integer,integer,integer,numeric,integer,integer,numeric,numeric,numeric,numeric,text,text,text,text,numeric,numeric,integer,integer,uuid,uuid,boolean,integer,jsonb) to service_role;
revoke all on function public.retry_failed_analysis_stage(uuid) from public, anon;
grant execute on function public.retry_failed_analysis_stage(uuid) to authenticated;
grant execute on function public.retry_failed_analysis_stage(uuid) to service_role;

notify pgrst, 'reload schema';
