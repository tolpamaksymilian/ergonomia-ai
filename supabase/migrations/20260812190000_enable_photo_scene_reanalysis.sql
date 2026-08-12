-- Photo Scene Builder v0.4: authenticated, idempotent re-analysis control.
-- Existing detection_result and all manual scene_state data remain untouched.

create or replace function public.retry_scene_detection(p_analysis_id uuid)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_requeued boolean := false;
begin
  update public.analyses set
    status = 'queued'::public.analysis_status,
    progress = 10,
    processing_stage = 'ready-for-scene-detection',
    worker_id = null,
    claimed_at = null,
    heartbeat_at = null,
    queued_at = now(),
    error_code = null,
    error_message = null
  where id = p_analysis_id
    and analysis_type = 'PHOTO_SCENE'
    and source_image_path is not null
    and (user_id = (select auth.uid()) or (select public.is_admin()))
    and (
      processing_stage in ('scene-detection-failed', 'scene-ready')
      or processing_stage is null
      or (
        processing_stage = 'ready-for-scene-detection'
        and coalesce(updated_at, queued_at, created_at) < now() - interval '2 minutes'
      )
      or (
        processing_stage = 'scene-detection-processing'
        and coalesce(heartbeat_at, claimed_at, updated_at, created_at) < now() - interval '2 minutes'
      )
    );

  v_requeued := found;
  if v_requeued then
    update public.photo_scenes set
      detection_error_code = null,
      detection_error_message = null
    where analysis_id = p_analysis_id;
  end if;
  return v_requeued;
end;
$$;

revoke all on function public.retry_scene_detection(uuid) from public;
revoke all on function public.retry_scene_detection(uuid) from anon;
revoke all on function public.retry_scene_detection(uuid) from authenticated;
grant execute on function public.retry_scene_detection(uuid) to authenticated;

notify pgrst, 'reload schema';
