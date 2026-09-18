import { apiClient } from "./client";
import type { Page, Project } from "@/types";

interface BackendProject {
  id: string;
  space_id: string;
  owner_id: string;
  name: string;
  description: string | null;
  learning_goal: string | null;
  target_outcome?: string | null;
  difficulty?: string | null;
  archived_at: string | null;
  created_at: string;
  updated_at: string;
  material_count?: number | null;
}

function toProject(p: BackendProject): Project {
  return {
    id: p.id,
    spaceId: p.space_id,
    name: p.name,
    description: p.description,
    learningGoal: p.learning_goal,
    targetOutcome: p.target_outcome ?? null,
    difficulty: p.difficulty ?? null,
    archivedAt: p.archived_at,
    createdAt: p.created_at,
    updatedAt: p.updated_at,
    materialCount: p.material_count ?? null,
  };
}

export interface ProjectListParams {
  spaceId?: string;
  page?: number;
  pageSize?: number;
  search?: string;
  includeArchived?: boolean;
}

export interface ProjectInput {
  spaceId: string;
  name: string;
  description?: string;
  learningGoal?: string;
}

export interface ProjectUpdateInput {
  name?: string;
  description?: string;
  learningGoal?: string;
  targetOutcome?: string;
  difficulty?: string;
}

export const projectsApi = {
  async list(params: ProjectListParams = {}): Promise<Page<Project>> {
    const res = await apiClient.get<Page<BackendProject>>("/api/v1/projects", {
      params: {
        page: params.page ?? 1,
        page_size: params.pageSize ?? 20,
        ...(params.spaceId ? { space_id: params.spaceId } : {}),
        ...(params.search ? { search: params.search } : {}),
        ...(params.includeArchived ? { include_archived: true } : {}),
      },
    });
    return { ...res.data, items: res.data.items.map(toProject) };
  },

  async get(id: string): Promise<Project> {
    const res = await apiClient.get<BackendProject>(`/api/v1/projects/${id}`);
    return toProject(res.data);
  },

  async create(input: ProjectInput): Promise<Project> {
    const res = await apiClient.post<BackendProject>("/api/v1/projects", {
      space_id: input.spaceId,
      name: input.name,
      description: input.description ?? null,
      learning_goal: input.learningGoal ?? null,
    });
    return toProject(res.data);
  },

  async update(id: string, input: ProjectUpdateInput): Promise<Project> {
    const res = await apiClient.patch<BackendProject>(`/api/v1/projects/${id}`, {
      ...(input.name !== undefined ? { name: input.name } : {}),
      ...(input.description !== undefined ? { description: input.description } : {}),
      ...(input.learningGoal !== undefined ? { learning_goal: input.learningGoal } : {}),
      ...(input.targetOutcome !== undefined ? { target_outcome: input.targetOutcome } : {}),
      ...(input.difficulty !== undefined ? { difficulty: input.difficulty } : {}),
    });
    return toProject(res.data);
  },

  async archive(id: string): Promise<Project> {
    const res = await apiClient.delete<BackendProject>(`/api/v1/projects/${id}`);
    return toProject(res.data);
  },

  async restore(id: string): Promise<Project> {
    const res = await apiClient.post<BackendProject>(`/api/v1/projects/${id}/restore`);
    return toProject(res.data);
  },
};
