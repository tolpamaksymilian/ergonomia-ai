"use client";

import { type ChangeEvent, type FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { Check, ImagePlus, LoaderCircle, TriangleAlert } from "lucide-react";

import { createClient } from "@/lib/supabase/client";

const MAX_IMAGE_BYTES = 20 * 1024 * 1024;
const allowedExtensions = new Set(["jpg", "jpeg", "png", "webp"]);
const allowedMimes = new Set(["image/jpeg", "image/png", "image/webp"]);

type Workstation = { id: string; name: string; code: string | null };
type Category = { id: string; name: string; group_name: string };
type ImageMetadata = { width: number; height: number; orientation: number };

export function PhotoSceneCreateForm({ userId, workstations, categories }: { userId: string; workstations: Workstation[]; categories: Category[] }) {
  const router = useRouter();
  const [supabase] = useState(() => createClient());
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [workstationId, setWorkstationId] = useState("");
  const [categoryIds, setCategoryIds] = useState<string[]>([]);
  const [processName, setProcessName] = useState("");
  const [notes, setNotes] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [metadata, setMetadata] = useState<ImageMetadata | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function chooseImage(event: ChangeEvent<HTMLInputElement>) {
    const selected = event.target.files?.[0] ?? null;
    setFile(null); setMetadata(null); setError(null);
    if (!selected) return;
    try {
      validateImageEnvelope(selected);
      await validateMagicBytes(selected);
      const decoded = await decodeImage(selected);
      setFile(selected); setMetadata(decoded);
    } catch (reason) {
      event.target.value = "";
      setError(reason instanceof Error ? reason.message : "Nie udało się odczytać zdjęcia.");
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(null);
    const cleanTitle = title.trim();
    if (cleanTitle.length < 3 || cleanTitle.length > 120) return setError("Nazwa musi zawierać od 3 do 120 znaków.");
    if (!file || !metadata) return setError("Dodaj poprawne zdjęcie stanowiska.");
    const analysisId = crypto.randomUUID();
    const safeName = file.name.replace(/[^a-zA-Z0-9._-]+/g, "-").replace(/^-+|-+$/g, "") || "scene-image";
    const path = `${userId}/${analysisId}/source/${safeName}`;
    setBusy(true);
    try {
      const { data: { user }, error: authError } = await supabase.auth.getUser();
      if (authError || user?.id !== userId) throw new Error("Sesja wygasła. Zaloguj się ponownie.");
      const { error: createError } = await supabase.from("analyses").insert({
        id: analysisId, user_id: userId, analysis_type: "PHOTO_SCENE",
        title: cleanTitle, description: description.trim() || null,
        status: "uploading", progress: 0, processing_stage: "photo-uploading",
        source_video_path: null, source_image_path: path,
        source_file_name: file.name, source_mime_type: file.type, source_size_bytes: file.size,
        source_width: metadata.width, source_height: metadata.height,
        workstation_id: workstationId || null,
        analysis_context: { schema_version: "1.0", process_name: processName.trim() || undefined, notes: notes.trim() || undefined },
      });
      if (createError) throw new Error(`Nie udało się utworzyć projektu: ${createError.message}`);
      const { error: uploadError } = await supabase.storage.from("analysis-scenes").upload(path, file, { contentType: file.type, upsert: false });
      if (uploadError) throw new Error(`Nie udało się przesłać zdjęcia: ${uploadError.message}`);
      if (categoryIds.length) {
        const { error: linkError } = await supabase.from("analysis_category_links").insert(categoryIds.map((categoryId) => ({ analysis_id: analysisId, category_id: categoryId, user_id: userId })));
        if (linkError) throw new Error(`Zdjęcie zapisano, ale nie udało się przypisać kategorii: ${linkError.message}`);
      }
      const { error: finalizeError } = await supabase.rpc("finalize_photo_scene_upload", {
        p_analysis_id: analysisId, p_image_width: metadata.width, p_image_height: metadata.height, p_image_orientation: metadata.orientation,
      });
      if (finalizeError) throw new Error(`Nie udało się przygotować konfiguracji sceny: ${finalizeError.message}`);
      router.push(`/panel/analizy/${analysisId}/scena`); router.refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Nie udało się utworzyć projektu.");
    } finally { setBusy(false); }
  }

  return <form onSubmit={submit} className="ui-card space-y-7 p-6 sm:p-8">
    <header><p className="text-xs font-bold uppercase tracking-[0.18em] text-primary">Photo Scene Builder · Beta</p><h2 className="mt-2 text-2xl font-bold">Informacje i zdjęcie</h2><p className="mt-2 text-sm text-muted-foreground">Po zapisie najpierw pokażesz systemowi podłogę i znane wymiary. Worker uruchomi się dopiero na Twoje polecenie.</p></header>
    <ol className="grid grid-cols-3 gap-2 text-center text-[10px] lg:grid-cols-9">{["Zdjęcie", "Podłoga", "Wysokości", "Wymiary", "Obiekty", "Worker", "Weryfikacja", "Operator", "Ergonomia"].map((step, index) => <li key={step} className={`rounded-xl border px-2 py-2 ${index === 0 ? "border-primary/30 bg-primary/10 text-primary" : "border-border text-muted-foreground"}`}>{index + 1}. {step}</li>)}</ol>
    <div className="grid gap-5 md:grid-cols-2">
      <label className="text-sm font-semibold">Nazwa projektu<input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={120} required className="mt-2 min-h-11 w-full rounded-xl border border-border bg-card px-3" /></label>
      <label className="text-sm font-semibold">Stanowisko<select value={workstationId} onChange={(e) => setWorkstationId(e.target.value)} className="mt-2 min-h-11 w-full rounded-xl border border-border bg-card px-3"><option value="">Bez przypisania</option>{workstations.map((item) => <option key={item.id} value={item.id}>{item.name}{item.code ? ` · ${item.code}` : ""}</option>)}</select></label>
      <label className="text-sm font-semibold md:col-span-2">Opis<textarea value={description} onChange={(e) => setDescription(e.target.value)} maxLength={1000} className="mt-2 min-h-24 w-full rounded-xl border border-border bg-card p-3" /></label>
      <label className="text-sm font-semibold">Proces<input value={processName} onChange={(e) => setProcessName(e.target.value)} maxLength={120} className="mt-2 min-h-11 w-full rounded-xl border border-border bg-card px-3" /></label>
      <label className="text-sm font-semibold">Notatki<input value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={500} className="mt-2 min-h-11 w-full rounded-xl border border-border bg-card px-3" /></label>
    </div>
    {!!categories.length && <fieldset><legend className="text-sm font-semibold">Kategorie</legend><div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">{categories.map((item) => <label key={item.id} className="flex min-h-11 items-center gap-2 rounded-xl border border-border px-3 text-sm"><input type="checkbox" checked={categoryIds.includes(item.id)} onChange={() => setCategoryIds((current) => current.includes(item.id) ? current.filter((id) => id !== item.id) : [...current, item.id])} />{item.group_name}: {item.name}</label>)}</div></fieldset>}
    <label className="block rounded-2xl border border-dashed border-primary/40 bg-primary/[0.04] p-6 text-center"><ImagePlus className="mx-auto size-8 text-primary" /><span className="mt-3 block font-semibold">Oryginalne zdjęcie stanowiska</span><span className="mt-1 block text-xs text-muted-foreground">JPG, PNG lub WEBP · maks. 20 MB · obraz zostanie zweryfikowany przez dekodowanie</span><input type="file" accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp" onChange={chooseImage} className="mt-4 block w-full text-sm" /></label>
    {file && metadata && <div className="flex items-center gap-3 rounded-xl border border-green-300 bg-green-50 p-4 text-sm text-green-900 dark:border-green-900 dark:bg-green-950/30 dark:text-green-200"><Check className="size-5" />{file.name} · {metadata.width}×{metadata.height}px</div>}
    {error && <div role="alert" className="flex gap-3 rounded-xl border border-red-300 bg-red-50 p-4 text-sm text-red-900 dark:border-red-900 dark:bg-red-950/30 dark:text-red-200"><TriangleAlert className="size-5 shrink-0" />{error}</div>}
    <div className="rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-950 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-100">Zdjęcie jest obrazem 2D. Detekcja wymaga potwierdzenia, a rzeczywiste wymiary wymagają ręcznej kalibracji. Ten moduł nie wykonuje jeszcze oceny ergonomicznej.</div>
    <button type="submit" disabled={busy || !file} className="ui-button-primary w-full justify-center disabled:opacity-50">{busy ? <><LoaderCircle className="size-5 animate-spin" />Tworzenie projektu…</> : "Dalej — oznacz podłogę"}</button>
  </form>;
}

function validateImageEnvelope(file: File) {
  const extension = file.name.split(".").pop()?.toLowerCase() ?? "";
  if (!allowedExtensions.has(extension) || !allowedMimes.has(file.type)) throw new Error("Dozwolone są wyłącznie pliki JPG, PNG i WEBP.");
  if (file.size <= 0 || file.size > MAX_IMAGE_BYTES) throw new Error("Zdjęcie musi mieć od 1 bajtu do 20 MB.");
}

async function validateMagicBytes(file: File) {
  const bytes = new Uint8Array(await file.slice(0, 16).arrayBuffer());
  const jpeg = bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff;
  const png = bytes[0] === 0x89 && bytes[1] === 0x50 && bytes[2] === 0x4e && bytes[3] === 0x47;
  const webp = String.fromCharCode(...bytes.slice(0, 4)) === "RIFF" && String.fromCharCode(...bytes.slice(8, 12)) === "WEBP";
  if (!jpeg && !png && !webp) throw new Error("Zawartość pliku nie odpowiada obsługiwanemu formatowi obrazu.");
}

async function decodeImage(file: File): Promise<ImageMetadata> {
  const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
  const result = { width: bitmap.width, height: bitmap.height, orientation: 1 };
  bitmap.close();
  if (result.width < 64 || result.height < 64) throw new Error("Zdjęcie jest zbyt małe. Minimalny wymiar to 64×64 px.");
  return result;
}
