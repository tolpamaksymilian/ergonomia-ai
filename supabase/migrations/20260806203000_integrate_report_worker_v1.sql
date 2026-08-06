-- ============================================================
-- ERGONOMIA AI
-- Report Worker V1
-- Requires: 20260806120000_integrate_risk_worker_v1.sql
-- ============================================================

alter table public.analyses
  add column if not exists report_path text,
  add column if not exists report_version text,
  add column if not exists report_summary jsonb,
  add column if not exists report_completed_at timestamptz,
  add column if not exists report_error_code text,
  add column if not exists report_error_message text,
  add column if not exists report_worker_id text,
  add column if not exists report_started_at timestamptz,
  add column if not exists report_attempts integer not null default 0;

alter table public.analyses
  drop constraint if exists analyses_report_path_not_blank,
  drop constraint if exists analyses_report_version_not_blank,
  drop constraint if exists analyses_report_summary_object_check,
  drop constraint if exists analyses_report_attempts_check;

alter table public.analyses
  add constraint analyses_report_path_not_blank
    check (report_path is null or btrim(report_path) <> ''),
  add constraint analyses_report_version_not_blank
    check (report_version is null or btrim(report_version) <> ''),
  add constraint analyses_report_summary_object_check
    check (report_summary is null or jsonb_typeof(report_summary) = 'object'),
  add constraint analyses_report_attempts_check
    check (report_attempts >= 0);

create index if not exists analyses_report_queue_claim_idx
on public.analyses (queued_at, created_at, id)
where
  status = 'queued'::public.analysis_status
  and processing_stage = 'ready-for-report'
  and risk_assessment_path is not null
  and btrim(risk_assessment_path) <> ''
  and ergonomics_metrics_path is not null
  and btrim(ergonomics_metrics_path) <> '';

-- ============================================================
-- Atomic claim: ready-for-report -> report-processing
-- ============================================================

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
    a.id,
    a.user_id,
    a.title,
    a.status,
    a.progress,
    a.processing_stage,
    a.worker_id,
    a.report_worker_id,
    a.created_at,
    a.source_file_name,
    a.source_duration_seconds,
    a.source_width,
    a.source_height,
    a.pose_quality_version,
    a.pose_processed_frames,
    a.pose_detected_frames,
    a.pose_presence_ratio,
    a.ergonomics_metrics_path,
    a.ergonomics_metrics_version,
    a.ergonomics_processed_frames,
    a.ergonomics_valid_metric_ratio,
    a.risk_assessment_path,
    a.risk_assessment_version,
    a.risk_profile_id,
    a.risk_profile_version,
    a.risk_profile_status,
    a.risk_processed_frames,
    a.risk_valid_metric_ratio,
    a.risk_overall_level;
end;
$$;

-- ============================================================
-- Atomic completion: report-processing -> completed
-- ============================================================

create or replace function public.complete_report_v1(
  p_analysis_id uuid,
  p_worker_id text,
  p_report_path text,
  p_report_version text,
  p_report_summary jsonb
)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_owner_id uuid;
  v_expected_path text;
  v_valid_metric_ratio numeric;
