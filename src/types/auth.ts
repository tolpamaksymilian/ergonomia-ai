export type AuthActionState = {
  status: "idle" | "error" | "success";
  message?: string;
  fieldErrors?: {
    fullName?: string;
    email?: string;
    password?: string;
    confirmPassword?: string;
  };
};

export const initialAuthState: AuthActionState = {
  status: "idle",
};