-- ============================================================
-- ERGONOMIA AI
-- Kontrolowane usuwanie analiz i filmów źródłowych
-- ============================================================

-- ------------------------------------------------------------
-- DELETE DLA TABELI ANALYSES
-- ------------------------------------------------------------

grant delete
on table public.analyses
to authenticated;

drop policy if exists
  "Users can delete own inactive analyses"
on public.analyses;

create policy
  "Users can delete own inactive analyses"
on public.analyses
for delete
to authenticated
using (
  (
    user_id = (select auth.uid())
    or (select public.is_admin())
  )
  and status in (
    'draft'::public.analysis_status,
    'queued'::public.analysis_status,
    'completed'::public.analysis_status,
    'failed'::public.analysis_status,
    'cancelled'::public.analysis_status
  )
);

-- ------------------------------------------------------------
-- DELETE DLA STORAGE
-- ------------------------------------------------------------

drop policy if exists
  "Users can delete own analysis videos"
on storage.objects;

create policy
  "Users can delete own analysis videos"
on storage.objects
for delete
to authenticated
using (
  bucket_id = 'analysis-videos'
  and (
    (storage.foldername(name))[1]
      = (select auth.uid())::text

    or

    (select public.is_admin())
  )
);