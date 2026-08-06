-- ============================================================
-- ERGONOMIA AI
-- Osobny etap Ergonomics Metrics Engine V1
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
  drop constraint if exists analyses_ergonomics_metrics_path_not_blank;

alter table public.analyses
  add constraint analyses_ergonomics_metrics_path_not_blank
  check (
    ergonomics_metrics_path is null
    or btrim(ergonomics_metrics_path) <> ''
  );

alter table public.analyses
  drop constraint if exists analyses_ergonomics_processed_frames_check;

alter table public.analyses
  add constraint analyses_ergonomics_processed_frames_check
  check (
    ergonomics_processed_frames is null
    or ergonomics_processed_frames >= 0
  );

alter table public.analyses
  drop constraint if exists analyses_ergonomics_valid_metric_ratio_check;

alter table public.analyses
  add constraint analyses_ergonomics_valid_metric_ratio_check
  check (
    ergonomics_valid_metric_ratio is null
    or ergonomics_valid_metric_ratio between 0 and 1
  );

alter table public.analyses
  drop constraint if exists analyses_ergonomics_metrics_summary_object_check;

alter table public.analyses
  add constraint analyses_ergonomics_metrics_summary_object_check
  check (
    ergonomics_metrics_summary is null
    or jsonb_typeof(ergonomics_metrics_summary) = 'object'
  );

create index if not exists analyses_ergonomics_queue_claim_idx
on public.analyses (
  queued_at,
  created_at,
  id
)
where
  status = 'queued'::public.analysis_status
  and processing_stage = 'ready-for-ergonomics'
  and result_json_path is not null
  and btrim(result_json_path) <> '';

-- ============================================================
-- ATOMOWE PRZEJĘCIE ETAPU ERGONOMICZNEGO
-- ============================================================

create or replace function public.claim_next_ergonomics_analysis(
  p_worker_id text
)
returns table (
  id uuid,
  user_id uuid,
  title text,
  status public.analysis_status,
  progress integer,
  result_json_path text,
  worker_id text
)
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_worker_id text;
begin
  v_worker_id := btrim(coalesce(p_worker_id, ''));

  if v_worker_id = '' then
    raise exception 'Worker ID nie może być pusty.';
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
    order by
      coalesce(a.queued_at, a.created_at),
      a.created_at,
      a.id
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
    a.id::uuid,
    a.user_id::uuid,
    a.title::text,
    a.status::public.analysis_status,
    a.progress::integer,
    a.result_json_path::text,
    a.worker_id::text;
end;
$$;

-- ============================================================
-- ZAKOŃCZENIE ERGONOMICS METRICS ENGINE V1
-- ============================================================

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
    raise exception 'Worker ID nie może być pusty.';
  end if;

  if btrim(coalesce(p_metrics_path, '')) = '' then
    raise exception 'Ścieżka metryk nie może być pusta.';
  end if;

  if btrim(coalesce(p_metrics_version, '')) = '' then
    raise exception 'Wersja metryk nie może być pusta.';
  end if;

  if p_processed_frames is null or p_processed_frames < 1 then
    raise exception 'Dokument metryk musi zawierać co najmniej jedną klatkę.';
  end if;

  if p_valid_metric_ratio is null
     or p_valid_metric_ratio < 0
     or p_valid_metric_ratio > 1 then
    raise exception 'Pokrycie poprawnymi danymi musi mieścić się w zakresie 0-1.';
  end if;

  if p_metrics_summary is null or jsonb_typeof(p_metrics_summary) <> 'object' then
    raise exception 'Podsumowanie metryk musi być obiektem JSON.';
  end if;

  select a.user_id
  into v_owner_id
  from public.analyses as a
  where a.id = p_analysis_id
    and a.status = 'processing'::public.analysis_status
    and a.processing_stage = 'ergonomics-processing'
    and a.worker_id = btrim(coalesce(p_worker_id, ''))
  for update;

  if not found then
    return false;
  end if;

  v_expected_path :=
    v_owner_id::text
    || '/'
    || p_analysis_id::text
    || '/results/ergonomics-metrics.json';

  if p_metrics_path <> v_expected_path then
    raise exception 'Nieprawidłowa ścieżka pliku metryk ergonomicznych.';
  end if;

  if not exists (
    select 1
    from storage.objects
    where bucket_id = 'analysis-results'
      and name = p_metrics_path
  ) then
    raise exception 'Plik metryk ergonomicznych nie istnieje w Storage.';
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
    and worker_id = btrim(coalesce(p_worker_id, ''));

  return found;
end;
$$;

-- ============================================================
-- BŁĄD WYŁĄCZNIE ETAPU ERGONOMICZNEGO
-- ============================================================

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
  v_error_code text;
  v_error_message text;
begin
  v_error_code := left(
    coalesce(nullif(btrim(coalesce(p_error_code, '')), ''), 'ERGONOMICS_WORKER_ERROR'),
    100
  );
  v_error_message := left(
    coalesce(nullif(btrim(coalesce(p_error_message, '')), ''), 'Nieznany błąd Ergonomics Worker.'),
    2000
  );

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

-- ============================================================
-- PONOWIENIE WYŁĄCZNIE ETAPU ERGONOMICZNEGO
-- ============================================================

create or replace function public.retry_ergonomics_analysis(
  p_analysis_id uuid
)
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
      (
        status = 'failed'::public.analysis_status
        and processing_stage = 'ergonomics-failed'
      )
      or (
        status = 'queued'::public.analysis_status
        and processing_stage = 'ready-for-risk-assessment'
      )
    );

  return found;
end;
$$;

-- Spójny postęp całego, nadal nieukończonego pipeline'u.
create or replace function public.normalize_analysis_pipeline_progress()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if new.status = 'completed'::public.analysis_status then
    new.progress := 100;
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

revoke execute
on function public.claim_next_ergonomics_analysis(text)
from public, anon, authenticated;

revoke execute
on function public.complete_ergonomics_metrics_v1(
  uuid, text, text, text, integer, numeric, jsonb
)
from public, anon, authenticated;

revoke execute
on function public.fail_ergonomics_processing(uuid, text, text, text)
from public, anon, authenticated;

revoke execute
on function public.retry_ergonomics_analysis(uuid)
from public, anon, authenticated;

grant execute
on function public.claim_next_ergonomics_analysis(text)
to service_role;

grant execute
on function public.complete_ergonomics_metrics_v1(
  uuid, text, text, text, integer, numeric, jsonb
)
to service_role;

grant execute
on function public.fail_ergonomics_processing(uuid, text, text, text)
to service_role;

grant execute
on function public.retry_ergonomics_analysis(uuid)
to service_role;
