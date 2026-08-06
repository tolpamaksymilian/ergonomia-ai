-- ============================================================
-- ERGONOMIA AI
-- Ergonomics Worker prerequisite + Risk Worker V1 integration
--
-- The earlier ergonomics integration file was stored outside the directory
-- used by Supabase CLI. This migration is intentionally self-contained and
-- idempotently installs that prerequisite before the risk stage.
-- ============================================================

alter table public.analyses
  add column if not exists ergonomics_metrics_path text,
  add column if not exists ergonomics_metrics_version text,
  add column if not exists ergonomics_processed_frames integer,
  add column if not exists ergonomics_valid_metric_ratio numeric(7, 6),
  add column if not exists ergonomics_metrics_summary jsonb,
  add column if not exists ergonomics_completed_at timestamptz,
  add column if not exists ergonomics_error_code text,
  add column if not exists ergonomics_error_message text;

alter table public.analyses
  drop constraint if exists analyses_ergonomics_metrics_path_not_blank,
  drop constraint if exists analyses_ergonomics_processed_frames_check,
  drop constraint if exists analyses_ergonomics_valid_metric_ratio_check,
  drop constraint if exists analyses_ergonomics_metrics_summary_object_check;

alter table public.analyses
  add constraint analyses_ergonomics_metrics_path_not_blank
    check (ergonomics_metrics_path is null or btrim(ergonomics_metrics_path) <> ''),
  add constraint analyses_ergonomics_processed_frames_check
    check (ergonomics_processed_frames is null or ergonomics_processed_frames >= 0),
  add constraint analyses_ergonomics_valid_metric_ratio_check
    check (
      ergonomics_valid_metric_ratio is null
      or ergonomics_valid_metric_ratio between 0 and 1
    ),
  add constraint analyses_ergonomics_metrics_summary_object_check
    check (
      ergonomics_metrics_summary is null
      or jsonb_typeof(ergonomics_metrics_summary) = 'object'
    );

create index if not exists analyses_ergonomics_queue_claim_idx
on public.analyses (queued_at, created_at, id)
where
  status = 'queued'::public.analysis_status
  and processing_stage = 'ready-for-ergonomics'
  and result_json_path is not null
  and btrim(result_json_path) <> '';

drop function if exists public.claim_next_ergonomics_analysis(text);

create function public.claim_next_ergonomics_analysis(p_worker_id text)
returns table (
  id uuid,
  user_id uuid,
  title text,
  status public.analysis_status,
  progress integer,
  result_json_path text,
  processing_stage text,
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
      and a.processing_stage = 'ready-for-ergonomics'
      and a.result_json_path is not null
      and btrim(a.result_json_path) <> ''
      and a.worker_id is null
    order by coalesce(a.queued_at, a.created_at), a.created_at, a.id
    for update skip locked
    limit 1
  )
  update public.analyses as a
  set
    status = 'processing'::public.analysis_status,
    progress = greatest(coalesce(a.progress, 0), 78),
    worker_id = v_worker_id,
    attempts = coalesce(a.attempts, 0) + 1,
    claimed_at = now(),
    heartbeat_at = now(),
    started_at = coalesce(a.started_at, now()),
    processing_stage = 'ergonomics-processing',
    error_code = null,
    error_message = null,
    ergonomics_error_code = null,
    ergonomics_error_message = null,
    ergonomics_metrics_path = null,
    ergonomics_metrics_version = null,
    ergonomics_processed_frames = null,
    ergonomics_valid_metric_ratio = null,
    ergonomics_metrics_summary = null,
    ergonomics_completed_at = null
  from next_analysis
  where a.id = next_analysis.id
    and a.status = 'queued'::public.analysis_status
    and a.processing_stage = 'ready-for-ergonomics'
    and a.worker_id is null
  returning
    a.id,
    a.user_id,
    a.title,
    a.status,
    a.progress,
    a.result_json_path,
    a.processing_stage,
    a.worker_id;
end;
$$;

create or replace function public.complete_ergonomics_metrics_v1(
  p_analysis_id uuid,
  p_worker_id text,
  p_metrics_path text,
  p_metrics_version text,
  p_processed_frames integer,
  p_valid_metric_ratio numeric,
  p_metrics_summary jsonb
)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_owner_id uuid;
  v_expected_path text;
