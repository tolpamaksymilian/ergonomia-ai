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

revoke execute
on function public.claim_next_analysis(text)
from public, anon, authenticated;

grant execute
on function public.claim_next_analysis(text)
to service_role;