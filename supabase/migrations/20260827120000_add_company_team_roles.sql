-- Ergonomia AI 0.28.0-beta.1
-- Informational team roles. Authorization remains based only on app/system roles.

alter table public.profiles
  add column if not exists team_role varchar(120),
  add constraint profiles_team_role_not_blank
    check (team_role is null or length(btrim(team_role)) between 2 and 120);

alter table public.company_invitations
  add column if not exists team_role varchar(120),
  add constraint company_invitations_team_role_not_blank
    check (team_role is null or length(btrim(team_role)) between 2 and 120);

grant select (team_role) on table public.profiles to authenticated;

create or replace function public.manage_company_member_v2(
  p_user_id uuid,
  p_company_id uuid,
  p_company_role public.company_member_role,
  p_position_id uuid default null,
  p_account_status public.account_status default 'active',
  p_team_role text default null
)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
begin
  if not public.can_manage_company(p_company_id) then
    raise exception 'company_access_denied' using errcode = '42501';
  end if;

  if p_position_id is not null and not exists (
    select 1
    from public.company_positions cp
    where cp.id = p_position_id and cp.company_id = p_company_id
  ) then
    raise exception 'position_company_mismatch' using errcode = '23503';
  end if;

  if p_team_role is not null and length(btrim(p_team_role)) not between 2 and 120 then
    raise exception 'invalid_team_role' using errcode = '22023';
  end if;

  update public.profiles
  set company_id = p_company_id,
      company_role = p_company_role,
      position_id = p_position_id,
      account_status = p_account_status,
      team_role = nullif(btrim(p_team_role), ''),
      updated_at = now()
  where id = p_user_id
    and (company_id = p_company_id or public.is_admin());

  return found;
end;
$$;

revoke all on function public.manage_company_member_v2(uuid, uuid, public.company_member_role, uuid, public.account_status, text) from public, anon;
grant execute on function public.manage_company_member_v2(uuid, uuid, public.company_member_role, uuid, public.account_status, text) to authenticated;

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_invitation public.company_invitations%rowtype;
begin
  select * into v_invitation
  from public.company_invitations
  where lower(email) = lower(new.email)
    and status = 'pending'
    and expires_at > now()
  order by created_at desc
  limit 1;

  insert into public.profiles (
    id, full_name, email, role, company_id, company_role, position_id, team_role, account_status
  ) values (
    new.id,
    coalesce(nullif(new.raw_user_meta_data ->> 'full_name', ''), v_invitation.full_name, ''),
    lower(new.email),
    'user'::public.app_role,
    v_invitation.company_id,
    v_invitation.company_role,
    v_invitation.position_id,
    v_invitation.team_role,
    case
      when v_invitation.id is null then 'active'::public.account_status
      else 'pending'::public.account_status
    end
  );
  return new;
end;
$$;

notify pgrst, 'reload schema';
