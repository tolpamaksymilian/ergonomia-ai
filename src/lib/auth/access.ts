import { redirect } from "next/navigation";

import { createClient } from "@/lib/supabase/server";

export type AppRole = "user" | "admin";

export async function getCurrentAccount() {
  const supabase = await createClient();

  const {
    data: { user },
    error: userError,
  } = await supabase.auth.getUser();

  if (userError || !user) {
    return null;
  }

  const { data: profile, error: profileError } = await supabase
    .from("profiles")
    .select("id, full_name, role, created_at, updated_at")
    .eq("id", user.id)
    .maybeSingle();

  if (profileError) {
    throw new Error(
      `Nie udało się pobrać profilu użytkownika: ${profileError.message}`,
    );
  }

  return {
    supabase,
    user,
    profile,
  };
}

export async function requireUser() {
  const account = await getCurrentAccount();

  if (!account) {
    redirect("/logowanie");
  }

  return account;
}

export async function requireAdmin() {
  const account = await requireUser();

  if (account.profile?.role !== "admin") {
    redirect("/panel");
  }

  return account;
}