-- ============================================================
-- ERGONOMIA AI
-- Dostęp do prywatnych filmów analiz
-- ============================================================

-- Oczekiwana struktura ścieżki:
--
-- USER_ID/ANALYSIS_ID/source/nazwa-pliku.mp4
--
-- Przykład:
--
-- 8140.../fe21.../source/stanowisko-01.mp4

-- ------------------------------------------------------------
-- UPLOAD
-- ------------------------------------------------------------

drop policy if exists
  "Users can upload own analysis videos"
on storage.objects;

create policy
  "Users can upload own analysis videos"
on storage.objects
for insert
to authenticated
with check (
  bucket_id = 'analysis-videos'
  and (storage.foldername(name))[1]
    = (select auth.uid())::text
);

-- ------------------------------------------------------------
-- ODCZYT
-- ------------------------------------------------------------

drop policy if exists
  "Users can read own analysis videos"
on storage.objects;

create policy
  "Users can read own analysis videos"
on storage.objects
for select
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