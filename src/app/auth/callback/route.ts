import { NextResponse, type NextRequest } from "next/server";

import { createClient } from "@/lib/supabase/server";

function getSafeRedirectPath(value: string | null) {
  if (!value) {
    return "/panel";
  }

  if (!value.startsWith("/") || value.startsWith("//")) {
    return "/panel";
  }

  return value;
}

export async function GET(request: NextRequest) {
  const code = request.nextUrl.searchParams.get("code");

  const next = getSafeRedirectPath(
    request.nextUrl.searchParams.get("next"),
  );

  if (!code) {
    const loginUrl = request.nextUrl.clone();

    loginUrl.pathname = "/logowanie";
    loginUrl.search = "";
    loginUrl.searchParams.set("error", "missing_code");

    return NextResponse.redirect(loginUrl);
  }

  const supabase = await createClient();

  const { error } =
    await supabase.auth.exchangeCodeForSession(code);

  if (error) {
    const loginUrl = request.nextUrl.clone();

    loginUrl.pathname = "/logowanie";
    loginUrl.search = "";
    loginUrl.searchParams.set(
      "error",
      "confirmation_failed",
    );

    return NextResponse.redirect(loginUrl);
  }

  await supabase.rpc("accept_my_company_invitation");

  const destinationUrl = request.nextUrl.clone();

  destinationUrl.pathname = next;
  destinationUrl.search = "";

  return NextResponse.redirect(destinationUrl);
}