begin
  if btrim(coalesce(p_worker_id, '')) = '' then
    raise exception 'Worker ID must not be empty.';
  end if;
  if btrim(coalesce(p_metrics_path, '')) = '' then
    raise exception 'Metrics path must not be empty.';
  end if;
  if btrim(coalesce(p_metrics_version, '')) = '' then
    raise exception 'Metrics version must not be empty.';
  end if;
  if p_processed_frames is null or p_processed_frames < 1 then
    raise exception 'Metrics document must contain at least one frame.';
  end if;
  if p_valid_metric_ratio is null or p_valid_metric_ratio < 0 or p_valid_metric_ratio > 1 then
    raise exception 'Valid metric coverage must be between 0 and 1.';
  end if;
  if p_metrics_summary is null or jsonb_typeof(p_metrics_summary) <> 'object' then
    raise exception 'Metrics summary must be a JSON object.';
  end if;

  select a.user_id
  into v_owner_id
  from public.analyses as a
  where a.id = p_analysis_id
    and a.status = 'processing'::public.analysis_status
    and a.processing_stage = 'ergonomics-processing'
    and a.worker_id = btrim(p_worker_id)
  for update;

  if not found then
    return false;
  end if;

  v_expected_path := v_owner_id::text || '/' || p_analysis_id::text
    || '/results/ergonomics-metrics.json';

  if p_metrics_path <> v_expected_path then
    raise exception 'Invalid ergonomics metrics storage path.';
  end if;
  if not exists (
    select 1 from storage.objects
    where bucket_id = 'analysis-results' and name = p_metrics_path
  ) then
    raise exception 'Ergonomics metrics object does not exist in Storage.';
  end if;

  update public.analyses
  set
    status = 'queued'::public.analysis_status,
    progress = greatest(coalesce(progress, 0), 90),
    processing_stage = 'ready-for-risk-assessment',
    ergonomics_metrics_path = p_metrics_path,
    ergonomics_metrics_version = left(btrim(p_metrics_version), 80),
    ergonomics_processed_frames = p_processed_frames,
    ergonomics_valid_metric_ratio = round(p_valid_metric_ratio, 6),
    ergonomics_metrics_summary = p_metrics_summary,
    ergonomics_completed_at = now(),
    worker_id = null,
    claimed_at = null,
    heartbeat_at = null,
    queued_at = now(),
    error_code = null,
    error_message = null,
    ergonomics_error_code = null,
    ergonomics_error_message = null
  where id = p_analysis_id
    and status = 'processing'::public.analysis_status
    and processing_stage = 'ergonomics-processing'
    and worker_id = btrim(p_worker_id);

  return found;
end;
$$;

create or replace function public.fail_ergonomics_processing(
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
    coalesce(nullif(btrim(coalesce(p_error_code, '')), ''), 'ERGONOMICS_WORKER_ERROR'),
    100
  );
  v_error_message text := left(
    coalesce(nullif(btrim(coalesce(p_error_message, '')), ''), 'Unknown Ergonomics Worker error.'),
    2000
  );
begin
  update public.analyses
  set
    status = 'failed'::public.analysis_status,
    processing_stage = 'ergonomics-failed',
    worker_id = null,
    claimed_at = null,
    heartbeat_at = null,
    error_code = v_error_code,
    error_message = v_error_message,
    ergonomics_error_code = v_error_code,
    ergonomics_error_message = v_error_message
  where id = p_analysis_id
    and status = 'processing'::public.analysis_status
    and processing_stage = 'ergonomics-processing'
    and worker_id = btrim(coalesce(p_worker_id, ''));
  return found;
end;
$$;

create or replace function public.retry_ergonomics_analysis(p_analysis_id uuid)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
begin
  update public.analyses
  set
    status = 'queued'::public.analysis_status,
    progress = 75,
    processing_stage = 'ready-for-ergonomics',
    worker_id = null,
    claimed_at = null,
    heartbeat_at = null,
    queued_at = now(),
    completed_at = null,
    error_code = null,
    error_message = null,
    ergonomics_metrics_path = null,
    ergonomics_metrics_version = null,
    ergonomics_processed_frames = null,
    ergonomics_valid_metric_ratio = null,
    ergonomics_metrics_summary = null,
    ergonomics_completed_at = null,
    ergonomics_error_code = null,
    ergonomics_error_message = null
  where id = p_analysis_id
    and result_json_path is not null
    and btrim(result_json_path) <> ''
    and (
      (status = 'failed'::public.analysis_status and processing_stage = 'ergonomics-failed')
      or
      (status = 'queued'::public.analysis_status and processing_stage = 'ready-for-risk-assessment')
    );
  return found;
