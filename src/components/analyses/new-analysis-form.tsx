"use client";

import type {
  ChangeEvent,
  FormEvent,
} from "react";
import {
  useRef,
  useState,
} from "react";
import { useRouter } from "next/navigation";
import * as tus from "tus-js-client";
import {
  CheckCircle2,
  FileVideo,
  Film,
  LoaderCircle,
  Ruler,
  UploadCloud,
  X,
  XCircle,
} from "lucide-react";

import { createClient } from "@/lib/supabase/client";

const MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024;
const TUS_CHUNK_SIZE_BYTES = 6 * 1024 * 1024;

const ALLOWED_EXTENSIONS = new Set([
  "mp4",
  "webm",
  "mov",
]);

const ALLOWED_MIME_TYPES = new Set([
  "video/mp4",
  "video/webm",
  "video/quicktime",
]);

type UploadPhase =
  | "idle"
  | "preparing"
  | "uploading"
  | "finalizing"
  | "success"
  | "error"
  | "cancelled";

type VideoMetadata = {
  durationSeconds: number | null;
  width: number | null;
  height: number | null;
};

type NewAnalysisFormProps = {
  userId: string;
};

export function NewAnalysisForm({
  userId,
}: NewAnalysisFormProps) {
  const router = useRouter();

  const [supabase] = useState(() => createClient());

  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");

  const [file, setFile] = useState<File | null>(null);

  const [videoMetadata, setVideoMetadata] =
    useState<VideoMetadata | null>(null);

  const [metadataWarning, setMetadataWarning] =
    useState<string | null>(null);

  const [isReadingMetadata, setIsReadingMetadata] =
    useState(false);

  const [phase, setPhase] =
    useState<UploadPhase>("idle");

  const [progress, setProgress] = useState(0);

  const [errorMessage, setErrorMessage] =
    useState<string | null>(null);

  const uploadRef = useRef<tus.Upload | null>(null);

  const rejectUploadRef = useRef<
    ((reason?: unknown) => void) | null
  >(null);

  const analysisIdRef = useRef<string | null>(null);
  const cancelRequestedRef = useRef(false);

  const isBusy =
    phase === "preparing" ||
    phase === "uploading" ||
    phase === "finalizing";

  async function handleFileChange(
    event: ChangeEvent<HTMLInputElement>,
  ) {
    const selectedFile =
      event.target.files?.[0] ?? null;

    setFile(null);
    setVideoMetadata(null);
    setMetadataWarning(null);
    setErrorMessage(null);
    setProgress(0);
    setPhase("idle");

    if (!selectedFile) {
      return;
    }

    const validationError =
      validateVideoFile(selectedFile);

    if (validationError) {
      event.target.value = "";
      setErrorMessage(validationError);
      setPhase("error");
      return;
    }

    setFile(selectedFile);
    setIsReadingMetadata(true);

    try {
      const metadata =
        await readVideoMetadata(selectedFile);

      setVideoMetadata(metadata);
    } catch {
      setVideoMetadata({
        durationSeconds: null,
        width: null,
        height: null,
      });

      setMetadataWarning(
        "Przeglądarka nie odczytała parametrów nagrania. " +
          "Film może zostać wysłany, a dane techniczne odczyta później worker.",
      );
    } finally {
      setIsReadingMetadata(false);
    }
  }

  async function handleSubmit(
    event: FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault();

    setErrorMessage(null);
    cancelRequestedRef.current = false;

    const normalizedTitle = title.trim();
    const normalizedDescription =
      description.trim();

    if (
      normalizedTitle.length < 3 ||
      normalizedTitle.length > 120
    ) {
      setPhase("error");
      setErrorMessage(
        "Tytuł musi zawierać od 3 do 120 znaków.",
      );
      return;
    }

    if (!file) {
      setPhase("error");
      setErrorMessage("Wybierz film do analizy.");
      return;
    }

    const fileValidationError =
      validateVideoFile(file);

    if (fileValidationError) {
      setPhase("error");
      setErrorMessage(fileValidationError);
      return;
    }

    const analysisId = crypto.randomUUID();

    analysisIdRef.current = analysisId;

    const safeFileName = sanitizeFileName(file.name);

    const storagePath =
      `${userId}/${analysisId}/source/${safeFileName}`;

    const contentType = getContentType(file);

    try {
      setPhase("preparing");
      setProgress(0);

      const {
        data: { session },
        error: sessionError,
      } = await supabase.auth.getSession();

      if (
        sessionError ||
        !session ||
        session.user.id !== userId
      ) {
        throw new Error(
          "Sesja użytkownika wygasła. Zaloguj się ponownie.",
        );
      }

      const { error: createError } = await supabase
        .from("analyses")
        .insert({
          id: analysisId,
          user_id: userId,
          title: normalizedTitle,
          description:
            normalizedDescription || null,

          status: "uploading",
          progress: 0,

          source_video_path: storagePath,
          source_file_name: file.name,
          source_mime_type: contentType,
          source_size_bytes: file.size,

          source_duration_seconds:
            videoMetadata?.durationSeconds ?? null,

          source_width:
            videoMetadata?.width ?? null,

          source_height:
            videoMetadata?.height ?? null,
        });

      if (createError) {
        throw new Error(
          `Nie udało się utworzyć analizy: ${createError.message}`,
        );
      }

      setPhase("uploading");

      await uploadVideoWithTus({
        file,
        analysisId,
        storagePath,
        contentType,
        accessToken: session.access_token,
        onProgress: setProgress,
      });

      if (cancelRequestedRef.current) {
        return;
      }

      setPhase("finalizing");
      setProgress(100);

      await finalizeUploadWithRetry(analysisId);

      setPhase("success");

      router.push(
        `/panel/analizy/${analysisId}`,
      );

      router.refresh();
    } catch (error) {
      if (cancelRequestedRef.current) {
        return;
      }

      const message =
        error instanceof Error
          ? error.message
          : "Wystąpił nieznany błąd przesyłania.";

      const analysisId =
        analysisIdRef.current;

      if (analysisId) {
        await supabase.rpc(
          "mark_analysis_upload_failed",
          {
            p_analysis_id: analysisId,
            p_error_message: message,
          },
        );
      }

      setPhase("error");
      setErrorMessage(message);
    }
  }

  async function uploadVideoWithTus({
    file,
    analysisId,
    storagePath,
    contentType,
    accessToken,
    onProgress,
  }: {
    file: File;
    analysisId: string;
    storagePath: string;
    contentType: string;
    accessToken: string;
    onProgress: (value: number) => void;
  }) {
    const supabaseUrl =
      process.env.NEXT_PUBLIC_SUPABASE_URL;

    if (!supabaseUrl) {
      throw new Error(
        "Brakuje NEXT_PUBLIC_SUPABASE_URL.",
      );
    }

    const projectHost =
      new URL(supabaseUrl).hostname;

    const projectId =
      projectHost.split(".")[0];

    if (!projectId) {
      throw new Error(
        "Nie udało się ustalić identyfikatora projektu Supabase.",
      );
    }

    const endpoint =
      `https://${projectId}.storage.supabase.co` +
      "/storage/v1/upload/resumable";

    await new Promise<void>((resolve, reject) => {
      rejectUploadRef.current = reject;

      const upload = new tus.Upload(file, {
        endpoint,

        retryDelays: [
          0,
          3000,
          5000,
          10000,
          20000,
        ],

        chunkSize: TUS_CHUNK_SIZE_BYTES,

        uploadDataDuringCreation: true,
        removeFingerprintOnSuccess: true,

        headers: {
          authorization:
            `Bearer ${accessToken}`,
        },

        metadata: {
          bucketName: "analysis-videos",
          objectName: storagePath,
          contentType,
          cacheControl: "3600",
        },

        fingerprint: () =>
          Promise.resolve(
            [
              "ergonomia-ai",
              analysisId,
              file.name,
              file.size,
              file.lastModified,
            ].join(":"),
          ),

        onProgress(
          bytesUploaded,
          bytesTotal,
        ) {
          if (bytesTotal <= 0) {
            onProgress(0);
            return;
          }

          const percentage = Math.min(
            100,
            Math.round(
              (bytesUploaded / bytesTotal) * 100,
            ),
          );

          onProgress(percentage);
        },

        onError(error) {
          uploadRef.current = null;
          rejectUploadRef.current = null;
          reject(error);
        },

        onSuccess() {
          uploadRef.current = null;
          rejectUploadRef.current = null;
          resolve();
        },
      });

      uploadRef.current = upload;

      upload
        .findPreviousUploads()
        .then((previousUploads) => {
          if (previousUploads.length > 0) {
            upload.resumeFromPreviousUpload(
              previousUploads[0],
            );
          }

          upload.start();
        })
        .catch((error: unknown) => {
          uploadRef.current = null;
          rejectUploadRef.current = null;
          reject(error);
        });
    });
  }

  async function finalizeUploadWithRetry(
    analysisId: string,
  ) {
    let lastErrorMessage =
      "Nie udało się skierować analizy do kolejki.";

    for (
      let attempt = 1;
      attempt <= 3;
      attempt += 1
    ) {
      const { error } = await supabase.rpc(
        "finalize_analysis_upload",
        {
          p_analysis_id: analysisId,
        },
      );

      if (!error) {
        return;
      }

      lastErrorMessage = error.message;

      if (attempt < 3) {
        await wait(attempt * 700);
      }
    }

    throw new Error(lastErrorMessage);
  }

  async function handleCancel() {
    cancelRequestedRef.current = true;

    const activeUpload = uploadRef.current;
    const analysisId = analysisIdRef.current;

    if (activeUpload) {
      try {
        await activeUpload.abort(true);
      } catch {
        try {
          await activeUpload.abort();
        } catch {
          // Upload został już zatrzymany albo zakończony.
        }
      }
    }

    rejectUploadRef.current?.(
      new Error("UPLOAD_CANCELLED"),
    );

    rejectUploadRef.current = null;
    uploadRef.current = null;

    if (analysisId) {
      await supabase.rpc(
        "cancel_analysis_upload",
        {
          p_analysis_id: analysisId,
        },
      );
    }

    setPhase("cancelled");
    setErrorMessage(
      "Przesyłanie filmu zostało anulowane.",
    );
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="space-y-6"
    >
      <section className="rounded-[28px] border border-white/10 bg-white/[0.035] p-6 sm:p-8">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-emerald-400">
          Informacje o analizie
        </p>

        <div className="mt-6 grid gap-6">
          <div>
            <label
              htmlFor="analysis-title"
              className="mb-2 block text-sm font-medium text-slate-200"
            >
              Tytuł analizy
            </label>

            <input
              id="analysis-title"
              type="text"
              value={title}
              onChange={(event) =>
                setTitle(event.target.value)
              }
              disabled={isBusy}
              minLength={3}
              maxLength={120}
              required
              placeholder="Np. Stanowisko montażu pomp – zmiana 1"
              className="w-full rounded-xl border border-white/10 bg-slate-950/60 px-4 py-3.5 text-white outline-none transition placeholder:text-slate-600 focus:border-emerald-400/50 disabled:opacity-60"
            />

            <p className="mt-2 text-right text-xs text-slate-600">
              {title.length}/120
            </p>
          </div>

          <div>
            <label
              htmlFor="analysis-description"
              className="mb-2 block text-sm font-medium text-slate-200"
            >
              Opis lub uwagi
            </label>

            <textarea
              id="analysis-description"
              value={description}
              onChange={(event) =>
                setDescription(
                  event.target.value,
                )
              }
              disabled={isBusy}
              rows={4}
              maxLength={1500}
              placeholder="Opcjonalnie: rodzaj wykonywanej pracy, obserwowane problemy, warunki nagrania..."
              className="w-full resize-none rounded-xl border border-white/10 bg-slate-950/60 px-4 py-3.5 text-white outline-none transition placeholder:text-slate-600 focus:border-emerald-400/50 disabled:opacity-60"
            />

            <p className="mt-2 text-right text-xs text-slate-600">
              {description.length}/1500
            </p>
          </div>
        </div>
      </section>

      <section className="rounded-[28px] border border-white/10 bg-white/[0.035] p-6 sm:p-8">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-accent-foreground">
              Film źródłowy
            </p>

            <h2 className="mt-3 text-2xl font-semibold">
              Wybierz nagranie stanowiska
            </h2>

            <p className="mt-2 text-sm leading-6 text-slate-400">
              Obsługiwane formaty: MP4, WebM i MOV.
              Maksymalny rozmiar: 50 MB.
            </p>
          </div>

          <div className="rounded-xl border border-white/10 bg-slate-950/40 px-4 py-2 text-xs text-slate-400">
            Prywatny Storage
          </div>
        </div>

        <label
          htmlFor="analysis-video"
          className={`mt-7 flex min-h-[210px] cursor-pointer flex-col items-center justify-center rounded-2xl border border-dashed px-6 text-center transition ${
            isBusy
              ? "cursor-not-allowed border-white/10 opacity-50"
              : file
                ? "border-emerald-400/30 bg-emerald-400/[0.05]"
                : "border-border bg-surface-muted hover:border-orange-200 hover:bg-brand-soft"
          }`}
        >
          {isReadingMetadata ? (
            <>
              <LoaderCircle className="size-10 animate-spin text-primary" />

              <p className="mt-4 font-semibold">
                Odczytywanie parametrów filmu...
              </p>
            </>
          ) : file ? (
            <>
              <CheckCircle2 className="size-11 text-emerald-300" />

              <p className="mt-4 max-w-xl break-all font-semibold text-white">
                {file.name}
              </p>

              <p className="mt-2 text-sm text-slate-400">
                {formatBytes(file.size)}
              </p>

              {!isBusy && (
                <p className="mt-4 text-xs font-semibold text-emerald-300">
                  Kliknij, aby wybrać inny film
                </p>
              )}
            </>
          ) : (
            <>
              <UploadCloud className="size-12 text-primary" />

              <p className="mt-5 text-lg font-semibold">
                Kliknij, aby wybrać film
              </p>

              <p className="mt-2 text-sm text-slate-500">
                Plik zostanie wysłany dopiero po zatwierdzeniu formularza
              </p>
            </>
          )}

          <input
            id="analysis-video"
            type="file"
            accept="video/mp4,video/webm,video/quicktime,.mp4,.webm,.mov"
            onChange={handleFileChange}
            disabled={isBusy}
            className="sr-only"
          />
        </label>

        {videoMetadata && file && (
          <div className="mt-5 grid gap-3 sm:grid-cols-3">
            <FileMetric
              icon={Film}
              label="Długość"
              value={formatDuration(
                videoMetadata.durationSeconds,
              )}
            />

            <FileMetric
              icon={Ruler}
              label="Rozdzielczość"
              value={
                videoMetadata.width &&
                videoMetadata.height
                  ? `${videoMetadata.width} × ${videoMetadata.height}`
                  : "Odczyta worker"
              }
            />

            <FileMetric
              icon={FileVideo}
              label="Typ pliku"
              value={getContentType(file)}
            />
          </div>
        )}

        {metadataWarning && (
          <div className="mt-5 rounded-2xl border border-amber-300/20 bg-amber-400/[0.07] px-4 py-3 text-sm leading-6 text-amber-100/80">
            {metadataWarning}
          </div>
        )}
      </section>

      {phase !== "idle" &&
        phase !== "error" &&
        phase !== "cancelled" && (
          <section className="rounded-xl border border-border bg-card p-6">
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="text-xs uppercase tracking-[0.17em] text-slate-500">
                  Postęp operacji
                </p>

                <p className="mt-2 font-semibold text-white">
                  {getPhaseLabel(phase)}
                </p>
              </div>

              <p className="text-2xl font-bold text-accent-foreground">
                {progress}%
              </p>
            </div>

            <div className="mt-5 h-2 overflow-hidden rounded-full bg-white/10">
              <div
                className="h-full rounded-full bg-primary transition-[width] duration-300"
                style={{
                  width: `${progress}%`,
                }}
              />
            </div>
          </section>
        )}

      {errorMessage && (
        <div
          className={`flex items-start gap-3 rounded-2xl border p-4 text-sm leading-6 ${
            phase === "cancelled"
              ? "border-amber-300/20 bg-amber-400/[0.07] text-amber-100/80"
              : "border-red-400/20 bg-red-400/[0.07] text-red-200"
          }`}
        >
          {phase === "cancelled" ? (
            <X className="mt-0.5 size-5 shrink-0" />
          ) : (
            <XCircle className="mt-0.5 size-5 shrink-0" />
          )}

          {errorMessage}
        </div>
      )}

      <div className="flex flex-wrap justify-end gap-3">
        {phase === "uploading" && (
          <button
            type="button"
            onClick={handleCancel}
            className="flex items-center gap-2 rounded-xl border border-red-400/20 bg-red-400/[0.06] px-5 py-3 font-semibold text-red-200 transition hover:bg-red-400/10"
          >
            <X className="size-5" />
            Anuluj przesyłanie
          </button>
        )}

        <button
          type="submit"
          disabled={
            isBusy ||
            isReadingMetadata ||
            !file
          }
          className="flex items-center gap-2 rounded-xl bg-emerald-400 px-6 py-3 font-semibold text-slate-950 shadow-xl shadow-emerald-500/15 transition hover:bg-emerald-300 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isBusy ? (
            <>
              <LoaderCircle className="size-5 animate-spin" />
              {getPhaseLabel(phase)}
            </>
          ) : (
            <>
              <UploadCloud className="size-5" />
              Utwórz analizę
            </>
          )}
        </button>
      </div>
    </form>
  );
}

