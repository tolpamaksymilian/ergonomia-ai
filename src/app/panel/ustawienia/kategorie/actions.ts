"use server";

import { revalidatePath } from "next/cache";
import { requireUser } from "@/lib/auth/access";

export async function createCategory(formData: FormData) { const { supabase, user } = await requireUser(); const { error } = await supabase.from("analysis_categories").insert({ user_id: user.id, name: required(formData,"name",80), group_name: required(formData,"group_name",80), description: optional(formData,"description",500) }); if (error) throw new Error(error.code === "23505" ? "Kategoria o tej nazwie już istnieje w tej grupie." : "Nie udało się dodać kategorii."); revalidatePath("/panel/ustawienia/kategorie"); }
export async function updateCategory(formData: FormData) { const { supabase } = await requireUser(); const id = required(formData,"id",36); const currentActive=formData.get("current_active")==="true"; const isActive=formData.get("intent")==="toggle"?!currentActive:currentActive; const { error } = await supabase.from("analysis_categories").update({ name: required(formData,"name",80), group_name: required(formData,"group_name",80), description: optional(formData,"description",500), is_active: isActive }).eq("id",id); if (error) throw new Error(error.code === "23505" ? "Kategoria o tej nazwie już istnieje w tej grupie." : "Nie udało się zapisać kategorii."); revalidatePath("/panel/ustawienia/kategorie"); }
function required(data: FormData,name:string,max:number){const value=optional(data,name,max);if(!value)throw new Error(`Pole ${name} jest wymagane.`);return value;}
function optional(data:FormData,name:string,max:number){const value=data.get(name);return typeof value==="string"&&value.trim()?value.trim().slice(0,max):null;}
