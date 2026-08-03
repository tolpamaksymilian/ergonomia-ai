-- ============================================================
-- ERGONOMIA AI
-- Wyniki estymacji pozy RTMW
-- ============================================================

-- ------------------------------------------------------------
-- PRYWATNY BUCKET WYNIKÓW
-- ------------------------------------------------------------

insert into storage.buckets (
  id,
  name,
  public,
  file_size_limit,
  allowed_mime_types
)
values (
  'analysis-results',
  'analysis-results',
  false,
  52428800,
  array[
    'video/mp4',
    'application/json',
    'application/gzip',
    'image/jpeg',
    'application/pdf'
  ]::text[]
)
on conflict (id)
do update set
  public = excluded.public,
  file_size_limit = excluded.file_size_limit,
  allowed_mime_types = excluded.allowed_mime_types;

-- ------------------------------------------------------------
-- ODCZYT WYNIKÓW
-- ------------------------------------------------------------

drop policy if exists
  "Users can read own analysis results"
on storage.objects;

create policy
  "Users can read own analysis results"
on storage.objects
for select
to authenticated
using (
  bucket_id = 'analysis-results'
  and (
    (storage.foldername(name))[1]
      = (select auth.uid())::text

    or

    (select public.is_admin())
  )
);

-- ------------------------------------------------------------
-- USUWANIE WYNIKÓW
-- ------------------------------------------------------------

drop policy if exists
  "Users can delete own analysis results"
on storage.objects;

create policy
  "Users can delete own analysis results"
on storage.objects
for delete
to authenticated
using (
  bucket_id = 'analysis-results'
  and (
    (storage.foldername(name))[1]
      = (select auth.uid())::text

    or

    (select public.is_admin())
  )
);

-- ------------------------------------------------------------
-- METADANE ESTYMACJI POZY
-- ------------------------------------------------------------

alter table public.analyses
  add column if not exists pose_model text;

alter table public.analyses
  add column if not exists pose_sample_stride integer;

alter table public.analyses
  add column if not exists pose_processed_frames integer;

alter table public.analyses
  add column if not exists pose_detected_frames integer;

alter table public.analyses
  add column if not exists pose_average_confidence numeric(7, 6);

alter table public.analyses
  add column if not exists pose_completed_at timestamptz;

alter table public.analyses
  drop constraint if exists analyses_pose_sample_stride_check;

alter table public.analyses
  add constraint analyses_pose_sample_stride_check
  check (
    pose_sample_stride is null
    or pose_sample_stride >= 1
  );

alter table public.analyses
  drop constraint if exists analyses_pose_processed_frames_check;

alter table public.analyses
  add constraint analyses_pose_processed_frames_check
  check (
    pose_processed_frames is null
    or pose_processed_frames >= 0
  );

alter table public.analyses
  drop constraint if exists analyses_pose_detected_frames_check;

alter table public.analyses
  add constraint analyses_pose_detected_frames_check
  check (
    pose_detected_frames is null
    or pose_detected_frames >= 0
  );

alter table public.analyses
  drop constraint if exists analyses_pose_average_confidence_check;

alter table public.analyses
  add constraint analyses_pose_average_confidence_check
  check (
    pose_average_confidence is null
    or (
      pose_average_confidence >= 0
      and pose_average_confidence <= 1
    )
  );

-- ============================================================
-- PRZEJĘCIE ANALIZY GOTOWEJ DO MODELU POZY
-- ============================================================

create or replace function public.claim_next_pose_analysis(
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
  v_worker_id text;
begin
  v_worker_id :=
    btrim(coalesce(p_worker_id, ''));

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

      and a.processing_stage =
        'ready-for-ai'

    order by
      coalesce(a.queued_at, a.created_at),
      a.created_at,
      a.id

    for update skip locked
    limit 1
  )
  update public.analyses as a
  set
    status =
      'processing'::public.analysis_status,

    progress = 20,

    worker_id = v_worker_id,

    attempts =
      coalesce(a.attempts, 0) + 1,

    claimed_at = now(),

    heartbeat_at = now(),

    started_at =
      coalesce(a.started_at, now()),

    processing_stage = 'pose-claimed',

    error_code = null,

    error_message = null
  from next_analysis
  where
    a.id = next_analysis.id

    and a.status =
      'queued'::public.analysis_status

    and a.processing_stage =
      'ready-for-ai'

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

