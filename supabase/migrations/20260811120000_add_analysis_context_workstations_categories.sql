-- Ergonomia AI v0.10.0-beta.1
-- Analysis Context, workstations and grouped analysis categories.

create table public.workstations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  name varchar(120) not null,
  code varchar(80),
  description text,
  department varchar(120),
  area varchar(120),
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint workstations_name_not_blank check (length(btrim(name)) >= 2),
  constraint workstations_code_not_blank check (code is null or length(btrim(code)) > 0),
  constraint workstations_user_identity_unique unique (id, user_id)
);

create unique index workstations_owner_normalized_identity_uidx
on public.workstations (
  user_id,
  lower(btrim(name)),
  lower(coalesce(btrim(code), ''))
);

create index workstations_owner_active_name_idx
on public.workstations (user_id, is_active, name);

create table public.analysis_categories (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  name varchar(80) not null,
  group_name varchar(80) not null,
  description text,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint analysis_categories_name_not_blank check (length(btrim(name)) >= 2),
  constraint analysis_categories_group_not_blank check (length(btrim(group_name)) >= 2),
  constraint analysis_categories_user_identity_unique unique (id, user_id)
);

create unique index analysis_categories_owner_normalized_name_uidx
on public.analysis_categories (
  user_id,
  lower(btrim(group_name)),
  lower(btrim(name))
);

create index analysis_categories_owner_group_active_idx
on public.analysis_categories (user_id, group_name, is_active, name);

alter table public.analyses
  add column workstation_id uuid,
  add column analysis_context jsonb not null default '{"schema_version":"1.0"}'::jsonb,
  add column analysis_date date,
  add constraint analyses_context_is_object
    check (jsonb_typeof(analysis_context) = 'object'),
  add constraint analyses_user_identity_unique unique (id, user_id),
  add constraint analyses_workstation_owner_fk
    foreign key (workstation_id, user_id)
    references public.workstations (id, user_id)
    on delete restrict;

create index analyses_owner_workstation_created_idx
on public.analyses (user_id, workstation_id, created_at desc);

create index analyses_owner_status_created_idx
on public.analyses (user_id, status, created_at desc);

create index analyses_owner_analysis_date_idx
on public.analyses (user_id, analysis_date desc)
where analysis_date is not null;

create index analyses_context_process_search_idx
on public.analyses (user_id, lower(analysis_context ->> 'process_name'))
where analysis_context ? 'process_name';

create table public.analysis_category_links (
  analysis_id uuid not null,
  category_id uuid not null,
  user_id uuid not null,
  created_at timestamptz not null default now(),
  primary key (analysis_id, category_id),
  constraint analysis_category_links_analysis_owner_fk
    foreign key (analysis_id, user_id)
    references public.analyses (id, user_id)
    on delete cascade,
  constraint analysis_category_links_category_owner_fk
    foreign key (category_id, user_id)
    references public.analysis_categories (id, user_id)
    on delete cascade
);

create index analysis_category_links_owner_category_analysis_idx
on public.analysis_category_links (user_id, category_id, analysis_id);

create index analysis_category_links_owner_analysis_idx
on public.analysis_category_links (user_id, analysis_id);

create trigger set_workstations_updated_at
before update on public.workstations
for each row execute procedure public.set_analysis_updated_at();

create trigger set_analysis_categories_updated_at
before update on public.analysis_categories
for each row execute procedure public.set_analysis_updated_at();

alter table public.workstations enable row level security;
alter table public.analysis_categories enable row level security;
alter table public.analysis_category_links enable row level security;

revoke all on table public.workstations from anon, authenticated;
revoke all on table public.analysis_categories from anon, authenticated;
revoke all on table public.analysis_category_links from anon, authenticated;

grant select, insert, update on table public.workstations to authenticated;
grant select, insert, update on table public.analysis_categories to authenticated;
grant select, insert, delete on table public.analysis_category_links to authenticated;
grant update (title, description, workstation_id, analysis_context, analysis_date)
on table public.analyses to authenticated;

create policy "Users can read own workstations"
on public.workstations for select to authenticated
using (user_id = (select auth.uid()) or (select public.is_admin()));

create policy "Users can create own workstations"
on public.workstations for insert to authenticated
with check (user_id = (select auth.uid()));

create policy "Users can update own workstations"
on public.workstations for update to authenticated
using (user_id = (select auth.uid()) or (select public.is_admin()))
with check (user_id = (select auth.uid()) or (select public.is_admin()));

create policy "Users can read own analysis categories"
on public.analysis_categories for select to authenticated
using (user_id = (select auth.uid()) or (select public.is_admin()));

create policy "Users can create own analysis categories"
on public.analysis_categories for insert to authenticated
with check (user_id = (select auth.uid()));

create policy "Users can update own analysis categories"
on public.analysis_categories for update to authenticated
using (user_id = (select auth.uid()) or (select public.is_admin()))
with check (user_id = (select auth.uid()) or (select public.is_admin()));

create policy "Users can read own analysis category links"
on public.analysis_category_links for select to authenticated
using (user_id = (select auth.uid()) or (select public.is_admin()));

create policy "Users can create own analysis category links"
on public.analysis_category_links for insert to authenticated
with check (user_id = (select auth.uid()));

create policy "Users can remove own analysis category links"
on public.analysis_category_links for delete to authenticated
using (user_id = (select auth.uid()) or (select public.is_admin()));

create policy "Users can update own analysis metadata"
on public.analyses for update to authenticated
using (user_id = (select auth.uid()) or (select public.is_admin()))
with check (user_id = (select auth.uid()) or (select public.is_admin()));

create or replace function public.set_analysis_categories(
  p_analysis_id uuid,
  p_category_ids uuid[] default '{}'::uuid[]
)
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_owner_id uuid;
begin
  select a.user_id into v_owner_id
  from public.analyses as a
  where a.id = p_analysis_id;

  if v_owner_id is null
     or (v_owner_id <> auth.uid() and not public.is_admin()) then
    raise exception 'analysis_not_available' using errcode = '42501';
  end if;

  if exists (
    select 1 from unnest(coalesce(p_category_ids, '{}'::uuid[])) as requested(category_id)
    left join public.analysis_categories as category
      on category.id = requested.category_id
     and category.user_id = v_owner_id
    where category.id is null
  ) then
    raise exception 'invalid_category_owner' using errcode = '23503';
  end if;

  delete from public.analysis_category_links
  where analysis_id = p_analysis_id;

  insert into public.analysis_category_links (analysis_id, category_id, user_id)
  select p_analysis_id, category_id, v_owner_id
  from (select distinct unnest(coalesce(p_category_ids, '{}'::uuid[])) as category_id) as selected;
end;
$$;

revoke all on function public.set_analysis_categories(uuid, uuid[]) from public, anon;
grant execute on function public.set_analysis_categories(uuid, uuid[]) to authenticated;

notify pgrst, 'reload schema';
