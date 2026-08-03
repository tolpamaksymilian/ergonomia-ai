-- ============================================================
-- ERGONOMIA AI
-- Preprocessing filmu przed właściwą analizą AI
-- ============================================================

-- ------------------------------------------------------------
-- METADANE TECHNICZNE FILMU
-- ------------------------------------------------------------

alter table public.analyses
  add column if not exists source_fps numeric(10, 3);

alter table public.analyses
  add column if not exists source_frame_count integer;

alter table public.analyses
  drop constraint if exists analyses_source_fps_check;

alter table public.analyses
  add constraint analyses_source_fps_check
  check (
    source_fps is null
    or source_fps > 0
  );

alter table public.analyses
  drop constraint if exists analyses_source_frame_count_check;

alter table public.analyses
  add constraint analyses_source_frame_count_check
  check (
    source_frame_count is null
    or source_frame_count >= 0
  );

-- ============================================================
-- PRZEJĘCIE ANALIZY DO PREPROCESSINGU
-- ============================================================
--
-- Funkcja pobiera tylko nowe zadania:
--   processing_stage IS NULL
--   processing_stage = queued
--   processing_stage = retry
--
-- Nie pobiera ponownie rekordów ready-for-ai.
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
  v_worker_id := btrim(
    coalesce(p_worker_id, '')
  );

  if v_worker_id = '' then
    raise exception
      'Worker ID nie może być pusty.';
  end if;

  return query
  with next_analysis as (
    select a.id
    from public.analyses as a
    where
      a.status =
        'queued'::public.analysis_status
      and coalesce(
        a.processing_stage,
        'queued'
      ) in (
        'queued',
        'retry'
      )
    order by
      coalesce(
        a.queued_at,
        a.created_at
      ),
      a.created_at,
      a.id
    for update skip locked
    limit 1
  )
  update public.analyses as a
  set
    status =
      'processing'::public.analysis_status,

    progress = 1,

    worker_id = v_worker_id,

    attempts =
      coalesce(a.attempts, 0) + 1,

    claimed_at = now(),

    heartbeat_at = now(),

    started_at =
      coalesce(a.started_at, now()),

    processing_stage =
      'claimed-for-preprocessing',

    error_code = null,

    error_message = null
  from next_analysis
  where
    a.id = next_analysis.id
    and a.status =
      'queued'::public.analysis_status
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
    a.attempts::integer,
    a.worker_id::text;
end;
$$;

-- ============================================================
-- ZAKOŃCZENIE PREPROCESSINGU
-- ============================================================

create or replace function public.complete_analysis_preprocessing(
  p_analysis_id uuid,
  p_worker_id text,
  p_width integer,
  p_height integer,
  p_fps numeric,
  p_frame_count integer,
  p_duration_seconds numeric
)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
begin
  if p_width <= 0 then
    raise exception
      'Szerokość filmu musi być większa od zera.';
  end if;

  if p_height <= 0 then
    raise exception
      'Wysokość filmu musi być większa od zera.';
  end if;

  if p_fps <= 0 then
    raise exception
      'FPS filmu musi być większy od zera.';
  end if;

  if p_frame_count <= 0 then
    raise exception
      'Liczba klatek musi być większa od zera.';
  end if;

  if p_duration_seconds <= 0 then
    raise exception
      'Długość filmu musi być większa od zera.';
  end if;

  update public.analyses
  set
    status =
      'queued'::public.analysis_status,

    progress = 0,

    worker_id = null,

    processing_stage = 'ready-for-ai',

    source_width = p_width,

    source_height = p_height,

    source_fps =
      round(p_fps, 3),

    source_frame_count =
      p_frame_count,

    source_duration_seconds =
      round(p_duration_seconds, 3),

    queued_at = now(),

    claimed_at = null,

    heartbeat_at = now(),

    started_at = null,

    error_code = null,

    error_message = null
  where
    id = p_analysis_id

    and status =
      'processing'::public.analysis_status

    and worker_id =
      btrim(coalesce(p_worker_id, ''));

  return found;
end;
$$;

-- ============================================================
-- BŁĄD PRZETWARZANIA
-- ============================================================

create or replace function public.fail_analysis_processing(
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
  update public.analyses
  set
    status =
      'failed'::public.analysis_status,

    worker_id = null,

    processing_stage =
      'processing-failed',

    heartbeat_at = now(),

    completed_at = now(),

    error_code = left(
      coalesce(
        nullif(
          btrim(p_error_code),
          ''
        ),
        'WORKER_ERROR'
      ),
      100
    ),

    error_message = left(
      coalesce(
        nullif(
          btrim(p_error_message),
          ''
        ),
        'Nieznany błąd workera.'
      ),
      2000
    )
  where
    id = p_analysis_id

    and status =
      'processing'::public.analysis_status

    and worker_id =
      btrim(coalesce(p_worker_id, ''));

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
on function public.complete_analysis_preprocessing(
  uuid,
  text,
  integer,
  integer,
  numeric,
  integer,
  numeric
)
from public, anon, authenticated;

revoke execute
on function public.fail_analysis_processing(
  uuid,
  text,
  text,
  text
)
from public, anon, authenticated;

grant execute
on function public.claim_next_analysis(text)
to service_role;

grant execute
on function public.complete_analysis_preprocessing(
  uuid,
  text,
  integer,
  integer,
  numeric,
  integer,
  numeric
)
to service_role;

grant execute
on function public.fail_analysis_processing(
  uuid,
  text,
  text,
  text
)
to service_role;