-- ============================================================
-- ERGONOMIA AI
-- Sprawdzanie roli administratora i dostęp administracyjny
-- ============================================================

create or replace function public.is_admin()
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1
    from public.profiles
    where id = (select auth.uid())
      and role = 'admin'::public.app_role
  );
$$;

revoke all
on function public.is_admin()
from public;

grant execute
on function public.is_admin()
to authenticated;

-- Administrator może przeglądać profile użytkowników.
-- Zwykły użytkownik nadal widzi tylko swój profil
-- dzięki istniejącej polityce RLS.

drop policy if exists
  "Admins can read all profiles"
on public.profiles;

create policy
  "Admins can read all profiles"
on public.profiles
for select
to authenticated
using (
  (select public.is_admin())
);