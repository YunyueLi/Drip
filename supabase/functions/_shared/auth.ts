// Supabase access helpers for the Edge Functions.
//
// - admin(): service-role client. Bypasses RLS — used to read/write the
//   access_token in ad_connections, insert audit rows, and manage oauth_states.
//   NEVER expose the service role key to the browser.
// - userFromRequest(): verifies the caller's Supabase JWT (Authorization: Bearer
//   <token>) and returns the authenticated user, or null.
import { createClient, type SupabaseClient } from "https://esm.sh/@supabase/supabase-js@2.45.0";

const URL = Deno.env.get("SUPABASE_URL")!;
const SERVICE_ROLE = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;

export function admin(): SupabaseClient {
  return createClient(URL, SERVICE_ROLE, { auth: { persistSession: false, autoRefreshToken: false } });
}

export async function userFromRequest(req: Request): Promise<{ id: string; email: string } | null> {
  const authz = req.headers.get("Authorization") || "";
  const token = authz.replace(/^Bearer\s+/i, "").trim();
  if (!token) return null;
  const { data, error } = await admin().auth.getUser(token);
  if (error || !data?.user) return null;
  return { id: data.user.id, email: data.user.email || "" };
}
