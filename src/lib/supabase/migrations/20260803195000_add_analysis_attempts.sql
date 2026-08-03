-- ============================================================
-- ERGONOMIA AI
-- Licznik prób przetwarzania analizy
-- ============================================================

alter table public.analyses
  add column if not exists attempts integer not null default 0;

alter table public.analyses
  drop constraint if exists analyses_attempts_check;

alter table public.analyses
  add constraint analyses_attempts_check
  check (attempts >= 0);