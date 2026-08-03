-- ============================================================
-- ERGONOMIA AI
-- Uzupełnienie wszystkich kolumn wymaganych przez worker queue
-- ============================================================

alter table public.analyses
  add column if not exists worker_id text,
  add column if not exists attempts integer not null default 0,
  add column if not exists processing_stage text,
  add column if not exists claimed_at timestamptz,
  add column if not exists heartbeat_at timestamptz,
  add column if not exists queued_at timestamptz,
  add column if not exists started_at timestamptz,
  add column if not exists completed_at timestamptz;

alter table public.analyses
  drop constraint if exists analyses_attempts_check;

alter table public.analyses
  add constraint analyses_attempts_check
  check (attempts >= 0);

-- Uzupełnienie queued_at dla istniejących zadań.
update public.analyses
set queued_at = coalesce(
  queued_at,
  created_at,
  now()
)
where status = 'queued'::public.analysis_status;