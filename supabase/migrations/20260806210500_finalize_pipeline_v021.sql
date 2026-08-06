-- Ergonomia AI v0.2.1-beta.1
-- Final pipeline safeguards: monotonic progress, admin-only stage retry and
-- a read-only readiness diagnostic for the local service worker.

create or replace function public.normalize_analysis_pipeline_progress()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if new.status = 'completed'::public.analysis_status
     or new.processing_stage = 'completed' then
    new.progress := 100;
  elsif new.processing_stage = 'report-processing' then
    new.progress := greatest(coalesce(new.progress, 0), 98);
  elsif new.processing_stage = 'ready-for-report' then
    new.progress := greatest(coalesce(new.progress, 0), 97);
  elsif new.processing_stage = 'risk-processing' then
    new.progress := greatest(coalesce(new.progress, 0), 92);
  elsif new.processing_stage = 'ready-for-risk-assessment' then
    new.progress := greatest(coalesce(new.progress, 0), 90);
  elsif new.processing_stage = 'ergonomics-processing' then
    new.progress := greatest(coalesce(new.progress, 0), 78);
  elsif new.processing_stage = 'ready-for-ergonomics' then
    new.progress := greatest(coalesce(new.progress, 0), 75);
  elsif new.processing_stage in (
    'pose-claimed',
    'downloading-for-pose-v3',
    'pose-inference-active-segment-v3',
    'uploading-pose-results-v3',
    'saving-pose-results-v3'
  ) then
    new.progress := greatest(coalesce(new.progress, 0), 20);
  elsif new.processing_stage = 'ready-for-ai' then
    new.progress := greatest(coalesce(new.progress, 0), 20);
  elsif new.processing_stage in (
    'claimed',
    'claimed-for-preprocessing',
    'downloading-source',
    'preprocessing-video',
    'saving-preprocessing-results'
  ) then
    new.progress := greatest(coalesce(new.progress, 0), 1);
  end if;

  return new;
end;
$$;

drop trigger if exists analyses_normalize_pipeline_progress
on public.analyses;

create trigger analyses_normalize_pipeline_progress
before insert or update of status, processing_stage, progress
on public.analyses
for each row
execute procedure public.normalize_analysis_pipeline_progress();

update public.analyses
set progress = case
  when status = 'completed'::public.analysis_status
    or processing_stage = 'completed' then 100
  when processing_stage = 'report-processing' then greatest(progress, 98)
  when processing_stage = 'ready-for-report' then greatest(progress, 97)
  when processing_stage = 'risk-processing' then greatest(progress, 92)
  when processing_stage = 'ready-for-risk-assessment' then greatest(progress, 90)
  when processing_stage = 'ergonomics-processing' then greatest(progress, 78)
  when processing_stage = 'ready-for-ergonomics' then greatest(progress, 75)
  when processing_stage = 'ready-for-ai' then greatest(progress, 20)
  else progress
end
where status = 'completed'::public.analysis_status
   or processing_stage in (
     'completed',
     'report-processing',
     'ready-for-report',
     'risk-processing',
     'ready-for-risk-assessment',
     'ergonomics-processing',
     'ready-for-ergonomics',
     'ready-for-ai'
   );

create or replace function public.retry_failed_analysis_stage(
  p_analysis_id uuid
)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_analysis public.analyses%rowtype;
  v_next_stage text;
  v_next_progress integer;
