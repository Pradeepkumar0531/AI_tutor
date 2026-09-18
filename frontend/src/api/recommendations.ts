import { apiClient } from "./client";

export type RecommendationType =
  "REVIEW_CONCEPT" | "PRACTICE_QUIZ" | "STUDY_MATERIAL" | "TUTOR_SESSION";
export type RecommendationStatus = "ACTIVE" | "COMPLETED" | "DISMISSED" | "EXPIRED";

export interface Recommendation {
  id: string;
  projectId: string;
  conceptId: string | null;
  conceptName: string;
  materialId: string | null;
  materialName: string;
  type: RecommendationType;
  title: string;
  description: string | null;
  reason: string | null;
  actions: string[];
  priority: number;
  status: RecommendationStatus;
  sourceAssessmentId: string | null;
  createdAt: string;
  completedAt: string | null;
}

interface BackendRecommendation {
  id: string;
  project_id: string;
  concept_id: string | null;
  concept_name: string;
  material_id: string | null;
  material_name: string;
  type: RecommendationType;
  title: string;
  description: string | null;
  reason: string | null;
  actions: string[];
  priority: number;
  status: RecommendationStatus;
  source_assessment_id: string | null;
  created_at: string;
  completed_at: string | null;
}

function toRecommendation(r: BackendRecommendation): Recommendation {
  return {
    id: r.id,
    projectId: r.project_id,
    conceptId: r.concept_id,
    conceptName: r.concept_name,
    materialId: r.material_id,
    materialName: r.material_name,
    type: r.type,
    title: r.title,
    description: r.description,
    reason: r.reason,
    actions: r.actions ?? [],
    priority: r.priority,
    status: r.status,
    sourceAssessmentId: r.source_assessment_id,
    createdAt: r.created_at,
    completedAt: r.completed_at,
  };
}

export const recommendationsApi = {
  async list(projectId: string): Promise<Recommendation[]> {
    const res = await apiClient.get<{ items: BackendRecommendation[] }>(
      `/api/v1/projects/${projectId}/recommendations`,
    );
    return res.data.items.map(toRecommendation);
  },

  async complete(projectId: string, id: string): Promise<Recommendation> {
    const res = await apiClient.post<BackendRecommendation>(
      `/api/v1/projects/${projectId}/recommendations/${id}/complete`,
    );
    return toRecommendation(res.data);
  },

  async dismiss(projectId: string, id: string): Promise<Recommendation> {
    const res = await apiClient.post<BackendRecommendation>(
      `/api/v1/projects/${projectId}/recommendations/${id}/dismiss`,
    );
    return toRecommendation(res.data);
  },
};