function FileMetric({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof Film;
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-2xl border border-white/[0.07] bg-slate-950/35 p-4">
      <Icon className="size-5 text-primary" />

      <p className="mt-3 text-[10px] uppercase tracking-[0.16em] text-slate-500">
        {label}
      </p>

      <p className="mt-1 truncate text-sm font-semibold text-white">
        {value}
      </p>
    </div>
  );
}

function validateVideoFile(
  file: File,
): string | null {
  if (file.size <= 0) {
    return "Wybrany plik jest pusty.";
  }

  if (file.size > MAX_FILE_SIZE_BYTES) {
    return (
      "Film przekracza maksymalny rozmiar 50 MB. " +
      `Rozmiar wybranego pliku: ${formatBytes(file.size)}.`
    );
  }

  const extension = getFileExtension(file.name);

  if (!ALLOWED_EXTENSIONS.has(extension)) {
    return "Dozwolone formaty filmu to MP4, WebM i MOV.";
  }

  if (
    file.type &&
    !ALLOWED_MIME_TYPES.has(file.type)
  ) {
    return `Nieobsługiwany typ pliku: ${file.type}.`;
  }

  return null;
}

function sanitizeFileName(
  originalName: string,
) {
  const extension =
    getFileExtension(originalName) || "mp4";

  const withoutExtension =
    originalName.includes(".")
      ? originalName.slice(
          0,
          originalName.lastIndexOf("."),
        )
      : originalName;

  const safeBaseName = withoutExtension
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80);

  return `${safeBaseName || "video"}.${extension}`;
}

