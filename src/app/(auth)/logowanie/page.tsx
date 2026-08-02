import { AuthPage } from "@/components/auth/auth-page";

type LoginPageProps = {
  searchParams: Promise<{
    error?: string;
  }>;
};

export default async function LoginPage({
  searchParams,
}: LoginPageProps) {
  const params = await searchParams;

  const notice =
    params.error === "confirmation_failed"
      ? "Nie udało się potwierdzić konta. Link mógł wygasnąć albo został już wcześniej wykorzystany."
      : params.error === "missing_code"
        ? "Link potwierdzający nie zawiera wymaganego kodu autoryzacyjnego."
        : undefined;

  return (
    <AuthPage
      mode="login"
      notice={notice}
    />
  );
}