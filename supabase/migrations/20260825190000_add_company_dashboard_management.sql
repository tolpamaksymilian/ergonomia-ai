-- Ergonomia AI 0.27.0-beta.1
-- Minimal company, position and invitation model for the dashboard redesign.

do $$ begin
  create type public.company_member_role as enum ('admin', 'member', 'reviewer');
exception when duplicate_object then null; end $$;

do $$ begin
  create type public.account_status as enum ('active', 'inactive', 'pending');
exception when duplicate_object then null; end $$;

do $$ begin
  create type public.invitation_status as enum ('pending', 'accepted', 'expired', 'cancelled');
exception when duplicate_object then null; end $$;

create table public.companies (
  id uuid primary key default gen_random_uuid(),
  name varchar(160) not null,
  legal_name varchar(200),
  tax_id varchar(32),
  city varchar(120),
  address text,
  status varchar(24) not null default 'active',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint companies_name_not_blank check (length(btrim(name)) >= 2),
  constraint companies_status_valid check (status in ('active', 'inactive'))
);

create table public.company_positions (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null references public.companies(id) on delete cascade,
  name varchar(120) not null,
  description text,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint company_positions_name_not_blank check (length(btrim(name)) >= 2),
  constraint company_positions_unique_name unique (company_id, name)
);

alter table public.profiles
  add column email varchar(320),
  add column company_id uuid references public.companies(id) on delete set null,
  add column company_role public.company_member_role,
  add column position_id uuid references public.company_positions(id) on delete set null,
  add column job_title varchar(120),
  add column account_status public.account_status not null default 'active',
  add column last_seen_at timestamptz;

update public.profiles p
set email = lower(u.email)
from auth.users u
where u.id = p.id and u.email is not null;

create unique index profiles_email_uidx on public.profiles (lower(email)) where email is not null;

create table public.company_invitations (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null references public.companies(id) on delete cascade,
  email varchar(320) not null,
  full_name varchar(160),
  company_role public.company_member_role not null default 'member',
  position_id uuid references public.company_positions(id) on delete set null,
  status public.invitation_status not null default 'pending',
  invited_by uuid not null references auth.users(id) on delete restrict,
  expires_at timestamptz not null default (now() + interval '7 days'),
  accepted_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint company_invitations_email_valid check (email = lower(btrim(email)) and position('@' in email) > 1),
  constraint company_invitations_expiry_valid check (expires_at > created_at)
);

create unique index company_invitations_pending_email_uidx
on public.company_invitations (lower(email)) where status = 'pending';
create index profiles_company_status_idx on public.profiles (company_id, account_status, created_at desc);
create index company_positions_company_active_idx on public.company_positions (company_id, is_active, name);
create index company_invitations_company_status_idx on public.company_invitations (company_id, status, created_at desc);

create trigger set_companies_updated_at before update on public.companies
for each row execute procedure public.set_analysis_updated_at();
create trigger set_company_positions_updated_at before update on public.company_positions
for each row execute procedure public.set_analysis_updated_at();
create trigger set_company_invitations_updated_at before update on public.company_invitations
for each row execute procedure public.set_analysis_updated_at();

create or replace function public.can_manage_company(p_company_id uuid)
returns boolean language sql stable security definer set search_path = '' as $$
  select public.is_admin() or exists (
    select 1 from public.profiles p
    where p.id = auth.uid() and p.company_id = p_company_id
      and p.company_role = 'admin'::public.company_member_role
      and p.account_status = 'active'::public.account_status
  );
$$;

revoke all on function public.can_manage_company(uuid) from public, anon;
grant execute on function public.can_manage_company(uuid) to authenticated;

create or replace function public.current_company_id()
returns uuid language sql stable security definer set search_path = '' as $$
  select p.company_id from public.profiles p where p.id = auth.uid();
$$;

revoke all on function public.current_company_id() from public, anon;
grant execute on function public.current_company_id() to authenticated;

alter table public.companies enable row level security;
alter table public.company_positions enable row level security;
alter table public.company_invitations enable row level security;

revoke all on table public.companies, public.company_positions, public.company_invitations from anon, authenticated;
grant select, insert, update on table public.companies to authenticated;
grant select, insert, update on table public.company_positions to authenticated;
grant select, insert, update, delete on table public.company_invitations to authenticated;
grant select (email, company_id, company_role, position_id, job_title, account_status, last_seen_at) on table public.profiles to authenticated;