function getFileExtension(
  fileName: string,
) {
  const lastPart =
    fileName.split(".").pop();

  return lastPart?.toLowerCase() ?? "";
}

function getContentType(
  file: File,
) {
  if (ALLOWED_MIME_TYPES.has(file.type)) {
    return file.type;
  }

  const extension =
    getFileExtension(file.name);

  if (extension === "webm") {
    return "video/webm";
  }

  if (extension === "mov") {
    return "video/quicktime";
  }

  return "video/mp4";
}

function readVideoMetadata(
  file: File,
): Promise<VideoMetadata> {
  return new Promise((resolve, reject) => {
    const objectUrl =
      URL.createObjectURL(file);

    const video =
      document.createElement("video");

    video.preload = "metadata";
    video.muted = true;
    video.playsInline = true;

    function cleanup() {
      URL.revokeObjectURL(objectUrl);
      video.removeAttribute("src");
      video.load();
    }

    video.onloadedmetadata = () => {
      const duration =
        Number.isFinite(video.duration)
          ? Number(video.duration.toFixed(3))
          : null;

      const width =
        video.videoWidth > 0
          ? video.videoWidth
          : null;

      const height =
        video.videoHeight > 0
          ? video.videoHeight
          : null;

      cleanup();

      resolve({
        durationSeconds: duration,
        width,
        height,
      });
    };

    video.onerror = () => {
      cleanup();

      reject(
        new Error(
          "Nie udało się odczytać metadanych filmu.",
        ),
      );
    };

    video.src = objectUrl;
  });
}

function formatBytes(
  bytes: number,
) {
  if (bytes < 1024) {
    return `${bytes} B`;
  }

  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }

  return `${(
    bytes /
    (1024 * 1024)
  ).toFixed(1)} MB`;
}

function formatDuration(
  seconds: number | null,
) {
  if (
    seconds === null ||
    !Number.isFinite(seconds)
  ) {
    return "Odczyta worker";
  }

  const totalSeconds =
    Math.max(0, Math.round(seconds));

  const minutes =
    Math.floor(totalSeconds / 60);

  const remainingSeconds =
    totalSeconds % 60;

  return `${minutes}:${String(
    remainingSeconds,
  ).padStart(2, "0")}`;
}

function getPhaseLabel(
  phase: UploadPhase,
) {
  switch (phase) {
    case "preparing":
      return "Przygotowywanie analizy...";

    case "uploading":
      return "Przesyłanie filmu...";

    case "finalizing":
      return "Dodawanie do kolejki...";

    case "success":
      return "Analiza utworzona";

    default:
      return "Przetwarzanie...";
  }
}

function wait(
  milliseconds: number,
) {
  return new Promise<void>((resolve) => {
    window.setTimeout(resolve, milliseconds);
  });
}
