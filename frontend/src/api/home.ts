import { apiClient } from "./client";

export interface AttentionItem {
  projectId: string;
  concept: string;
  change: number;
}

export interface GlobalSummary {
  projects: number;
  materials: number;
  materialsReady: number;
  assessments: number;
  questionsAnswered: number;
  tutorMessages: number;
  masteryAvg: number;
  masteryConcepts: number;
  attention: AttentionItem[];
  activeRecommendations: number;
  recentProjectIds: string[];
  lastActivityAt: string | null;
}

export interface HomeNextAction {
  kind: string;
  title: string;
  reason: string;
  projectId: string;
  recommendationId: string | null;
}

export interface HomeData {
  continueLearning: {
    projectId: string;
    projectName: string;
    spaceId: string;
    materials: number;
    nextAction: HomeNextAction;
  } | null;
  recentProjects: { id: string; name: string; spaceId: string; updatedAt: string | null }[];
  progress: {
    projects: number;
    materials: number;
    materialsReady: number;
    assessments: number;
    questionsAnswered: number;
    masteryAvg: number;
    masteryConcepts: number;
  };
  attention: AttentionItem[];
  recommendedAction: HomeNextAction | null;
}

interface BackendAttention {
  project_id: string;
  concept: string;
  change: number;
}

interface BackendSummary {
  projects: number;
  materials: number;
  materials_ready: number;
  assessments: number;
  questions_answered: number;
  tutor_messages: number;
  mastery_avg: number;
  mastery_concepts: number;
  attention: BackendAttention[];
  active_recommendations: number;
  recent_project_ids: string[];
  last_activity_at: string | null;
}

function toAttention(a: BackendAttention): AttentionItem {
  return { projectId: a.project_id, concept: a.concept, change: a.change };
}

function toSummary(s: BackendSummary): GlobalSummary {
  return {
    projects: s.projects,
    materials: s.materials,
    materialsReady: s.materials_ready,
    assessments: s.assessments,
    questionsAnswered: s.questions_answered,
    tutorMessages: s.tutor_messages,
    masteryAvg: s.mastery_avg,
    masteryConcepts: s.mastery_concepts,
    attention: s.attention.map(toAttention),
    activeRecommendations: s.active_recommendations,
    recentProjectIds: s.recent_project_ids,
    lastActivityAt: s.last_activity_at,
  };
}

interface BackendAction {
  kind: string;
  title: string;
  reason: string;
  project_id: string;
  recommendation_id: string | null;
}

function toAction(a: BackendAction): HomeNextAction {
  return {
    kind: a.kind,
    title: a.title,
    reason: a.reason,
    projectId: a.project_id,
    recommendationId: a.recommendation_id,
  };
}

export const homeApi = {
  async summary(): Promise<GlobalSummary> {
    const res = await apiClient.get<BackendSummary>("/api/v1/analytics/summary");
    return toSummary(res.data);
  },

  async home(): Promise<HomeData> {
    const res = await apiClient.get("/api/v1/home");
    const d = res.data;
    return {
      continueLearning: d.continue_learning
        ? {
            projectId: d.continue_learning.project_id,
            projectName: d.continue_learning.project_name,
            spaceId: d.continue_learning.space_id,
            materials: d.continue_learning.materials,
            nextAction: toAction(d.continue_learning.next_action),
          }
        : null,
      recentProjects: (d.recent_projects ?? []).map(
        (p: { id: string; name: string; space_id: string; updated_at: string | null }) => ({
          id: p.id,
          name: p.name,
          spaceId: p.space_id,
          updatedAt: p.updated_at,
        }),
      ),
      progress: {
        projects: d.progress.projects,
        materials: d.progress.materials,
        materialsReady: d.progress.materials_ready,
        assessments: d.progress.assessments,
        questionsAnswered: d.progress.questions_answered,
        masteryAvg: d.progress.mastery_avg,
        masteryConcepts: d.progress.mastery_concepts,
      },
      attention: (d.attention ?? []).map(toAttention),
      recommendedAction: d.recommended_action ? toAction(d.recommended_action) : null,
    };
  },
};