begin
  if p_analysis_id is null then
    return false;
  end if;

  if not exists (
    select 1
    from public.profiles as p
    where p.id = (select auth.uid())
      and p.role = 'admin'
  ) then
    raise exception 'Administrator privileges are required.'
      using errcode = '42501';
  end if;

  select a.*
  into v_analysis
  from public.analyses as a
  where a.id = p_analysis_id
    and a.status = 'failed'::public.analysis_status
  for update;

  if not found then
    return false;
  end if;

  case v_analysis.processing_stage
    when 'processing-failed' then
      if v_analysis.source_width is not null
         and v_analysis.source_height is not null
         and v_analysis.source_fps is not null
         and v_analysis.source_frame_count is not null then
        v_next_stage := 'ready-for-ai';
        v_next_progress := 20;
      else
        v_next_stage := 'queued';
        v_next_progress := 0;
      end if;
    when 'ergonomics-failed' then
      if coalesce(btrim(v_analysis.result_json_path), '') = '' then
        return false;
      end if;
      v_next_stage := 'ready-for-ergonomics';
      v_next_progress := 75;
    when 'risk-failed' then
      if coalesce(btrim(v_analysis.ergonomics_metrics_path), '') = '' then
        return false;
      end if;
      v_next_stage := 'ready-for-risk-assessment';
      v_next_progress := 90;
    when 'report-failed' then
      if coalesce(btrim(v_analysis.risk_assessment_path), '') = '' then
        return false;
      end if;
      v_next_stage := 'ready-for-report';
      v_next_progress := 97;
    else
      return false;
  end case;

  update public.analyses
  set status = 'queued'::public.analysis_status,
      progress = v_next_progress,
      processing_stage = v_next_stage,
      worker_id = null,
      claimed_at = null,
      heartbeat_at = null,
      queued_at = now(),
      completed_at = null,
      processing_completed_at = null,
      error_code = null,
      error_message = null,
      ergonomics_error_code = case
        when v_analysis.processing_stage = 'ergonomics-failed' then null
        else ergonomics_error_code
      end,
      ergonomics_error_message = case
        when v_analysis.processing_stage = 'ergonomics-failed' then null
        else ergonomics_error_message
      end,
      risk_error_code = case
        when v_analysis.processing_stage = 'risk-failed' then null
        else risk_error_code
      end,
      risk_error_message = case
        when v_analysis.processing_stage = 'risk-failed' then null
        else risk_error_message
      end,
      risk_worker_id = case
        when v_analysis.processing_stage = 'risk-failed' then null
        else risk_worker_id
      end,
      report_error_code = case
        when v_analysis.processing_stage = 'report-failed' then null
        else report_error_code
      end,
      report_error_message = case
        when v_analysis.processing_stage = 'report-failed' then null
        else report_error_message
      end,
      report_worker_id = case
        when v_analysis.processing_stage = 'report-failed' then null
        else report_worker_id
      end
  where id = p_analysis_id
    and status = 'failed'::public.analysis_status
    and processing_stage = v_analysis.processing_stage;

  return found;
end;
$$;

revoke all on function public.retry_failed_analysis_stage(uuid)
from public, anon;
grant execute on function public.retry_failed_analysis_stage(uuid)
to authenticated;

create or replace function public.check_pipeline_readiness_v021()
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_required_columns text[] := array[
    'ergonomics_metrics_path', 'ergonomics_metrics_version',
    'ergonomics_processed_frames', 'ergonomics_valid_metric_ratio',
    'ergonomics_metrics_summary', 'ergonomics_completed_at',
    'risk_assessment_path', 'risk_assessment_version', 'risk_profile_id',
    'risk_processed_frames', 'risk_valid_metric_ratio', 'risk_overall_level',
    'risk_assessment_summary', 'risk_completed_at',
    'report_path', 'report_version', 'report_summary', 'report_completed_at'
  ];
  v_required_rpcs text[] := array[
    'claim_next_analysis', 'complete_analysis_preprocessing',
    'claim_next_pose_analysis', 'complete_pose_inference_v3',
    'claim_next_ergonomics_analysis', 'complete_ergonomics_metrics_v1',
    'claim_next_risk_analysis', 'complete_risk_assessment_v1',
    'claim_next_report_analysis', 'complete_report_v1'
  ];
  v_missing_columns text[];
  v_missing_rpcs text[];
  v_missing_execute text[];
  v_missing_buckets text[];
  v_public_buckets text[];
  v_completed_status boolean;
  v_stage_constraint_ok boolean;