end;
$$;

-- ============================================================
-- Risk Worker V1 database fields and constraints
-- ============================================================

alter table public.analyses
  add column if not exists risk_assessment_path text,
  add column if not exists risk_assessment_version text,
  add column if not exists risk_profile_id text,
  add column if not exists risk_profile_version text,
  add column if not exists risk_profile_status text,
  add column if not exists risk_processed_frames integer,
  add column if not exists risk_valid_metric_ratio numeric(7, 6),
  add column if not exists risk_overall_level text,
  add column if not exists risk_assessment_summary jsonb,
  add column if not exists risk_completed_at timestamptz,
  add column if not exists risk_error_code text,
  add column if not exists risk_error_message text,
  add column if not exists risk_worker_id text,
  add column if not exists risk_started_at timestamptz,
  add column if not exists risk_attempts integer not null default 0;

alter table public.analyses
  drop constraint if exists analyses_risk_assessment_path_not_blank,
  drop constraint if exists analyses_risk_assessment_version_not_blank,
  drop constraint if exists analyses_risk_profile_id_not_blank,
  drop constraint if exists analyses_risk_profile_version_not_blank,
  drop constraint if exists analyses_risk_profile_status_check,
  drop constraint if exists analyses_risk_processed_frames_check,
  drop constraint if exists analyses_risk_valid_metric_ratio_check,
  drop constraint if exists analyses_risk_overall_level_check,
  drop constraint if exists analyses_risk_assessment_summary_object_check,
  drop constraint if exists analyses_risk_attempts_check;

alter table public.analyses
  add constraint analyses_risk_assessment_path_not_blank
    check (risk_assessment_path is null or btrim(risk_assessment_path) <> ''),
  add constraint analyses_risk_assessment_version_not_blank
    check (risk_assessment_version is null or btrim(risk_assessment_version) <> ''),
  add constraint analyses_risk_profile_id_not_blank
    check (risk_profile_id is null or btrim(risk_profile_id) <> ''),
  add constraint analyses_risk_profile_version_not_blank
    check (risk_profile_version is null or btrim(risk_profile_version) <> ''),
  add constraint analyses_risk_profile_status_check
    check (
      risk_profile_status is null
      or risk_profile_status in ('development', 'draft', 'approved', 'archived')
    ),
  add constraint analyses_risk_processed_frames_check
    check (risk_processed_frames is null or risk_processed_frames >= 1),
  add constraint analyses_risk_valid_metric_ratio_check
    check (risk_valid_metric_ratio is null or risk_valid_metric_ratio between 0 and 1),
  add constraint analyses_risk_overall_level_check
    check (
      risk_overall_level is null
      or risk_overall_level in ('low', 'moderate', 'high', 'critical', 'insufficient_data')
    ),
  add constraint analyses_risk_assessment_summary_object_check
    check (
      risk_assessment_summary is null
      or jsonb_typeof(risk_assessment_summary) = 'object'
    ),
  add constraint analyses_risk_attempts_check
    check (risk_attempts >= 0);

create index if not exists analyses_risk_queue_claim_idx
on public.analyses (queued_at, created_at, id)
where
  status = 'queued'::public.analysis_status
  and processing_stage = 'ready-for-risk-assessment'
  and ergonomics_metrics_path is not null
  and btrim(ergonomics_metrics_path) <> '';

-- ============================================================
-- Atomic claim: ready-for-risk-assessment -> risk-processing
-- ============================================================

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
    a.id,
    a.user_id,
    a.title,
    a.status,
    a.progress,
    a.processing_stage,
    a.ergonomics_metrics_path,
    a.worker_id;
end;
$$;

-- ============================================================
-- Atomic completion: risk-processing -> ready-for-report
-- ============================================================

create or replace function public.complete_risk_assessment_v1(
  p_analysis_id uuid,
  p_worker_id text,
  p_assessment_path text,
  p_assessment_version text,
  p_profile_id text,
  p_profile_version text,
  p_profile_status text,
  p_processed_frames integer,
  p_valid_metric_ratio numeric,
  p_overall_level text,
  p_assessment_summary jsonb
)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_owner_id uuid;
  v_expected_path text;
