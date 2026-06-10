-- Drip live backend — per-user ad-platform connections + an append-only audit
-- trail for every real/shadow write. Row-Level Security locks each row to its
-- owner, so even with the anon key a user only ever sees their own data.
--
-- Apply:  supabase db push      (or paste into the SQL editor)

-- ── platform connections (OAuth tokens live here, never in the browser) ──────
create table if not exists public.ad_connections (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid not null references auth.users(id) on delete cascade,
  platform     text not null check (platform in ('meta','tiktok','tencent','oceanengine','kuaishou')),
  account_id   text not null default '',
  access_token text not null,
  refresh_token text default '',
  expires_at   timestamptz,
  scopes       text default '',
  meta         jsonb not null default '{}'::jsonb,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now(),
  unique (user_id, platform)
);

alter table public.ad_connections enable row level security;

-- Owners can read/manage their own connection rows. The access_token column is
-- only ever read by the Edge Functions (service role bypasses RLS); the browser
-- uses these policies and should select non-secret columns.
create policy ad_connections_select on public.ad_connections
  for select using (auth.uid() = user_id);
create policy ad_connections_insert on public.ad_connections
  for insert with check (auth.uid() = user_id);
create policy ad_connections_update on public.ad_connections
  for update using (auth.uid() = user_id);
create policy ad_connections_delete on public.ad_connections
  for delete using (auth.uid() = user_id);

-- ── OAuth state nonces (CSRF + maps the provider callback back to a user) ────
create table if not exists public.oauth_states (
  state      text primary key,
  user_id    uuid not null references auth.users(id) on delete cascade,
  platform   text not null,
  created_at timestamptz not null default now()
);
alter table public.oauth_states enable row level security;
-- no browser policies: only the service role (Edge Functions) touches this table.

-- ── append-only audit trail (mirrors src/drip/safety.py audit()) ─────────────
create table if not exists public.drip_audit (
  id          bigint generated always as identity primary key,
  user_id     uuid not null references auth.users(id) on delete cascade,
  ts          timestamptz not null default now(),
  platform    text not null,
  target_id   text not null,
  label       text default '',
  action      text not null,
  field       text default '',
  old_value   text,
  new_value   text,
  status      text not null,          -- applied | shadow | skipped | denied | failed
  mode        text not null,          -- shadow | copilot | autonomous
  detail      text default ''
);
alter table public.drip_audit enable row level security;
create policy drip_audit_select on public.drip_audit
  for select using (auth.uid() = user_id);
-- inserts come from the Edge Functions (service role); no browser insert policy.

create index if not exists drip_audit_user_ts on public.drip_audit (user_id, ts desc);
