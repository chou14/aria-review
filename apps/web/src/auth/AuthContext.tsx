/**
 * AuthContext — 登录态（Phase B）。
 *
 * 用 react-query 查 /auth/me 作为登录态真源；监听 client.ts 广播的 aria:unauthorized
 * 事件（会话过期时）自动刷新，触发 RequireAuth 跳登录页。
 */
import { createContext, useContext, useEffect, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { authLogout, authMe, type AuthUser } from "../api/client";

const AUTH_KEY = ["auth", "me"] as const;

interface AuthState {
  user: AuthUser | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  refresh: () => void;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: AUTH_KEY,
    queryFn: authMe,
    staleTime: 60_000,
    retry: false,
  });

  useEffect(() => {
    const onUnauth = () => {
      qc.setQueryData(AUTH_KEY, null);
      qc.invalidateQueries({ queryKey: AUTH_KEY });
    };
    window.addEventListener("aria:unauthorized", onUnauth);
    return () => window.removeEventListener("aria:unauthorized", onUnauth);
  }, [qc]);

  const value: AuthState = {
    user: data ?? null,
    isLoading,
    isAuthenticated: !!data,
    refresh: () => qc.invalidateQueries({ queryKey: AUTH_KEY }),
    logout: async () => {
      try {
        await authLogout();
      } finally {
        qc.setQueryData(AUTH_KEY, null);
        qc.invalidateQueries({ queryKey: AUTH_KEY });
      }
    },
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth 必须在 AuthProvider 内使用");
  return ctx;
}
