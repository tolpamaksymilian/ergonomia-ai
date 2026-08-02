-- ============================================================
-- ERGONOMIA AI
-- Główna tabela analiz ergonomicznych
-- ============================================================

-- ------------------------------------------------------------
-- STATUS ANALIZY
-- ------------------------------------------------------------

do $$
begin
  create type public.analysis_status as enum (
    'draft',
    'uploading',
    'queued',
    'processing',
    'completed',
    'failed',
    'cancelled'
  );
exception
  when duplicate_object then null;
end
$$;

-- ------------------------------------------------------------
-- TABELA ANALIZ
-- ------------------------------------------------------------

create table if not exists public.analyses (
  id uuid
    primary key
    default gen_random_uuid(),

  user_id uuid
    not null
    references auth.users(id)
    on delete cascade,

  title varchar(120)
    not null,

  description text,

  status public.analysis_status
    not null
    default 'queued',

  progress smallint
    not null
    default 0
    check (
      progress >= 0
      and progress <= 100
    ),

  -- Plik źródłowy
  source_video_path text
    not null
    unique,

  source_file_name text
    not null,

  source_mime_type text
    not null,

  source_size_bytes bigint
    not null
    check (
      source_size_bytes > 0
    ),

  source_duration_seconds numeric(12, 3)
    check (
      source_duration_seconds is null
      or source_duration_seconds >= 0
    ),

  -- Parametry nagrania odczytane później przez worker
  source_width integer
    check (
      source_width is null
      or source_width > 0
    ),

  source_height integer
    check (
      source_height is null
      or source_height > 0
    ),

  source_fps numeric(10, 4)
    check (
      source_fps is null
      or source_fps > 0
    ),

  source_frame_count bigint
    check (
      source_frame_count is null
      or source_frame_count >= 0
    ),

  -- Pliki wynikowe
  result_video_path text,
  result_json_path text,
  report_pdf_path text,
  thumbnail_path text,

  -- Wynik podsumowujący
  final_score numeric(10, 2),

  risk_level text,

  critical_events_count integer
    check (
      critical_events_count is null
      or critical_events_count >= 0
    ),

  -- Informacje techniczne workera
  worker_id text,
  processing_attempts integer
    not null
    default 0
    check (
      processing_attempts >= 0
    ),

  error_code text,
  error_message text,

  queued_at timestamptz
    not null
    default now(),

  processing_started_at timestamptz,
  processing_completed_at timestamptz,

  created_at timestamptz
    not null
    default now(),

  updated_at timestamptz
    not null
    default now(),

  constraint analyses_title_not_blank
    check (
      length(trim(title)) >= 3
    ),

  constraint analyses_storage_path_matches_id
    check (
      source_video_path like
        user_id::text
        || '/'
        || id::text
        || '/source/%'
    )
);

-- ------------------------------------------------------------
-- INDEKSY
-- ------------------------------------------------------------

create index if not exists analyses_user_id_idx
on public.analyses (
  user_id
);

create index if not exists analyses_status_idx
on public.analyses (
  status
);

create index if not exists analyses_created_at_idx
on public.analyses (
  created_at desc
);

create index if not exists analyses_user_created_at_idx
on public.analyses (
  user_id,
  created_at desc
);

create index if not exists analyses_queue_idx
on public.analyses (
  status,
  queued_at
)
where status = 'queued';

-- ------------------------------------------------------------
-- ROW LEVEL SECURITY
-- ------------------------------------------------------------

alter table public.analyses
enable row level security;

revoke all
on table public.analyses
from anon;

revoke all
on table public.analyses
from authenticated;

grant select, insert
on table public.analyses
to authenticated;

-- Użytkownik widzi własne analizy.
-- Administrator widzi wszystkie analizy.

drop policy if exists
  "Users can read own analyses"
on public.analyses;

create policy
  "Users can read own analyses"
on public.analyses
for select
to authenticated
using (
  user_id = (select auth.uid())
  or (select public.is_admin())
);

-- Użytkownik może utworzyć wyłącznie własną analizę.
-- Rekord może powstać dopiero po przesłaniu filmu.
-- Pierwszym statusem jest queued.

drop policy if exists
  "Users can create own queued analyses"
on public.analyses;

create policy
  "Users can create own queued analyses"
on public.analyses
for insert
to authenticated
with check (
  (select auth.uid()) is not null
  and user_id = (select auth.uid())
  and status = 'queued'::public.analysis_status
  and progress = 0
  and source_video_path like
    (select auth.uid())::text
    || '/'
    || id::text
    || '/source/%'
);

-- ------------------------------------------------------------
-- AUTOMATYCZNE UPDATED_AT
-- ------------------------------------------------------------

create or replace function public.set_analysis_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists
  set_analyses_updated_at
on public.analyses;

create trigger set_analyses_updated_at
before update on public.analyses
for each row
execute procedure public.set_analysis_updated_at();