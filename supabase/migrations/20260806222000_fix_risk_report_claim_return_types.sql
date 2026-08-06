-- Fix exact RETURN QUERY types for the Risk and Report Worker claim RPCs.
-- The public contracts and atomic claim behavior remain unchanged.

create or replace function public.claim_next_risk_analysis(p_worker_id text)
returns table (
  id uuid,
  user_id uuid,
  title text,
  status public.analysis_status,
  progress integer,
  processing_stage text,
  ergonomics_metrics_path text,
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
    raise exception 'Worker ID must not be empty.';
  end if;

  return query
  with next_analysis as (
    select a.id
    from public.analyses as a
    where a.status = 'queued'::public.analysis_status
      and a.processing_stage = 'ready-for-risk-assessment'
      and a.ergonomics_metrics_path is not null
      and btrim(a.ergonomics_metrics_path) <> ''
      and a.worker_id is null
    order by coalesce(a.queued_at, a.created_at), a.created_at, a.id
    for update skip locked
    limit 1
  )
  update public.analyses as a
  set
    status = 'processing'::public.analysis_status,
    progress = greatest(coalesce(a.progress, 0), 92),
    processing_stage = 'risk-processing',
    worker_id = v_worker_id,
    risk_worker_id = v_worker_id,
    risk_attempts = coalesce(a.risk_attempts, 0) + 1,
    claimed_at = now(),
    heartbeat_at = now(),
    started_at = coalesce(a.started_at, now()),
    risk_started_at = now(),
    error_code = null,
    error_message = null,
    risk_error_code = null,
    risk_error_message = null,
    risk_assessment_path = null,
    risk_assessment_version = null,
    risk_profile_id = null,
    risk_profile_version = null,
    risk_profile_status = null,
    risk_processed_frames = null,
    risk_valid_metric_ratio = null,
    risk_overall_level = null,
    risk_assessment_summary = null,
    risk_completed_at = null
  from next_analysis
  where a.id = next_analysis.id
    and a.status = 'queued'::public.analysis_status
    and a.processing_stage = 'ready-for-risk-assessment'
    and a.worker_id is null
  returning
    a.id::uuid,
    a.user_id::uuid,
    a.title::text,
    a.status::public.analysis_status,
    a.progress::integer,
    a.processing_stage::text,
    a.ergonomics_metrics_path::text,
    a.worker_id::text;
end;
$$;

create or replace function public.claim_next_report_analysis(p_worker_id text)
returns table (
  id uuid,
  user_id uuid,
  title text,
  status public.analysis_status,
  progress integer,
  processing_stage text,
  worker_id text,
  report_worker_id text,
  created_at timestamptz,
  source_file_name text,
  source_duration_seconds numeric,
  source_width integer,
  source_height integer,
  pose_quality_version text,
  pose_processed_frames integer,
  pose_detected_frames integer,
  pose_presence_ratio numeric,
  ergonomics_metrics_path text,
  ergonomics_metrics_version text,
  ergonomics_processed_frames integer,
  ergonomics_valid_metric_ratio numeric,
  risk_assessment_path text,
  risk_assessment_version text,
  risk_profile_id text,
  risk_profile_version text,
  risk_profile_status text,
  risk_processed_frames integer,
  risk_valid_metric_ratio numeric,
  risk_overall_level text
)
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_worker_id text := btrim(coalesce(p_worker_id, ''));
begin
  if v_worker_id = '' then
    raise exception 'Worker ID must not be empty.';
  end if;

  return query
  with next_analysis as (
    select a.id
    from public.analyses as a
    where a.status = 'queued'::public.analysis_status
      and a.processing_stage = 'ready-for-report'
      and a.risk_assessment_path is not null
      and btrim(a.risk_assessment_path) <> ''
      and a.ergonomics_metrics_path is not null
      and btrim(a.ergonomics_metrics_path) <> ''
      and a.worker_id is null
      and a.report_worker_id is null
    order by coalesce(a.queued_at, a.created_at), a.created_at, a.id
    for update skip locked
    limit 1
  )
  update public.analyses as a
  set
    status = 'processing'::public.analysis_status,
    progress = greatest(coalesce(a.progress, 0), 98),
    processing_stage = 'report-processing',
    worker_id = v_worker_id,
    report_worker_id = v_worker_id,
    attempts = coalesce(a.attempts, 0) + 1,
    report_attempts = coalesce(a.report_attempts, 0) + 1,
    claimed_at = now(),
    heartbeat_at = now(),
    started_at = coalesce(a.started_at, now()),
    report_started_at = now(),
    error_code = null,
    error_message = null,
    report_error_code = null,
    report_error_message = null,
    report_path = null,
    report_version = null,
    report_summary = null,
    report_completed_at = null
  from next_analysis
  where a.id = next_analysis.id
    and a.status = 'queued'::public.analysis_status
    and a.processing_stage = 'ready-for-report'
    and a.worker_id is null
    and a.report_worker_id is null
  returning
    a.id::uuid,
    a.user_id::uuid,
    a.title::text,
    a.status::public.analysis_status,
    a.progress::integer,
    a.processing_stage::text,
    a.worker_id::text,
    a.report_worker_id::text,
    a.created_at::timestamptz,
    a.source_file_name::text,
    a.source_duration_seconds::numeric,
    a.source_width::integer,
    a.source_height::integer,
    a.pose_quality_version::text,
    a.pose_processed_frames::integer,
    a.pose_detected_frames::integer,
    a.pose_presence_ratio::numeric,
    a.ergonomics_metrics_path::text,
    a.ergonomics_metrics_version::text,
    a.ergonomics_processed_frames::integer,
    a.ergonomics_valid_metric_ratio::numeric,
    a.risk_assessment_path::text,
    a.risk_assessment_version::text,
    a.risk_profile_id::text,
    a.risk_profile_version::text,
    a.risk_profile_status::text,
    a.risk_processed_frames::integer,
    a.risk_valid_metric_ratio::numeric,
    a.risk_overall_level::text;
end;
$$;

revoke all on function public.claim_next_risk_analysis(text) from public;
revoke all on function public.claim_next_risk_analysis(text) from anon;
revoke all on function public.claim_next_risk_analysis(text) from authenticated;
grant execute on function public.claim_next_risk_analysis(text) to service_role;

revoke all on function public.claim_next_report_analysis(text) from public;
revoke all on function public.claim_next_report_analysis(text) from anon;
revoke all on function public.claim_next_report_analysis(text) from authenticated;
grant execute on function public.claim_next_report_analysis(text) to service_role;

notify pgrst, 'reload schema';
