-- Fix the claim RPC result types without changing its public contract or claim logic.
-- PostgreSQL requires every RETURN QUERY column to match RETURNS TABLE exactly.

create or replace function public.claim_next_ergonomics_analysis(p_worker_id text)
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
    a.id::uuid,
    a.user_id::uuid,
    a.title::text,
    a.status::public.analysis_status,
    a.progress::integer,
    a.result_json_path::text,
    a.processing_stage::text,
    a.worker_id::text;
end;
$$;

revoke all on function public.claim_next_ergonomics_analysis(text) from public;
revoke all on function public.claim_next_ergonomics_analysis(text) from anon;
revoke all on function public.claim_next_ergonomics_analysis(text) from authenticated;
grant execute on function public.claim_next_ergonomics_analysis(text) to service_role;

notify pgrst, 'reload schema';
