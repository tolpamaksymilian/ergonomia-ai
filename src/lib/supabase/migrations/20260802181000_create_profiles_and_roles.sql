-- ============================================================
-- ERGONOMIA AI
-- Profile użytkowników i role aplikacyjne
-- ============================================================

-- Dostępne role w aplikacji.
do $$
begin
  create type public.app_role as enum (
    'user',
    'admin'
  );
exception
  when duplicate_object then null;
end
$$;

-- ============================================================
-- TABELA PROFILI
-- ============================================================

create table if not exists public.profiles (
  id uuid primary key
    references auth.users(id)
    on delete cascade,

  full_name text not null default '',
  avatar_url text,

  role public.app_role
    not null
    default 'user',

  created_at timestamptz
    not null
    default now(),

  updated_at timestamptz
    not null
    default now()
);

alter table public.profiles
enable row level security;

-- ============================================================
-- UPRAWNIENIA
-- ============================================================

-- Niezalogowany użytkownik nie może odczytywać profili.
revoke all
on table public.profiles
from anon;

-- Zalogowany użytkownik może odczytać profil,
-- ale zakres rekordów kontrolują polityki RLS.
grant select
on table public.profiles
to authenticated;

-- Nie przyznajemy pełnego UPDATE.
-- Użytkownik nie może sam zmienić swojej roli.
revoke insert, update, delete
on table public.profiles
from authenticated;

grant update (
  full_name,
  avatar_url
)
on table public.profiles
to authenticated;

-- ============================================================
-- POLITYKI RLS
-- ============================================================

drop policy if exists
  "Users can read own profile"
on public.profiles;

create policy
  "Users can read own profile"
on public.profiles
for select
to authenticated
using (
  (select auth.uid()) = id
);

drop policy if exists
  "Users can update own profile"
on public.profiles;

create policy
  "Users can update own profile"
on public.profiles
for update
to authenticated
using (
  (select auth.uid()) = id
)
with check (
  (select auth.uid()) = id
);

-- ============================================================
-- AUTOMATYCZNE TWORZENIE PROFILU
-- ============================================================

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.profiles (
    id,
    full_name,
    role
  )
  values (
    new.id,
    coalesce(
      new.raw_user_meta_data ->> 'full_name',
      ''
    ),
    'user'
  );

  return new;
end;
$$;

drop trigger if exists
  on_auth_user_created
on auth.users;

create trigger on_auth_user_created
after insert on auth.users
for each row
execute procedure public.handle_new_user();

-- ============================================================
-- AUTOMATYCZNE UPDATED_AT
-- ============================================================

create or replace function public.set_profile_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists
  set_profiles_updated_at
on public.profiles;

create trigger set_profiles_updated_at
before update on public.profiles
for each row
execute procedure public.set_profile_updated_at();