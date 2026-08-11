"use client";

import Link from "next/link";
import { useActionState, useState } from "react";
import {
  ArrowRight,
  Eye,
  EyeOff,
  LoaderCircle,
  LockKeyhole,
  Mail,
  UserRound,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import {
  signInAction,
  signUpAction,
} from "@/actions/auth";

import { initialAuthState } from "@/types/auth";

type AuthFormProps = {
  mode: "login" | "register";
};

export function AuthForm({ mode }: AuthFormProps) {
  const isRegister = mode === "register";

  const selectedAction = isRegister
    ? signUpAction
    : signInAction;

  const [state, formAction, isPending] = useActionState(
    selectedAction,
    initialAuthState,
  );

  const [showPassword, setShowPassword] = useState(false);

  return (
    <form action={formAction} className="mt-8 space-y-5">
      {isRegister && (
        <FormField
          id="fullName"
          name="fullName"
          label="Imię i nazwisko"
          placeholder="Jan Kowalski"
          autoComplete="name"
          icon={UserRound}
          error={state.fieldErrors?.fullName}
        />
      )}

      <FormField
        id="email"
        name="email"
        type="email"
        label="Adres e-mail"
        placeholder="nazwa@firma.pl"
        autoComplete="email"
        icon={Mail}
        error={state.fieldErrors?.email}
      />

      <PasswordField
        id="password"
        name="password"
        label="Hasło"
        placeholder={
          isRegister
            ? "Minimum 8 znaków"
            : "Wpisz swoje hasło"
        }
        autoComplete={
          isRegister
            ? "new-password"
            : "current-password"
        }
        visible={showPassword}
        onToggle={() =>
          setShowPassword((current) => !current)
        }
        error={state.fieldErrors?.password}
      />

      {isRegister && (
        <PasswordField
          id="confirmPassword"
          name="confirmPassword"
          label="Powtórz hasło"
          placeholder="Wpisz ponownie hasło"
          autoComplete="new-password"
          visible={showPassword}
          onToggle={() =>
            setShowPassword((current) => !current)
          }
          error={state.fieldErrors?.confirmPassword}
        />
      )}

      {state.message && (
        <div
          role="status"
          className={`rounded-2xl border px-4 py-3 text-sm leading-6 ${
            state.status === "success"
              ? "border-emerald-400/20 bg-emerald-400/[0.08] text-emerald-200"
              : "border-red-400/20 bg-red-400/[0.08] text-red-200"
          }`}
        >
          {state.message}
        </div>
      )}

      <button
        type="submit"
        disabled={isPending}
        className="ui-button-primary group w-full py-3.5"
      >
        {isPending ? (
          <>
            <LoaderCircle className="size-5 animate-spin" />

            {isRegister
              ? "Tworzenie konta..."
              : "Logowanie..."}
          </>
        ) : (
          <>
            {isRegister
              ? "Utwórz konto"
              : "Zaloguj się"}

            <ArrowRight className="size-5 transition group-hover:translate-x-1" />
          </>
        )}
      </button>

      <p className="text-center text-sm text-slate-400">
        {isRegister ? (
          <>
            Masz już konto?{" "}
            <Link
              href="/logowanie"
              className="font-semibold text-primary transition hover:text-primary-hover"
            >
              Zaloguj się
            </Link>
          </>
        ) : (
          <>
            Nie masz konta?{" "}
            <Link
              href="/rejestracja"
              className="font-semibold text-primary transition hover:text-primary-hover"
            >
              Utwórz konto
            </Link>
          </>
        )}
      </p>
    </form>
  );
}

type FormFieldProps = {
  id: string;
  name: string;
  label: string;
  placeholder: string;
  type?: string;
  autoComplete?: string;
  icon: LucideIcon;
  error?: string;
};

function FormField({
  id,
  name,
  label,
  placeholder,
  type = "text",
  autoComplete,
  icon: Icon,
  error,
}: FormFieldProps) {
  return (
    <div>
      <label
        htmlFor={id}
        className="mb-2 block text-sm font-medium text-foreground"
      >
        {label}
      </label>

      <div className="relative">
        <Icon className="pointer-events-none absolute left-4 top-1/2 size-5 -translate-y-1/2 text-slate-500" />

        <input
          id={id}
          name={name}
          type={type}
          autoComplete={autoComplete}
          placeholder={placeholder}
          required
          aria-invalid={Boolean(error)}
          aria-describedby={
            error ? `${id}-error` : undefined
          }
          className={`w-full rounded-lg border bg-surface py-3.5 pl-12 pr-4 text-foreground outline-none transition placeholder:text-muted-foreground ${
            error
              ? "border-red-400/40 focus:border-red-300"
              : "border-input focus:border-primary"
          }`}
        />
      </div>

      {error && (
        <p
          id={`${id}-error`}
          className="mt-2 text-sm text-red-300"
        >
          {error}
        </p>
      )}
    </div>
  );
}

type PasswordFieldProps = {
  id: string;
  name: string;
  label: string;
  placeholder: string;
  autoComplete: string;
  visible: boolean;
  onToggle: () => void;
  error?: string;
};

function PasswordField({
  id,
  name,
  label,
  placeholder,
  autoComplete,
  visible,
  onToggle,
  error,
}: PasswordFieldProps) {
  return (
    <div>
      <label
        htmlFor={id}
        className="mb-2 block text-sm font-medium text-foreground"
      >
        {label}
      </label>

      <div className="relative">
        <LockKeyhole className="pointer-events-none absolute left-4 top-1/2 size-5 -translate-y-1/2 text-slate-500" />

        <input
          id={id}
          name={name}
          type={visible ? "text" : "password"}
          autoComplete={autoComplete}
          placeholder={placeholder}
          minLength={8}
          required
          aria-invalid={Boolean(error)}
          aria-describedby={
            error ? `${id}-error` : undefined
          }
          className={`w-full rounded-lg border bg-surface py-3.5 pl-12 pr-12 text-foreground outline-none transition placeholder:text-muted-foreground ${
            error
              ? "border-red-400/40 focus:border-red-300"
              : "border-input focus:border-primary"
          }`}
        />

        <button
          type="button"
          onClick={onToggle}
          aria-label={
            visible ? "Ukryj hasło" : "Pokaż hasło"
          }
          className="absolute right-4 top-1/2 -translate-y-1/2 text-muted-foreground transition hover:text-foreground"
        >
          {visible ? (
            <EyeOff className="size-5" />
          ) : (
            <Eye className="size-5" />
          )}
        </button>
      </div>

      {error && (
        <p
          id={`${id}-error`}
          className="mt-2 text-sm text-red-300"
        >
          {error}
        </p>
      )}
    </div>
  );
}