begin
  if p_analysis_id is null then
    raise exception 'Analysis ID must not be null.';
  end if;
  if btrim(coalesce(p_worker_id, '')) = '' then
    raise exception 'Worker ID must not be empty.';
  end if;
  if btrim(coalesce(p_report_path, '')) = '' then
    raise exception 'Report path must not be empty.';
  end if;
  if btrim(coalesce(p_report_version, '')) = '' then
    raise exception 'Report version must not be empty.';
  end if;
  if p_report_summary is null or jsonb_typeof(p_report_summary) <> 'object' then
    raise exception 'Report summary must be a JSON object.';
  end if;
  if p_report_summary ?| array[
    'frames', 'body_areas', 'metric_summary', 'key_moments', 'limitations'
  ] then
    raise exception 'Report summary contains full report data.';
  end if;
  if (p_report_summary ->> 'report_version') is distinct from p_report_version then
    raise exception 'Report summary version is inconsistent.';
  end if;
  if (p_report_summary ->> 'analysis_id') is distinct from p_analysis_id::text then
    raise exception 'Report summary analysis ID is inconsistent.';
  end if;
  if (p_report_summary ->> 'overall_level') is null
     or (p_report_summary ->> 'overall_level') not in (
       'low', 'moderate', 'high', 'critical', 'insufficient_data'
     ) then
    raise exception 'Report summary contains unsupported overall level.';
  end if;
  if (p_report_summary -> 'insufficient_data') is null
     or jsonb_typeof(p_report_summary -> 'insufficient_data') <> 'boolean' then
    raise exception 'Report summary insufficient_data must be boolean.';
  end if;
  if p_report_summary ->> 'valid_metric_ratio' is null then
    raise exception 'Report summary lacks valid metric coverage.';
  end if;
  v_valid_metric_ratio := (p_report_summary ->> 'valid_metric_ratio')::numeric;
  if v_valid_metric_ratio < 0 or v_valid_metric_ratio > 1 then
    raise exception 'Valid metric coverage must be between 0 and 1.';
  end if;
  if (p_report_summary ->> 'key_moments_count') is null
     or (p_report_summary ->> 'metric_count') is null
     or (p_report_summary ->> 'key_moments_count')::integer < 0
     or (p_report_summary ->> 'metric_count')::integer < 0 then
    raise exception 'Report summary counters must not be negative.';
  end if;
  if (p_report_summary ->> 'profile_status') is null
     or (p_report_summary ->> 'profile_status') not in (
       'development', 'draft', 'approved', 'archived'
     ) then
    raise exception 'Report summary contains unsupported profile status.';
  end if;

  select a.user_id
  into v_owner_id
  from public.analyses as a
  where a.id = p_analysis_id
    and a.status = 'processing'::public.analysis_status
    and a.processing_stage = 'report-processing'
    and a.worker_id = btrim(p_worker_id)
    and a.report_worker_id = btrim(p_worker_id)
  for update;

  if not found then
    return false;
  end if;

  v_expected_path := v_owner_id::text || '/' || p_analysis_id::text
    || '/results/analysis-report.json';

  if p_report_path <> v_expected_path then
    raise exception 'Invalid report storage path.';
  end if;
  if not exists (
    select 1
    from storage.objects
    where bucket_id = 'analysis-results'
      and name = p_report_path
  ) then
    raise exception 'Analysis report object does not exist in Storage.';
  end if;

  update public.analyses
  set
    status = 'completed'::public.analysis_status,
    progress = 100,
    processing_stage = 'completed',
    report_path = p_report_path,
    report_version = left(btrim(p_report_version), 80),
    report_summary = p_report_summary,
    report_completed_at = now(),
    completed_at = now(),
    processing_completed_at = now(),
    worker_id = null,
    report_worker_id = null,
    claimed_at = null,
    heartbeat_at = null,
    error_code = null,
    error_message = null,
    report_error_code = null,
    report_error_message = null
  where id = p_analysis_id
    and status = 'processing'::public.analysis_status
    and processing_stage = 'report-processing'
    and worker_id = btrim(p_worker_id)
    and report_worker_id = btrim(p_worker_id);

  return found;
end;
$$;

-- ============================================================
-- Report-only failure and retry. Previous pipeline results are preserved.
-- ============================================================

