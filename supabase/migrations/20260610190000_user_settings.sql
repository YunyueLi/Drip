-- Per-user roaming settings — the Drip account's single source of truth for
-- everything that should follow the user across devices (LLM provider configs,
-- targets, UI prefs). One jsonb blob per user, owner-only RLS.
--
-- The browser reads/writes this directly with the user's JWT (supabase-js);
-- newer updatedAt wins against the local cache (web/auth.js acctPull/acctSave).

create table if not exists public.user_settings (
  user_id    uuid primary key references auth.users(id) on delete cascade,
  data       jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

alter table public.user_settings enable row level security;

create policy user_settings_select on public.user_settings
  for select using (auth.uid() = user_id);
create policy user_settings_insert on public.user_settings
  for insert with check (auth.uid() = user_id);
create policy user_settings_update on public.user_settings
  for update using (auth.uid() = user_id);
create policy user_settings_delete on public.user_settings
  for delete using (auth.uid() = user_id);
