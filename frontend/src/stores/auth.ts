import { create } from "zustand";
import {
  signIn as apiSignIn,
  signUp as apiSignUp,
  signOut as apiSignOut,
  continueAsDemo as apiContinueAsDemo,
  fetchMe,
  getToken,
  type AuthUser,
} from "@/lib/api";

type Status = "loading" | "authed" | "anon";

interface AuthState {
  user: AuthUser | null;
  status: Status;
  /** On app load: validate an existing token, else mark anonymous. */
  init: () => Promise<void>;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (
    organizationName: string,
    fullName: string,
    email: string,
    password: string,
  ) => Promise<void>;
  continueAsDemo: () => Promise<void>;
  signOut: () => Promise<void>;
}

export const useAuth = create<AuthState>((set) => ({
  user: null,
  status: "loading",

  init: async () => {
    if (!getToken()) {
      set({ status: "anon", user: null });
      return;
    }
    try {
      const user = await fetchMe();
      set({ status: "authed", user });
    } catch {
      set({ status: "anon", user: null });
    }
  },

  signIn: async (email, password) => {
    const user = await apiSignIn(email, password);
    set({ status: "authed", user });
  },

  signUp: async (organizationName, fullName, email, password) => {
    const user = await apiSignUp(organizationName, fullName, email, password);
    set({ status: "authed", user });
  },

  continueAsDemo: async () => {
    const user = await apiContinueAsDemo();
    set({ status: "authed", user });
  },

  signOut: async () => {
    await apiSignOut();
    set({ status: "anon", user: null });
  },
}));