-- ============================================================
-- ZAKOŃCZENIE ESTYMACJI POZY
-- ============================================================

create or replace function public.complete_pose_inference(
  p_analysis_id uuid,
  p_worker_id text,
  p_result_video_path text,
  p_result_json_path text,
  p_thumbnail_path text,
  p_pose_model text,
  p_sample_stride integer,
  p_processed_frames integer,
  p_detected_frames integer,
  p_average_confidence numeric
)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_owner_id uuid;
  v_expected_prefix text;
begin
  if p_sample_stride < 1 then
    raise exception
      'Interwał próbkowania musi być większy od zera.';
  end if;

  if p_processed_frames < 1 then
    raise exception
      'Liczba przetworzonych klatek musi być większa od zera.';
  end if;

  if p_detected_frames < 0 then
    raise exception
      'Liczba wykrytych klatek nie może być ujemna.';
  end if;

  if p_detected_frames > p_processed_frames then
    raise exception
      'Liczba wykrytych klatek nie może przekraczać liczby przetworzonych klatek.';
  end if;

  if (
    p_average_confidence < 0
    or p_average_confidence > 1
  ) then
    raise exception
      'Średnia pewność musi mieścić się w zakresie 0-1.';
  end if;

  select a.user_id
  into v_owner_id
  from public.analyses as a
  where
    a.id = p_analysis_id

    and a.status =
      'processing'::public.analysis_status

    and a.worker_id =
      btrim(coalesce(p_worker_id, ''))

  for update;

  if v_owner_id is null then
    raise exception
      'Nie znaleziono analizy przejętej przez tego workera.';
  end if;

  v_expected_prefix :=
    v_owner_id::text
    || '/'
    || p_analysis_id::text
    || '/results/';

  if p_result_video_path not like
    v_expected_prefix || '%'
  then
    raise exception
      'Nieprawidłowa ścieżka filmu wynikowego.';
  end if;

  if p_result_json_path not like
    v_expected_prefix || '%'
  then
    raise exception
      'Nieprawidłowa ścieżka danych JSON.';
  end if;

  if p_thumbnail_path not like
    v_expected_prefix || '%'
  then
    raise exception
      'Nieprawidłowa ścieżka miniatury.';
  end if;

  if not exists (
    select 1
    from storage.objects
    where
      bucket_id = 'analysis-results'
      and name = p_result_video_path
  ) then
    raise exception
      'Film wynikowy nie istnieje w Storage.';
  end if;

  if not exists (
    select 1
    from storage.objects
    where
      bucket_id = 'analysis-results'
      and name = p_result_json_path
  ) then
    raise exception
      'Plik JSON nie istnieje w Storage.';
  end if;

  if not exists (
    select 1
    from storage.objects
    where
      bucket_id = 'analysis-results'
      and name = p_thumbnail_path
  ) then
    raise exception
      'Miniatura nie istnieje w Storage.';
  end if;

  update public.analyses
  set
    status =
      'queued'::public.analysis_status,

    progress = 0,

    worker_id = null,

    processing_stage =
      'ready-for-ergonomics',

    result_video_path =
      p_result_video_path,

    result_json_path =
      p_result_json_path,

    thumbnail_path =
      p_thumbnail_path,

    pose_model = left(
      nullif(
        btrim(coalesce(p_pose_model, '')),
        ''
      ),
      120
    ),

    pose_sample_stride =
      p_sample_stride,

    pose_processed_frames =
      p_processed_frames,

    pose_detected_frames =
      p_detected_frames,

    pose_average_confidence =
      round(p_average_confidence, 6),

    pose_completed_at = now(),

    queued_at = now(),

    claimed_at = null,

    heartbeat_at = now(),

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
-- UPRAWNIENIA
-- ============================================================

revoke execute
on function public.claim_next_pose_analysis(text)
from public, anon, authenticated;

revoke execute
on function public.complete_pose_inference(
  uuid,
  text,
  text,
  text,
  text,
  text,
  integer,
  integer,
  integer,
  numeric
)
from public, anon, authenticated;

grant execute
on function public.claim_next_pose_analysis(text)
to service_role;

grant execute
on function public.complete_pose_inference(
  uuid,
  text,
  text,
  text,
  text,
  text,
  integer,
  integer,
  integer,
  numeric
)
to service_role;