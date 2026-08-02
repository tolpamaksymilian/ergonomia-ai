"use server";

import { revalidatePath } from "next/cache";
import { headers } from "next/headers";
import { redirect } from "next/navigation";

import { createClient } from "@/lib/supabase/server";
import type { AuthActionState } from "@/types/auth";

function getTextValue(formData: FormData, fieldName: string) {
  const value = formData.get(fieldName);

  return typeof value === "string" ? value.trim() : "";
}

function isValidEmail(email: string) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

async function getRequestOrigin() {
  const requestHeaders = await headers();

  const origin = requestHeaders.get("origin");

  if (origin) {
    return origin.replace(/\/$/, "");
  }

  const forwardedHost = requestHeaders.get("x-forwarded-host");
  const host = forwardedHost ?? requestHeaders.get("host");

  const forwardedProtocol =
    requestHeaders.get("x-forwarded-proto") ?? "http";

  if (host) {
    return `${forwardedProtocol}://${host}`;
  }

  return (
    process.env.NEXT_PUBLIC_SITE_URL?.replace(/\/$/, "") ??
    "http://localhost:3000"
  );
}

export async function signInAction(
  _previousState: AuthActionState,
  formData: FormData,
): Promise<AuthActionState> {
  const email = getTextValue(formData, "email").toLowerCase();
  const password = getTextValue(formData, "password");

  const fieldErrors: AuthActionState["fieldErrors"] = {};

  if (!email) {
    fieldErrors.email = "Podaj adres e-mail.";
  } else if (!isValidEmail(email)) {
    fieldErrors.email = "Podaj poprawny adres e-mail.";
  }

  if (!password) {
    fieldErrors.password = "Podaj hasło.";
  }

  if (Object.keys(fieldErrors).length > 0) {
    return {
      status: "error",
      message: "Popraw zaznaczone pola.",
      fieldErrors,
    };
  }

  const supabase = await createClient();

  const { error } = await supabase.auth.signInWithPassword({
    email,
    password,
  });

  if (error) {
    return {
      status: "error",
      message:
        "Nie udało się zalogować. Sprawdź adres e-mail, hasło oraz potwierdzenie konta.",
    };
  }

  revalidatePath("/", "layout");
  redirect("/panel");
}

export async function signUpAction(
  _previousState: AuthActionState,
  formData: FormData,
): Promise<AuthActionState> {
  const fullName = getTextValue(formData, "fullName");
  const email = getTextValue(formData, "email").toLowerCase();
  const password = getTextValue(formData, "password");
  const confirmPassword = getTextValue(
    formData,
    "confirmPassword",
  );

  const fieldErrors: AuthActionState["fieldErrors"] = {};

  if (fullName.length < 2) {
    fieldErrors.fullName =
      "Imię i nazwisko musi zawierać co najmniej 2 znaki.";
  }

  if (!email) {
    fieldErrors.email = "Podaj adres e-mail.";
  } else if (!isValidEmail(email)) {
    fieldErrors.email = "Podaj poprawny adres e-mail.";
  }

  if (password.length < 8) {
    fieldErrors.password =
      "Hasło musi zawierać co najmniej 8 znaków.";
  }

  if (password !== confirmPassword) {
    fieldErrors.confirmPassword = "Hasła nie są identyczne.";
  }

  if (Object.keys(fieldErrors).length > 0) {
    return {
      status: "error",
      message: "Popraw zaznaczone pola.",
      fieldErrors,
    };
  }

  const origin = await getRequestOrigin();
  const supabase = await createClient();

  const { data, error } = await supabase.auth.signUp({
    email,
    password,
    options: {
      emailRedirectTo: `${origin}/auth/callback?next=/panel`,
      data: {
        full_name: fullName,
      },
    },
  });

  if (error) {
    return {
      status: "error",
      message:
        "Nie udało się utworzyć konta. Sprawdź dane i spróbuj ponownie.",
    };
  }

  /*
   * Jeżeli potwierdzanie adresu e-mail jest wyłączone,
   * Supabase może od razu zwrócić aktywną sesję.
   */
  if (data.session) {
    revalidatePath("/", "layout");
    redirect("/panel");
  }

  return {
    status: "success",
    message:
      "Konto zostało utworzone. Sprawdź skrzynkę pocztową i potwierdź adres e-mail.",
  };
}

export async function signOutAction() {
  const supabase = await createClient();

  await supabase.auth.signOut();

  revalidatePath("/", "layout");
  redirect("/");
}