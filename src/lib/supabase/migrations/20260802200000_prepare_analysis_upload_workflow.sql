-- ============================================================
-- ERGONOMIA AI
-- Bezpieczny workflow uploadu filmu
-- ============================================================

-- Nowa analiza zaczyna się od etapu przesyłania.
alter table public.analyses
  alter column status
  set default 'uploading'::public.analysis_status;

-- queued_at ustawiamy dopiero po ukończeniu uploadu.
alter table public.analyses
  alter column queued_at drop not null;

alter table public.analyses
  alter column queued_at drop default;

-- ============================================================
-- NOWA POLITYKA INSERT
-- ============================================================

drop policy if exists
  "Users can create own queued analyses"
on public.analyses;

drop policy if exists
  "Users can create own uploading analyses"
on public.analyses;

create policy
  "Users can create own uploading analyses"
on public.analyses
for insert
to authenticated
with check (
  (select auth.uid()) is not null
  and user_id = (select auth.uid())
  and status = 'uploading'::public.analysis_status
  and progress = 0
  and source_video_path like
    (select auth.uid())::text
    || '/'
    || id::text
    || '/source/%'
);

-- ============================================================
-- FINALIZACJA UPLOADU
-- ============================================================

create or replace function public.finalize_analysis_upload(
  p_analysis_id uuid
)
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_source_video_path text;
begin
  select source_video_path
  into v_source_video_path
  from public.analyses
  where id = p_analysis_id
    and user_id = (select auth.uid())
    and status = 'uploading'::public.analysis_status
  for update;

  if v_source_video_path is null then
    raise exception
      'Nie znaleziono analizy oczekującej na ukończenie uploadu.';
  end if;

  if not exists (
    select 1
    from storage.objects
    where bucket_id = 'analysis-videos'
      and name = v_source_video_path
  ) then
    raise exception
      'Plik filmu nie został odnaleziony w Storage.';
  end if;

  update public.analyses
  set
    status = 'queued'::public.analysis_status,
    progress = 0,
    queued_at = now(),
    error_code = null,
    error_message = null
  where id = p_analysis_id
    and user_id = (select auth.uid())
    and status = 'uploading'::public.analysis_status;

  if not found then
    raise exception
      'Nie udało się skierować analizy do kolejki.';
  end if;
end;
$$;

revoke all
on function public.finalize_analysis_upload(uuid)
from public;

grant execute
on function public.finalize_analysis_upload(uuid)
to authenticated;

-- ============================================================
-- OZNACZENIE NIEUDANEGO UPLOADU
-- ============================================================

create or replace function public.mark_analysis_upload_failed(
  p_analysis_id uuid,
  p_error_message text
)
returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
  update public.analyses
  set
    status = 'failed'::public.analysis_status,
    error_code = 'UPLOAD_FAILED',
    error_message = left(
      coalesce(
        p_error_message,
        'Nieznany błąd przesyłania filmu.'
      ),
      2000
    )
  where id = p_analysis_id
    and user_id = (select auth.uid())
    and status = 'uploading'::public.analysis_status;
end;
$$;

revoke all
on function public.mark_analysis_upload_failed(uuid, text)
from public;

grant execute
on function public.mark_analysis_upload_failed(uuid, text)
to authenticated;

-- ============================================================
-- ANULOWANIE UPLOADU
-- ============================================================

create or replace function public.cancel_analysis_upload(
  p_analysis_id uuid
)
returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
  update public.analyses
  set
    status = 'cancelled'::public.analysis_status,
    error_code = 'UPLOAD_CANCELLED',
    error_message = 'Przesyłanie filmu zostało anulowane przez użytkownika.'
  where id = p_analysis_id
    and user_id = (select auth.uid())
    and status = 'uploading'::public.analysis_status;
end;
$$;

revoke all
on function public.cancel_analysis_upload(uuid)
from public;

grant execute
on function public.cancel_analysis_upload(uuid)
to authenticated;