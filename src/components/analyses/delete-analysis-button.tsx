"use client";

import {
  useActionState,
  useState,
} from "react";
import { useFormStatus } from "react-dom";
import {
  LoaderCircle,
  Trash2,
  TriangleAlert,
  X,
} from "lucide-react";

import { deleteAnalysisAction } from "@/actions/analyses";

type DeleteAnalysisButtonProps = {
  analysisId: string;
  title: string;
  status: string;
};

const initialDeleteState = {
  status: "idle" as const,
  message: "",
};

const deletableStatuses = new Set([
  "draft",
  "queued",
  "completed",
  "failed",
  "cancelled",
]);

export function DeleteAnalysisButton({
  analysisId,
  title,
  status,
}: DeleteAnalysisButtonProps) {
  const [isOpen, setIsOpen] =
    useState(false);

  const [
    state,
    formAction,
  ] = useActionState(
    deleteAnalysisAction,
    initialDeleteState,
  );

  const canDelete =
    deletableStatuses.has(status);

  if (!canDelete) {
    return null;
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setIsOpen(true)}
        className="flex items-center gap-2 rounded-xl border border-red-400/20 bg-red-400/[0.06] px-4 py-2.5 text-sm font-semibold text-red-200 transition hover:border-red-400/35 hover:bg-red-400/10"
      >
        <Trash2 className="size-4" />
        Usuń analizę
      </button>

      {isOpen && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="delete-analysis-title"
          className="fixed inset-0 z-[100] flex items-center justify-center bg-black/75 px-5 backdrop-blur-sm"
        >
          <div className="w-full max-w-lg rounded-[28px] border border-white/10 bg-[#08111f] p-6 shadow-2xl shadow-black/60 sm:p-8">
            <div className="flex items-start justify-between gap-5">
              <div className="flex size-12 shrink-0 items-center justify-center rounded-2xl border border-red-400/20 bg-red-400/10">
                <TriangleAlert className="size-6 text-red-300" />
              </div>

              <button
                type="button"
                onClick={() =>
                  setIsOpen(false)
                }
                aria-label="Zamknij"
                className="flex size-9 items-center justify-center rounded-xl border border-white/10 text-slate-400 transition hover:bg-white/[0.06] hover:text-white"
              >
                <X className="size-5" />
              </button>
            </div>

            <h2
              id="delete-analysis-title"
              className="mt-6 text-2xl font-bold text-white"
            >
              Usunąć analizę?
            </h2>

            <p className="mt-4 leading-7 text-slate-400">
              Analiza{" "}
              <strong className="font-semibold text-white">
                „{title}”
              </strong>{" "}
              zostanie trwale usunięta razem
              z prywatnym plikiem źródłowym.
            </p>

            <div className="mt-5 rounded-2xl border border-red-400/15 bg-red-400/[0.06] px-4 py-3 text-sm leading-6 text-red-200/80">
              Tej operacji nie będzie można
              cofnąć.
            </div>

            {state.status === "error" && (
              <div className="mt-5 rounded-2xl border border-red-400/20 bg-red-400/[0.08] px-4 py-3 text-sm leading-6 text-red-200">
                {state.message}
              </div>
            )}

            <form
              action={formAction}
              className="mt-7 flex flex-wrap justify-end gap-3"
            >
              <input
                type="hidden"
                name="analysisId"
                value={analysisId}
              />

              <button
                type="button"
                onClick={() =>
                  setIsOpen(false)
                }
                className="rounded-xl border border-white/10 bg-white/[0.04] px-5 py-3 font-semibold text-white transition hover:bg-white/[0.08]"
              >
                Anuluj
              </button>

              <DeleteSubmitButton />
            </form>
          </div>
        </div>
      )}
    </>
  );
}

function DeleteSubmitButton() {
  const { pending } = useFormStatus();

  return (
    <button
      type="submit"
      disabled={pending}
      className="flex items-center gap-2 rounded-xl bg-red-400 px-5 py-3 font-semibold text-slate-950 transition hover:bg-red-300 disabled:cursor-not-allowed disabled:opacity-60"
    >
      {pending ? (
        <>
          <LoaderCircle className="size-5 animate-spin" />
          Usuwanie...
        </>
      ) : (
        <>
          <Trash2 className="size-5" />
          Usuń trwale
        </>
      )}
    </button>
  );
}