begin
  if btrim(coalesce(p_worker_id, '')) = '' then
    raise exception 'Worker ID must not be empty.';
  end if;
  if btrim(coalesce(p_assessment_path, '')) = '' then
    raise exception 'Risk assessment path must not be empty.';
  end if;
  if btrim(coalesce(p_assessment_version, '')) = '' then
    raise exception 'Risk assessment version must not be empty.';
  end if;
  if btrim(coalesce(p_profile_id, '')) = '' then
    raise exception 'Risk profile ID must not be empty.';
  end if;
  if btrim(coalesce(p_profile_version, '')) = '' then
    raise exception 'Risk profile version must not be empty.';
  end if;
  if p_profile_status is null
     or p_profile_status not in ('development', 'draft', 'approved', 'archived') then
    raise exception 'Unsupported risk profile status.';
  end if;
  if p_processed_frames is null or p_processed_frames < 1 then
    raise exception 'Risk assessment must contain at least one frame.';
  end if;
  if p_valid_metric_ratio is null or p_valid_metric_ratio < 0 or p_valid_metric_ratio > 1 then
    raise exception 'Valid metric coverage must be between 0 and 1.';
  end if;
  if p_overall_level is null
     or p_overall_level not in ('low', 'moderate', 'high', 'critical', 'insufficient_data') then
    raise exception 'Unsupported overall risk level.';
  end if;
  if p_assessment_summary is null or jsonb_typeof(p_assessment_summary) <> 'object' then
    raise exception 'Risk assessment summary must be a JSON object.';
  end if;
  if (p_assessment_summary ->> 'risk_engine_version') is distinct from p_assessment_version
     or (p_assessment_summary ->> 'overall_level') is distinct from p_overall_level
     or (p_assessment_summary ->> 'frame_count')::integer is distinct from p_processed_frames
     or (p_assessment_summary ->> 'valid_metric_ratio') is null
     or abs((p_assessment_summary ->> 'valid_metric_ratio')::numeric - p_valid_metric_ratio) > 0.000001
     or (p_assessment_summary #>> '{profile,profile_id}') is distinct from p_profile_id
     or (p_assessment_summary #>> '{profile,profile_version}') is distinct from p_profile_version
     or (p_assessment_summary #>> '{profile,status}') is distinct from p_profile_status then
    raise exception 'Risk assessment summary is inconsistent with metadata.';
  end if;

  select a.user_id
  into v_owner_id
  from public.analyses as a
  where a.id = p_analysis_id
    and a.status = 'processing'::public.analysis_status
    and a.processing_stage = 'risk-processing'
    and a.worker_id = btrim(p_worker_id)
    and a.risk_worker_id = btrim(p_worker_id)
  for update;

  if not found then
    return false;
  end if;

  v_expected_path := v_owner_id::text || '/' || p_analysis_id::text
    || '/results/risk-assessment.json';

  if p_assessment_path <> v_expected_path then
    raise exception 'Invalid risk assessment storage path.';
  end if;
  if not exists (
    select 1 from storage.objects
    where bucket_id = 'analysis-results' and name = p_assessment_path
  ) then
    raise exception 'Risk assessment object does not exist in Storage.';
  end if;

  update public.analyses
  set
    status = 'queued'::public.analysis_status,
    progress = greatest(coalesce(progress, 0), 97),
    processing_stage = 'ready-for-report',
    risk_assessment_path = p_assessment_path,
    risk_assessment_version = left(btrim(p_assessment_version), 80),
    risk_profile_id = left(btrim(p_profile_id), 160),
    risk_profile_version = left(btrim(p_profile_version), 80),
    risk_profile_status = p_profile_status,
    risk_processed_frames = p_processed_frames,
    risk_valid_metric_ratio = round(p_valid_metric_ratio, 6),
    risk_overall_level = p_overall_level,
    risk_assessment_summary = p_assessment_summary,
    risk_completed_at = now(),
    worker_id = null,
    claimed_at = null,
    heartbeat_at = null,
    queued_at = now(),
    error_code = null,
    error_message = null,
    risk_error_code = null,
    risk_error_message = null
  where id = p_analysis_id
    and status = 'processing'::public.analysis_status
    and processing_stage = 'risk-processing'
    and worker_id = btrim(p_worker_id)
    and risk_worker_id = btrim(p_worker_id);

  return found;
end;
$$;

-- ============================================================
-- Failure and retry affect only the risk stage. Pose and ergonomics
-- metadata remain untouched.
-- ============================================================

create or replace function public.fail_risk_processing(
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
    coalesce(nullif(btrim(coalesce(p_error_code, '')), ''), 'RISK_WORKER_ERROR'),
    100
  );
  v_error_message text := left(
    coalesce(nullif(btrim(coalesce(p_error_message, '')), ''), 'Unknown Risk Worker error.'),
    2000
  );
begin
  update public.analyses
  set
    status = 'failed'::public.analysis_status,
    processing_stage = 'risk-failed',
    worker_id = null,
    claimed_at = null,
    heartbeat_at = null,
    error_code = v_error_code,
    error_message = v_error_message,
    risk_error_code = v_error_code,
    risk_error_message = v_error_message
  where id = p_analysis_id
    and status = 'processing'::public.analysis_status
    and processing_stage = 'risk-processing'
    and worker_id = btrim(coalesce(p_worker_id, ''))
    and risk_worker_id = btrim(coalesce(p_worker_id, ''));
  return found;
end;
$$;

create or replace function public.retry_risk_analysis(p_analysis_id uuid)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
begin
  update public.analyses
  set
    status = 'queued'::public.analysis_status,
    progress = 90,
    processing_stage = 'ready-for-risk-assessment',
    worker_id = null,
    claimed_at = null,
    heartbeat_at = null,
    queued_at = now(),
    completed_at = null,
    error_code = null,
    error_message = null,
    risk_assessment_path = null,
    risk_assessment_version = null,
    risk_profile_id = null,
    risk_profile_version = null,
    risk_profile_status = null,
    risk_processed_frames = null,
    risk_valid_metric_ratio = null,
    risk_overall_level = null,
    risk_assessment_summary = null,
    risk_completed_at = null,
    risk_error_code = null,
    risk_error_message = null,
    risk_worker_id = null,
    risk_started_at = null
  where id = p_analysis_id
    and ergonomics_metrics_path is not null
    and btrim(ergonomics_metrics_path) <> ''
    and (
      (status = 'failed'::public.analysis_status and processing_stage = 'risk-failed')
      or
      (status = 'queued'::public.analysis_status and processing_stage = 'ready-for-report')
      or
      (
        status = 'processing'::public.analysis_status
        and processing_stage = 'risk-processing'
        and risk_started_at < now() - interval '30 minutes'
      )
    );
  return found;
end;
$$;

-- Keep the global progress monotonic while the report stage remains pending.
create or replace function public.normalize_analysis_pipeline_progress()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if new.status = 'completed'::public.analysis_status then
    new.progress := 100;
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
set progress = greatest(coalesce(progress, 0), 90)
where processing_stage = 'ready-for-risk-assessment';

update public.analyses
set progress = greatest(coalesce(progress, 0), 97)
where processing_stage = 'ready-for-report';

revoke execute on function public.claim_next_ergonomics_analysis(text)
from public, anon, authenticated;
revoke execute on function public.complete_ergonomics_metrics_v1(
  uuid, text, text, text, integer, numeric, jsonb
) from public, anon, authenticated;
revoke execute on function public.fail_ergonomics_processing(uuid, text, text, text)
from public, anon, authenticated;
revoke execute on function public.retry_ergonomics_analysis(uuid)
from public, anon, authenticated;

revoke execute on function public.claim_next_risk_analysis(text)
from public, anon, authenticated;
revoke execute on function public.complete_risk_assessment_v1(
  uuid, text, text, text, text, text, text, integer, numeric, text, jsonb
) from public, anon, authenticated;
revoke execute on function public.fail_risk_processing(uuid, text, text, text)
from public, anon, authenticated;
revoke execute on function public.retry_risk_analysis(uuid)
from public, anon, authenticated;

grant execute on function public.claim_next_ergonomics_analysis(text) to service_role;
grant execute on function public.complete_ergonomics_metrics_v1(
  uuid, text, text, text, integer, numeric, jsonb
) to service_role;
grant execute on function public.fail_ergonomics_processing(uuid, text, text, text)
to service_role;
grant execute on function public.retry_ergonomics_analysis(uuid) to service_role;

grant execute on function public.claim_next_risk_analysis(text) to service_role;
grant execute on function public.complete_risk_assessment_v1(
  uuid, text, text, text, text, text, text, integer, numeric, text, jsonb
) to service_role;
grant execute on function public.fail_risk_processing(uuid, text, text, text)
to service_role;
grant execute on function public.retry_risk_analysis(uuid) to service_role;

notify pgrst, 'reload schema';
