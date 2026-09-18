import { apiClient } from "./client";

export { ApiError, apiClient, getAccessToken, setAccessToken, toApiError } from "./client";

/** Future feature APIs plug in here without redesigning the client:
 *  auth.ts, spaces.ts, projects.ts, materials.ts, tutor.ts, quizzes.ts, ...
 */
export async function getHealth(): Promise<{ status: string; service: string }> {
  const res = await apiClient.get("/api/v1/health");
  return res.data;
}

export async function getReadiness(): Promise<{ ready: boolean; database: unknown }> {
  const res = await apiClient.get("/api/v1/health/ready");
  return res.data;
}
