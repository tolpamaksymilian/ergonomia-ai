-- ============================================================
-- ERGONOMIA AI
-- Spójny postęp całego pipeline analizy
-- ============================================================

create or replace function public.normalize_analysis_pipeline_progress()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if new.status = 'completed'::public.analysis_status then
    new.progress := 100;

  elsif
    new.status = 'queued'::public.analysis_status
    and new.processing_stage = 'ready-for-ergonomics'
  then
    new.progress := greatest(
      coalesce(new.progress, 0),
      75
    );

  elsif
    new.status = 'queued'::public.analysis_status
    and new.processing_stage = 'ready-for-ai'
  then
    new.progress := greatest(
      coalesce(new.progress, 0),
      20
    );
  end if;

  return new;
end;
$$;

drop trigger if exists
  analyses_normalize_pipeline_progress
on public.analyses;

create trigger analyses_normalize_pipeline_progress
before insert or update of
  status,
  processing_stage,
  progress
on public.analyses
for each row
execute function public.normalize_analysis_pipeline_progress();

-- Uzupełnienie już istniejących analiz.
update public.analyses
set progress = case
  when status = 'completed'::public.analysis_status
    then 100

  when
    status = 'queued'::public.analysis_status
    and processing_stage = 'ready-for-ergonomics'
    then 75

  when
    status = 'queued'::public.analysis_status
    and processing_stage = 'ready-for-ai'
    then 20

  else progress
end
where
  status = 'completed'::public.analysis_status
  or processing_stage in (
    'ready-for-ai',
    'ready-for-ergonomics'
  );