-- ============================================================
-- ERGONOMIA AI
-- Pose Pipeline V2: aktywny fragment, tracking i jakość danych
-- ============================================================

alter table public.analyses
  add column if not exists active_segment_start_frame integer,
  add column if not exists active_segment_end_frame integer,
  add column if not exists active_segment_start_seconds numeric(12, 3),
  add column if not exists active_segment_end_seconds numeric(12, 3),
  add column if not exists active_segment_duration_seconds numeric(12, 3),
  add column if not exists pose_presence_ratio numeric(7, 6),
  add column if not exists pose_tracking_method text,
  add column if not exists pose_smoothing_method text,
  add column if not exists pose_quality_version text;

alter table public.analyses
  drop constraint if exists analyses_active_segment_frames_check;

alter table public.analyses
  add constraint analyses_active_segment_frames_check
  check (
    active_segment_start_frame is null
    or active_segment_end_frame is null
    or (
      active_segment_start_frame >= 0
      and active_segment_end_frame >= active_segment_start_frame
    )
  );

alter table public.analyses
  drop constraint if exists analyses_active_segment_seconds_check;

alter table public.analyses
  add constraint analyses_active_segment_seconds_check
  check (
    active_segment_start_seconds is null
    or active_segment_end_seconds is null
    or active_segment_duration_seconds is null
    or (
      active_segment_start_seconds >= 0
      and active_segment_end_seconds >= active_segment_start_seconds
      and active_segment_duration_seconds > 0
    )
  );

alter table public.analyses
  drop constraint if exists analyses_pose_presence_ratio_check;

alter table public.analyses
  add constraint analyses_pose_presence_ratio_check
  check (
    pose_presence_ratio is null
    or (
      pose_presence_ratio >= 0
      and pose_presence_ratio <= 1
    )
  );

-- ============================================================
-- ZAKOŃCZENIE PIPELINE POZY V2
-- ============================================================

create or replace function public.complete_pose_inference_v2(
  p_analysis_id uuid,
  p_worker_id text,
  p_result_video_path text,
  p_result_json_path text,
  p_thumbnail_path text,
  p_pose_model text,
  p_sample_stride integer,
  p_processed_frames integer,
  p_detected_frames integer,
  p_average_confidence numeric,
  p_active_start_frame integer,
  p_active_end_frame integer,
  p_active_start_seconds numeric,
  p_active_end_seconds numeric,
  p_active_duration_seconds numeric,
  p_presence_ratio numeric,
  p_tracking_method text,
  p_smoothing_method text,
  p_quality_version text
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
    raise exception 'Interwał próbkowania musi być większy od zera.';
  end if;

  if p_processed_frames < 1 then
    raise exception 'Liczba przetworzonych klatek musi być większa od zera.';
  end if;

  if p_detected_frames < 0 or p_detected_frames > p_processed_frames then
    raise exception 'Nieprawidłowa liczba klatek z wykrytą osobą.';
  end if;

  if p_average_confidence < 0 or p_average_confidence > 1 then
    raise exception 'Średnia pewność musi mieścić się w zakresie 0-1.';
  end if;

  if p_presence_ratio < 0 or p_presence_ratio > 1 then
    raise exception 'Pokrycie obecności musi mieścić się w zakresie 0-1.';
  end if;

  if p_active_start_frame < 0 or p_active_end_frame < p_active_start_frame then
    raise exception 'Nieprawidłowy zakres klatek aktywnego fragmentu.';
  end if;

  if p_active_start_seconds < 0
     or p_active_end_seconds < p_active_start_seconds
     or p_active_duration_seconds <= 0 then
    raise exception 'Nieprawidłowy czas aktywnego fragmentu.';
  end if;

  select a.user_id
  into v_owner_id
  from public.analyses as a
  where a.id = p_analysis_id
    and a.status = 'processing'::public.analysis_status
    and a.worker_id = btrim(coalesce(p_worker_id, ''))
  for update;

  if v_owner_id is null then
    raise exception 'Nie znaleziono analizy przejętej przez tego workera.';
  end if;

  v_expected_prefix :=
    v_owner_id::text
    || '/'
    || p_analysis_id::text
    || '/results/';

  if p_result_video_path not like v_expected_prefix || '%' then
    raise exception 'Nieprawidłowa ścieżka filmu wynikowego.';
  end if;

  if p_result_json_path not like v_expected_prefix || '%' then
    raise exception 'Nieprawidłowa ścieżka danych JSON.';
  end if;

  if p_thumbnail_path not like v_expected_prefix || '%' then
    raise exception 'Nieprawidłowa ścieżka miniatury.';
  end if;

  if not exists (
    select 1
    from storage.objects
    where bucket_id = 'analysis-results'
      and name = p_result_video_path
  ) then
    raise exception 'Film wynikowy nie istnieje w Storage.';
  end if;

  if not exists (
    select 1
    from storage.objects
    where bucket_id = 'analysis-results'
      and name = p_result_json_path
  ) then
    raise exception 'Plik JSON nie istnieje w Storage.';
  end if;

  if not exists (
    select 1
    from storage.objects
    where bucket_id = 'analysis-results'
      and name = p_thumbnail_path
  ) then
    raise exception 'Miniatura nie istnieje w Storage.';
  end if;

  update public.analyses
  set
    status = 'queued'::public.analysis_status,
    progress = 75,
    worker_id = null,
    processing_stage = 'ready-for-ergonomics',

    result_video_path = p_result_video_path,
    result_json_path = p_result_json_path,
    thumbnail_path = p_thumbnail_path,

    pose_model = left(nullif(btrim(coalesce(p_pose_model, '')), ''), 120),
    pose_sample_stride = p_sample_stride,
    pose_processed_frames = p_processed_frames,
    pose_detected_frames = p_detected_frames,
    pose_average_confidence = round(p_average_confidence, 6),
    pose_completed_at = now(),

    active_segment_start_frame = p_active_start_frame,
    active_segment_end_frame = p_active_end_frame,
    active_segment_start_seconds = round(p_active_start_seconds, 3),
    active_segment_end_seconds = round(p_active_end_seconds, 3),
    active_segment_duration_seconds = round(p_active_duration_seconds, 3),
    pose_presence_ratio = round(p_presence_ratio, 6),
    pose_tracking_method = left(nullif(btrim(coalesce(p_tracking_method, '')), ''), 120),
    pose_smoothing_method = left(nullif(btrim(coalesce(p_smoothing_method, '')), ''), 120),
    pose_quality_version = left(nullif(btrim(coalesce(p_quality_version, '')), ''), 60),

    queued_at = now(),
    claimed_at = null,
    heartbeat_at = now(),
    error_code = null,
    error_message = null
  where id = p_analysis_id
    and status = 'processing'::public.analysis_status
    and worker_id = btrim(coalesce(p_worker_id, ''));

  return found;
end;
$$;

revoke execute
on function public.complete_pose_inference_v2(
  uuid,
  text,
  text,
  text,
  text,
  text,
  integer,
  integer,
  integer,
  numeric,
  integer,
  integer,
  numeric,
  numeric,
  numeric,
  numeric,
  text,
  text,
  text
)
from public, anon, authenticated;

grant execute
on function public.complete_pose_inference_v2(
  uuid,
  text,
  text,
  text,
  text,
  text,
  integer,
  integer,
  integer,
  numeric,
  integer,
  integer,
  numeric,
  numeric,
  numeric,
  numeric,
  text,
  text,
  text
)
to service_role;