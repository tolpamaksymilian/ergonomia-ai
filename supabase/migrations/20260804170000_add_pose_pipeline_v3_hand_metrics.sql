-- ============================================================
-- ERGONOMIA AI
-- Pose Pipeline V3.0 — metryki jakości dłoni MediaPipe
-- ============================================================

alter table public.analyses
  add column if not exists hand_model text,
  add column if not exists left_hand_valid_ratio numeric(7, 6),
  add column if not exists right_hand_valid_ratio numeric(7, 6),
  add column if not exists left_hand_rejected_frames integer,
  add column if not exists right_hand_rejected_frames integer,
  add column if not exists hand_completed_at timestamptz;

alter table public.analyses
  drop constraint if exists analyses_left_hand_valid_ratio_check;

alter table public.analyses
  add constraint analyses_left_hand_valid_ratio_check
  check (
    left_hand_valid_ratio is null
    or left_hand_valid_ratio between 0 and 1
  );

alter table public.analyses
  drop constraint if exists analyses_right_hand_valid_ratio_check;

alter table public.analyses
  add constraint analyses_right_hand_valid_ratio_check
  check (
    right_hand_valid_ratio is null
    or right_hand_valid_ratio between 0 and 1
  );

alter table public.analyses
  drop constraint if exists analyses_left_hand_rejected_frames_check;

alter table public.analyses
  add constraint analyses_left_hand_rejected_frames_check
  check (
    left_hand_rejected_frames is null
    or left_hand_rejected_frames >= 0
  );

alter table public.analyses
  drop constraint if exists analyses_right_hand_rejected_frames_check;

alter table public.analyses
  add constraint analyses_right_hand_rejected_frames_check
  check (
    right_hand_rejected_frames is null
    or right_hand_rejected_frames >= 0
  );

-- Funkcja V3 wykorzystuje całą walidację i zapis V2,
-- a następnie uzupełnia metryki dedykowanego modelu dłoni.
create or replace function public.complete_pose_inference_v3(
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
  p_quality_version text,
  p_hand_model text,
  p_left_hand_valid_ratio numeric,
  p_right_hand_valid_ratio numeric,
  p_left_hand_rejected_frames integer,
  p_right_hand_rejected_frames integer
)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_completed boolean;
begin
  if p_left_hand_valid_ratio < 0 or p_left_hand_valid_ratio > 1 then
    raise exception 'Udział poprawnych klatek lewej dłoni musi mieścić się w zakresie 0-1.';
  end if;

  if p_right_hand_valid_ratio < 0 or p_right_hand_valid_ratio > 1 then
    raise exception 'Udział poprawnych klatek prawej dłoni musi mieścić się w zakresie 0-1.';
  end if;

  if p_left_hand_rejected_frames < 0 then
    raise exception 'Liczba odrzuconych klatek lewej dłoni nie może być ujemna.';
  end if;

  if p_right_hand_rejected_frames < 0 then
    raise exception 'Liczba odrzuconych klatek prawej dłoni nie może być ujemna.';
  end if;

  v_completed := public.complete_pose_inference_v2(
    p_analysis_id,
    p_worker_id,
    p_result_video_path,
    p_result_json_path,
    p_thumbnail_path,
    p_pose_model,
    p_sample_stride,
    p_processed_frames,
    p_detected_frames,
    p_average_confidence,
    p_active_start_frame,
    p_active_end_frame,
    p_active_start_seconds,
    p_active_end_seconds,
    p_active_duration_seconds,
    p_presence_ratio,
    p_tracking_method,
    p_smoothing_method,
    p_quality_version
  );

  if not coalesce(v_completed, false) then
    return false;
  end if;

  update public.analyses
  set
    hand_model = left(
      nullif(btrim(coalesce(p_hand_model, '')), ''),
      160
    ),
    left_hand_valid_ratio = round(p_left_hand_valid_ratio, 6),
    right_hand_valid_ratio = round(p_right_hand_valid_ratio, 6),
    left_hand_rejected_frames = p_left_hand_rejected_frames,
    right_hand_rejected_frames = p_right_hand_rejected_frames,
    hand_completed_at = now()
  where id = p_analysis_id;

  return found;
end;
$$;

revoke execute
on function public.complete_pose_inference_v3(
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
  text,
  text,
  numeric,
  numeric,
  integer,
  integer
)
from public, anon, authenticated;

grant execute
on function public.complete_pose_inference_v3(
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
  text,
  text,
  numeric,
  numeric,
  integer,
  integer
)
to service_role;