begin
  select coalesce(array_agg(required_column order by required_column), array[]::text[])
  into v_missing_columns
  from unnest(v_required_columns) as required_column
  where not exists (
    select 1
    from information_schema.columns as c
    where c.table_schema = 'public'
      and c.table_name = 'analyses'
      and c.column_name = required_column
  );

  select coalesce(array_agg(required_rpc order by required_rpc), array[]::text[])
  into v_missing_rpcs
  from unnest(v_required_rpcs) as required_rpc
  where not exists (
    select 1
    from pg_catalog.pg_proc as p
    join pg_catalog.pg_namespace as n on n.oid = p.pronamespace
    where n.nspname = 'public' and p.proname = required_rpc
  );

  select coalesce(array_agg(required_rpc order by required_rpc), array[]::text[])
  into v_missing_execute
  from unnest(v_required_rpcs) as required_rpc
  where not exists (
    select 1
    from pg_catalog.pg_proc as p
    join pg_catalog.pg_namespace as n on n.oid = p.pronamespace
    where n.nspname = 'public'
      and p.proname = required_rpc
      and pg_catalog.has_function_privilege('service_role', p.oid, 'EXECUTE')
  );

  select coalesce(array_agg(required_bucket order by required_bucket), array[]::text[])
  into v_missing_buckets
  from unnest(array['analysis-videos', 'analysis-results']::text[]) as required_bucket
  where not exists (
    select 1 from storage.buckets as b where b.id = required_bucket
  );

  select coalesce(array_agg(b.id order by b.id), array[]::text[])
  into v_public_buckets
  from storage.buckets as b
  where b.id in ('analysis-videos', 'analysis-results') and b.public;

  select exists (
    select 1
    from pg_catalog.pg_enum as e
    join pg_catalog.pg_type as t on t.oid = e.enumtypid
    join pg_catalog.pg_namespace as n on n.oid = t.typnamespace
    where n.nspname = 'public'
      and t.typname = 'analysis_status'
      and e.enumlabel = 'completed'
  ) into v_completed_status;

  -- processing_stage is intentionally text. With no CHECK restriction it
  -- accepts every versioned worker stage used by the pipeline.
  select not exists (
    select 1
    from pg_catalog.pg_constraint as c
    where c.conrelid = 'public.analyses'::regclass
      and c.contype = 'c'
      and pg_catalog.pg_get_constraintdef(c.oid) ilike '%processing_stage%'
  ) into v_stage_constraint_ok;

  return jsonb_build_object(
    'database_ready',
      cardinality(v_missing_columns) = 0
      and cardinality(v_missing_rpcs) = 0
      and cardinality(v_missing_execute) = 0
      and cardinality(v_missing_buckets) = 0
      and cardinality(v_public_buckets) = 0
      and v_completed_status
      and v_stage_constraint_ok,
    'ergonomics_schema_ready', not (v_missing_columns && array[
      'ergonomics_metrics_path', 'ergonomics_metrics_version',
      'ergonomics_processed_frames', 'ergonomics_valid_metric_ratio',
      'ergonomics_metrics_summary', 'ergonomics_completed_at'
    ]::text[]),
    'risk_schema_ready', not (v_missing_columns && array[
      'risk_assessment_path', 'risk_assessment_version', 'risk_profile_id',
      'risk_processed_frames', 'risk_valid_metric_ratio', 'risk_overall_level',
      'risk_assessment_summary', 'risk_completed_at'
    ]::text[]),
    'report_schema_ready', not (v_missing_columns && array[
      'report_path', 'report_version', 'report_summary', 'report_completed_at'
    ]::text[]),
    'rpc_permissions_ready', cardinality(v_missing_rpcs) = 0
      and cardinality(v_missing_execute) = 0,
    'storage_ready', cardinality(v_missing_buckets) = 0
      and cardinality(v_public_buckets) = 0,
    'status_ready', v_completed_status and v_stage_constraint_ok,
    'missing_columns', to_jsonb(v_missing_columns),
    'missing_rpcs', to_jsonb(v_missing_rpcs),
    'missing_execute', to_jsonb(v_missing_execute),
    'missing_buckets', to_jsonb(v_missing_buckets),
    'public_buckets', to_jsonb(v_public_buckets)
  );
end;
$$;

revoke all on function public.check_pipeline_readiness_v021()
from public, anon, authenticated;
grant execute on function public.check_pipeline_readiness_v021()
to service_role;

notify pgrst, 'reload schema';
