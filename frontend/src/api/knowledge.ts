import { apiClient } from "./client";
import type {
  Concept,
  KnowledgeSearchResponse,
  KnowledgeStatus,
  KnowledgeTotals,
  Page,
} from "@/types";

interface BackendKnowledgeStatus {
  project_id: string;
  status: KnowledgeStatus;
  totals: KnowledgeTotals;
}

interface BackendConcept {
  id: string;
  project_id: string;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
  materials?: { id: string; name: string }[];
  chunk_count?: number;
  pages?: number[];
}

function toConcept(c: BackendConcept): Concept {
  return {
    id: c.id,
    projectId: c.project_id,
    name: c.name,
    description: c.description,
    createdAt: c.created_at,
    updatedAt: c.updated_at,
    materials: c.materials,
    chunkCount: c.chunk_count,
    pages: c.pages,
  };
}

export const knowledgeApi = {
  async status(projectId: string): Promise<BackendKnowledgeStatus> {
    const res = await apiClient.get<BackendKnowledgeStatus>(
      `/api/v1/projects/${projectId}/knowledge`,
    );
    return res.data;
  },

  async concepts(projectId: string, params: { page?: number; pageSize?: number } = {}) {
    const res = await apiClient.get<Page<BackendConcept>>(
      `/api/v1/projects/${projectId}/concepts`,
      { params: { page: params.page ?? 1, page_size: params.pageSize ?? 20 } },
    );
    return { ...res.data, items: res.data.items.map(toConcept) };
  },

  async concept(projectId: string, conceptId: string): Promise<Concept> {
    const res = await apiClient.get<BackendConcept>(
      `/api/v1/projects/${projectId}/concepts/${conceptId}`,
    );
    return toConcept(res.data);
  },

  async search(
    projectId: string,
    input: { query: string; top_k?: number; threshold?: number; material_ids?: string[] },
  ): Promise<KnowledgeSearchResponse> {
    const res = await apiClient.post<KnowledgeSearchResponse>(
      `/api/v1/projects/${projectId}/knowledge/search`,
      input,
    );
    return res.data;
  },

  async reprocess(projectId: string, materialId: string) {
    const res = await apiClient.post<{ material_id: string; job_status: string; reset: number }>(
      `/api/v1/projects/${projectId}/materials/${materialId}/reprocess-knowledge`,
    );
    return res.data;
  },
};
