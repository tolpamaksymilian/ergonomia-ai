-- ============================================================
-- ERGONOMIA AI
-- Atomowa kolejka zadań dla workerów AI
-- ============================================================

-- Dodatkowe informacje o aktualnym przetwarzaniu.
alter table public.analyses
  add column if not exists processing_stage text;

alter table public.analyses
  add column if not exists claimed_at timestamptz;

alter table public.analyses
  add column if not exists heartbeat_at timestamptz;

-- Indeks wspierający pobieranie najstarszej analizy z kolejki.
create index if not exists analyses_worker_queue_claim_idx
on public.analyses (
  queued_at,
  created_at
)
where status = 'queued'::public.analysis_status;

-- ============================================================
-- PRZEJĘCIE JEDNEGO ZADANIA
-- ============================================================

create or replace function public.claim_next_analysis(
  p_worker_id text
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
  attempts integer,
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
    progress = 1,
    worker_id = v_worker_id,
    attempts = coalesce(a.attempts, 0) + 1,
    claimed_at = now(),
    heartbeat_at = now(),
    started_at = coalesce(a.started_at, now()),
    processing_stage = 'claimed',
    error_code = null,
    error_message = null
  from next_analysis
  where a.id = next_analysis.id
    and a.status = 'queued'::public.analysis_status
  returning
    a.id,
    a.user_id,
    a.title,
    a.status,
    a.progress,
    a.source_video_path,
    a.source_file_name,
    a.source_mime_type,
    a.source_size_bytes,
    a.attempts,
    a.worker_id;
end;
$$;

-- ============================================================
-- AKTUALIZACJA POSTĘPU
-- ============================================================

create or replace function public.update_analysis_progress(
  p_analysis_id uuid,
  p_worker_id text,
  p_progress integer,
  p_processing_stage text
)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
begin
  if p_progress < 1 or p_progress > 99 then
    raise exception
      'Postęp aktywnej analizy musi mieścić się w zakresie 1-99.';
  end if;

  update public.analyses
  set
    progress = p_progress,
    processing_stage = left(
      nullif(
        btrim(coalesce(p_processing_stage, '')),
        ''
      ),
      120
    ),
    heartbeat_at = now()
  where id = p_analysis_id
    and status = 'processing'::public.analysis_status
    and worker_id = btrim(coalesce(p_worker_id, ''));

  return found;
end;
$$;

-- ============================================================
-- ZWROT ZADANIA DO KOLEJKI
-- Używany obecnie wyłącznie podczas testów infrastruktury.
-- ============================================================

create or replace function public.requeue_analysis(
  p_analysis_id uuid,
  p_worker_id text
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
    progress = 0,
    worker_id = null,
    processing_stage = 'queued',
    claimed_at = null,
    heartbeat_at = null,
    started_at = null,
    queued_at = now(),
    error_code = null,
    error_message = null
  where id = p_analysis_id
    and status = 'processing'::public.analysis_status
    and worker_id = btrim(coalesce(p_worker_id, ''));

  return found;
end;
$$;

-- ============================================================
-- UPRAWNIENIA
-- ============================================================

revoke execute
on function public.claim_next_analysis(text)
from public, anon, authenticated;

revoke execute
on function public.update_analysis_progress(
  uuid,
  text,
  integer,
  text
)
from public, anon, authenticated;

revoke execute
on function public.requeue_analysis(uuid, text)
from public, anon, authenticated;

grant execute
on function public.claim_next_analysis(text)
to service_role;

grant execute
on function public.update_analysis_progress(
  uuid,
  text,
  integer,
  text
)
to service_role;

grant execute
on function public.requeue_analysis(uuid, text)
to service_role;