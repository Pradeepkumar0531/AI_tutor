import { apiClient } from "./client";
import { clearStoredToken, getStoredToken, setStoredToken } from "./tokenStorage";
import type { User } from "@/types";

interface BackendUser {
  id: string;
  email: string;
  display_name: string;
  role?: string;
  created_at: string;
}

interface BackendAuthResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: BackendUser;
}

function toUser(u: BackendUser): User {
  return {
    id: u.id,
    email: u.email,
    displayName: u.display_name,
    role: u.role ?? "learner",
    createdAt: u.created_at,
  };
}

export interface AuthResult {
  user: User;
}

export async function register(
  email: string,
  password: string,
  displayName: string,
): Promise<AuthResult> {
  const res = await apiClient.post<BackendAuthResponse>("/api/v1/auth/register", {
    email,
    password,
    display_name: displayName,
  });
  setStoredToken(res.data.access_token);
  return { user: toUser(res.data.user) };
}

export async function login(email: string, password: string): Promise<AuthResult> {
  const res = await apiClient.post<BackendAuthResponse>("/api/v1/auth/login", {
    email,
    password,
  });
  setStoredToken(res.data.access_token);
  return { user: toUser(res.data.user) };
}

export async function fetchCurrentUser(): Promise<User | null> {
  if (!getStoredToken()) return null;
  const res = await apiClient.get<BackendUser>("/api/v1/auth/me");
  return toUser(res.data);
}

export async function logout(): Promise<void> {
  try {
    await apiClient.post("/api/v1/auth/logout");
  } finally {
    // Client-side credential is always dropped, even if the server call fails:
    // with stateless JWTs the browser holds the only copy of the session.
    clearStoredToken();
  }
}