create or replace function public.fail_report_generation(
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
declare
  v_error_code text := left(
    coalesce(nullif(btrim(coalesce(p_error_code, '')), ''), 'REPORT_BUILD_ERROR'),
    100
  );
  v_error_message text := left(
    coalesce(nullif(btrim(coalesce(p_error_message, '')), ''), 'Unknown Report Worker error.'),
    2000
  );
begin
  update public.analyses
  set
    status = 'failed'::public.analysis_status,
    processing_stage = 'report-failed',
    worker_id = null,
    report_worker_id = null,
    claimed_at = null,
    heartbeat_at = null,
    error_code = v_error_code,
    error_message = v_error_message,
    report_error_code = v_error_code,
    report_error_message = v_error_message
  where id = p_analysis_id
    and status = 'processing'::public.analysis_status
    and processing_stage = 'report-processing'
    and worker_id = btrim(coalesce(p_worker_id, ''))
    and report_worker_id = btrim(coalesce(p_worker_id, ''));

  return found;
end;
$$;

create or replace function public.retry_report_analysis(p_analysis_id uuid)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
begin
  update public.analyses
  set
    status = 'queued'::public.analysis_status,
    progress = 97,
    processing_stage = 'ready-for-report',
    worker_id = null,
    report_worker_id = null,
    claimed_at = null,
    heartbeat_at = null,
    queued_at = now(),
    completed_at = null,
    processing_completed_at = null,
    error_code = null,
    error_message = null,
    report_path = null,
    report_version = null,
    report_summary = null,
    report_completed_at = null,
    report_error_code = null,
    report_error_message = null,
    report_started_at = null
  where id = p_analysis_id
    and risk_assessment_path is not null
    and btrim(risk_assessment_path) <> ''
    and ergonomics_metrics_path is not null
    and btrim(ergonomics_metrics_path) <> ''
    and (
      (status = 'failed'::public.analysis_status and processing_stage = 'report-failed')
      or
      (status = 'completed'::public.analysis_status and processing_stage = 'completed')
      or
      (
        status = 'processing'::public.analysis_status
        and processing_stage = 'report-processing'
        and report_started_at < now() - interval '30 minutes'
      )
    );

  return found;
end;
$$;

-- Keep progress coherent for every stage without restricting the text-based
-- processing_stage column.
create or replace function public.normalize_analysis_pipeline_progress()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if new.status = 'completed'::public.analysis_status
     or new.processing_stage = 'completed' then
    new.progress := 100;
  elsif new.processing_stage = 'report-processing' then
    new.progress := greatest(coalesce(new.progress, 0), 98);
  elsif new.processing_stage = 'ready-for-report' then
    new.progress := greatest(coalesce(new.progress, 0), 97);
  elsif new.processing_stage = 'risk-processing' then
    new.progress := greatest(coalesce(new.progress, 0), 92);
  elsif new.processing_stage = 'ready-for-risk-assessment' then
    new.progress := greatest(coalesce(new.progress, 0), 90);
  elsif new.processing_stage = 'ergonomics-processing' then
    new.progress := greatest(coalesce(new.progress, 0), 78);
  elsif new.processing_stage = 'ready-for-ergonomics' then
    new.progress := greatest(coalesce(new.progress, 0), 75);
  elsif new.processing_stage = 'ready-for-ai' then
    new.progress := greatest(coalesce(new.progress, 0), 20);
  end if;
  return new;
end;
$$;

update public.analyses
set progress = greatest(coalesce(progress, 0), 97)
where processing_stage = 'ready-for-report';

revoke execute on function public.claim_next_report_analysis(text)
from public, anon, authenticated;
revoke execute on function public.complete_report_v1(uuid, text, text, text, jsonb)
from public, anon, authenticated;
revoke execute on function public.fail_report_generation(uuid, text, text, text)
from public, anon, authenticated;
revoke execute on function public.retry_report_analysis(uuid)
from public, anon, authenticated;

grant execute on function public.claim_next_report_analysis(text) to service_role;
grant execute on function public.complete_report_v1(uuid, text, text, text, jsonb)
to service_role;
grant execute on function public.fail_report_generation(uuid, text, text, text)
to service_role;
grant execute on function public.retry_report_analysis(uuid) to service_role;

notify pgrst, 'reload schema';
