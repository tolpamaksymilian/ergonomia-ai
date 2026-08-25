"use server";

import { revalidatePath } from "next/cache";

import { requireUser } from "@/lib/auth/access";

export async function updateProfile(formData: FormData) {
  const { supabase, user } = await requireUser();
  const fullName = text(formData, "full_name", 160);
  if (!fullName || fullName.length < 2) throw new Error("Imię i nazwisko musi mieć co najmniej 2 znaki.");
  const { error } = await supabase.from("profiles").update({ full_name: fullName }).eq("id", user.id);
  if (error) throw new Error("Nie udało się zapisać profilu.");
  revalidatePath("/panel", "layout");
}

export async function createWorkstation(formData: FormData) {
  const { supabase, user } = await requireUser();
  const { error } = await supabase.from("workstations").insert({ user_id: user.id, name: required(formData,"name",120), code: text(formData,"code",80), department: text(formData,"department",120), area: text(formData,"area",120), description: text(formData,"description",500) });
  if (error) throw new Error(error.code === "23505" ? "Takie stanowisko już istnieje." : "Nie udało się dodać stanowiska.");
  revalidatePath("/panel/stanowiska");
}

export async function toggleWorkstation(formData: FormData) {
  const { supabase } = await requireUser(); const id = required(formData,"id",36); const next = formData.get("active") !== "true";
  const { error } = await supabase.from("workstations").update({ is_active: next }).eq("id",id); if(error) throw new Error("Nie udało się zmienić statusu stanowiska."); revalidatePath("/panel/stanowiska");
}
function required(data:FormData,key:string,max:number){const value=text(data,key,max);if(!value)throw new Error(`Pole ${key} jest wymagane.`);return value;} function text(data:FormData,key:string,max:number){const value=data.get(key);return typeof value==="string"&&value.trim()?value.trim().slice(0,max):null;}