create policy "Members can read company" on public.companies for select to authenticated
using (public.is_admin() or id = (select p.company_id from public.profiles p where p.id = auth.uid()));
create policy "Admins can create companies" on public.companies for insert to authenticated
with check (public.is_admin());
create policy "Managers can update company" on public.companies for update to authenticated
using (public.can_manage_company(id)) with check (public.can_manage_company(id));

create policy "Members can read company positions" on public.company_positions for select to authenticated
using (public.is_admin() or company_id = (select p.company_id from public.profiles p where p.id = auth.uid()));
create policy "Managers can create positions" on public.company_positions for insert to authenticated
with check (public.can_manage_company(company_id));
create policy "Managers can update positions" on public.company_positions for update to authenticated
using (public.can_manage_company(company_id)) with check (public.can_manage_company(company_id));

create policy "Managers can read invitations" on public.company_invitations for select to authenticated
using (public.can_manage_company(company_id));
create policy "Managers can create invitations" on public.company_invitations for insert to authenticated
with check (public.can_manage_company(company_id) and invited_by = auth.uid());
create policy "Managers can update invitations" on public.company_invitations for update to authenticated
using (public.can_manage_company(company_id)) with check (public.can_manage_company(company_id));
create policy "Managers can remove invitations" on public.company_invitations for delete to authenticated
using (public.can_manage_company(company_id));

create policy "Company members can read colleagues" on public.profiles for select to authenticated
using (
  company_id is not null and company_id = public.current_company_id()
);

create or replace function public.manage_company_member(
  p_user_id uuid,
  p_company_id uuid,
  p_company_role public.company_member_role,
  p_position_id uuid default null,
  p_account_status public.account_status default 'active'
)
returns boolean language plpgsql security definer set search_path = '' as $$
begin
  if not public.can_manage_company(p_company_id) then
    raise exception 'company_access_denied' using errcode = '42501';
  end if;
  if p_position_id is not null and not exists (
    select 1 from public.company_positions cp where cp.id = p_position_id and cp.company_id = p_company_id
  ) then
    raise exception 'position_company_mismatch' using errcode = '23503';
  end if;
  update public.profiles set company_id = p_company_id, company_role = p_company_role,
    position_id = p_position_id, account_status = p_account_status, updated_at = now()
  where id = p_user_id and (company_id = p_company_id or public.is_admin());
  return found;
end;
$$;

revoke all on function public.manage_company_member(uuid, uuid, public.company_member_role, uuid, public.account_status) from public, anon;
grant execute on function public.manage_company_member(uuid, uuid, public.company_member_role, uuid, public.account_status) to authenticated;

create or replace function public.accept_my_company_invitation()
returns boolean language plpgsql security definer set search_path = '' as $$
declare v_email text;
begin
  select lower(email) into v_email from auth.users where id = auth.uid();
  update public.company_invitations set status = 'accepted', accepted_at = now(), updated_at = now()
  where lower(email) = v_email and status = 'pending' and expires_at > now();
  if found then
    update public.profiles set account_status = 'active', last_seen_at = now(), updated_at = now() where id = auth.uid();
    return true;
  end if;
  update public.profiles set last_seen_at = now(), updated_at = now() where id = auth.uid();
  return false;
end;
$$;

revoke all on function public.accept_my_company_invitation() from public, anon;
grant execute on function public.accept_my_company_invitation() to authenticated;

create or replace function public.handle_new_user()
returns trigger language plpgsql security definer set search_path = '' as $$
declare v_invitation public.company_invitations%rowtype;
begin
  select * into v_invitation from public.company_invitations
  where lower(email) = lower(new.email) and status = 'pending' and expires_at > now()
  order by created_at desc limit 1;
  insert into public.profiles (id, full_name, email, role, company_id, company_role, position_id, account_status)
  values (
    new.id,
    coalesce(nullif(new.raw_user_meta_data ->> 'full_name', ''), v_invitation.full_name, ''),
    lower(new.email),
    'user'::public.app_role,
    v_invitation.company_id,
    v_invitation.company_role,
    v_invitation.position_id,
    case when v_invitation.id is null then 'active'::public.account_status else 'pending'::public.account_status end
  );
  return new;
end;
$$;

notify pgrst, 'reload schema';
