import { apiClient } from "./client";
import type { Page, Space } from "@/types";

interface BackendSpace {
  id: string;
  owner_id: string;
  name: string;
  description: string | null;
  icon: string | null;
  color: string | null;
  archived_at: string | null;
  created_at: string;
  updated_at: string;
  project_count?: number | null;
}

function toSpace(s: BackendSpace): Space {
  return {
    id: s.id,
    name: s.name,
    description: s.description,
    archivedAt: s.archived_at,
    createdAt: s.created_at,
    updatedAt: s.updated_at,
    projectCount: s.project_count ?? null,
  };
}

export interface SpaceListParams {
  page?: number;
  pageSize?: number;
  search?: string;
  includeArchived?: boolean;
}

export const spacesApi = {
  async list(params: SpaceListParams = {}): Promise<Page<Space>> {
    const res = await apiClient.get<Page<BackendSpace>>("/api/v1/spaces", {
      params: {
        page: params.page ?? 1,
        page_size: params.pageSize ?? 20,
        ...(params.search ? { search: params.search } : {}),
        ...(params.includeArchived ? { include_archived: true } : {}),
      },
    });
    return { ...res.data, items: res.data.items.map(toSpace) };
  },

  async get(id: string): Promise<Space> {
    const res = await apiClient.get<BackendSpace>(`/api/v1/spaces/${id}`);
    return toSpace(res.data);
  },

  async create(input: { name: string; description?: string }): Promise<Space> {
    const res = await apiClient.post<BackendSpace>("/api/v1/spaces", {
      name: input.name,
      description: input.description ?? null,
    });
    return toSpace(res.data);
  },

  async update(id: string, input: { name?: string; description?: string }): Promise<Space> {
    const res = await apiClient.patch<BackendSpace>(`/api/v1/spaces/${id}`, input);
    return toSpace(res.data);
  },

  async archive(id: string): Promise<Space> {
    const res = await apiClient.delete<BackendSpace>(`/api/v1/spaces/${id}`);
    return toSpace(res.data);
  },

  async restore(id: string): Promise<Space> {
    const res = await apiClient.post<BackendSpace>(`/api/v1/spaces/${id}/restore`);
    return toSpace(res.data);
  },
};
