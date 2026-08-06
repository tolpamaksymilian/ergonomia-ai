-- ============================================================
-- ERGONOMIA AI
-- Poprawna konfiguracja typów MIME dla filmów analiz
-- ============================================================

update storage.buckets
set
  public = false,
  file_size_limit = 52428800,
  allowed_mime_types = array[
    'video/mp4',
    'video/webm',
    'video/quicktime'
  ]::text[]
where id = 'analysis-videos';