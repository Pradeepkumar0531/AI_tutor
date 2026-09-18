import { apiClient } from "./client";

export type DateRange = "7d" | "30d" | "90d" | "all";

export interface DashboardSummary {
  projectId: string;
  projectName: string;
  materialsCount: number;
  materialsReady: number;
  materialsFailed: number;
  documentsCount: number;
  pagesCount: number;
  chunksCount: number;
  imagesCount: number;
  conceptsCount: number;
  assessmentCount: number;
  questionsAnswered: number;
  questionsCorrect: number;
  questionsPartial: number;
  questionsIncorrect: number;
  averageAssessmentScore: number | null;
  overallMastery: number | null;
  masteryConfidence: number | null;
  growthStatus: "IMPROVING" | "STABLE" | "REQUIRING_ATTENTION" | null;
  activeRecommendations: number;
  tutorConversations: number;
  tutorMessages: number;
  lastActivityAt: string | null;
  hasLearningEvidence: boolean;
}

export interface ActivityItem {
  id: string;
  eventType: string;
  createdAt: string;
  resourceId: string | null;
  metadata: Record<string, unknown> | null;
  summary: string;
}

export interface ActivityDay {
  date: string;
  count: number;
}

export interface MasteryTrendPoint {
  date: string;
  score: number;
  assessmentId: string;
}

interface BackendSummary {
  project_id: string;
  project_name: string;
  materials_count: number;
  materials_ready: number;
  materials_failed: number;
  documents_count: number;
  pages_count: number;
  chunks_count: number;
  images_count: number;
  concepts_count: number;
  assessment_count: number;
  questions_answered: number;
  questions_correct: number;
  questions_partial: number;
  questions_incorrect: number;
  average_assessment_score: number | null;
  overall_mastery: number | null;
  mastery_confidence: number | null;
  growth_status: DashboardSummary["growthStatus"];
  active_recommendations: number;
  tutor_conversations: number;
  tutor_messages: number;
  last_activity_at: string | null;
  has_learning_evidence: boolean;
}

function toSummary(s: BackendSummary): DashboardSummary {
  return {
    projectId: s.project_id,
    projectName: s.project_name,
    materialsCount: s.materials_count,
    materialsReady: s.materials_ready,
    materialsFailed: s.materials_failed,
    documentsCount: s.documents_count,
    pagesCount: s.pages_count,
    chunksCount: s.chunks_count,
    imagesCount: s.images_count,
    conceptsCount: s.concepts_count,
    assessmentCount: s.assessment_count,
    questionsAnswered: s.questions_answered,
    questionsCorrect: s.questions_correct,
    questionsPartial: s.questions_partial,
    questionsIncorrect: s.questions_incorrect,
    averageAssessmentScore: s.average_assessment_score,
    overallMastery: s.overall_mastery,
    masteryConfidence: s.mastery_confidence,
    growthStatus: s.growth_status,
    activeRecommendations: s.active_recommendations,
    tutorConversations: s.tutor_conversations,
    tutorMessages: s.tutor_messages,
    lastActivityAt: s.last_activity_at,
    hasLearningEvidence: s.has_learning_evidence,
  };
}

interface BackendActivityItem {
  id: string;
  event_type: string;
  created_at: string;
  resource_id: string | null;
  metadata: Record<string, unknown> | null;
  summary: string;
}

function toActivityItem(a: BackendActivityItem): ActivityItem {
  return {
    id: a.id,
    eventType: a.event_type,
    createdAt: a.created_at,
    resourceId: a.resource_id,
    metadata: a.metadata,
    summary: a.summary,
  };
}

export const analyticsApi = {
  async dashboard(projectId: string): Promise<DashboardSummary> {
    const res = await apiClient.get<BackendSummary>(
      `/api/v1/projects/${projectId}/analytics/dashboard`,
    );
    return toSummary(res.data);
  },

  async activity(
    projectId: string,
    params: { range?: DateRange; limit?: number } = {},
  ): Promise<ActivityItem[]> {
    const res = await apiClient.get<{ items: BackendActivityItem[] }>(
      `/api/v1/projects/${projectId}/analytics/activity`,
      { params: { range: params.range ?? "30d", limit: params.limit ?? 8 } },
    );
    return res.data.items.map(toActivityItem);
  },

  async activityByDay(projectId: string, range: DateRange = "30d"): Promise<ActivityDay[]> {
    const res = await apiClient.get<ActivityDay[]>(
      `/api/v1/projects/${projectId}/analytics/activity-by-day`,
      { params: { range } },
    );
    return res.data;
  },

  async masteryTrend(projectId: string): Promise<MasteryTrendPoint[]> {
    const res = await apiClient.get<{ date: string; score: number; assessment_id: string }[]>(
      `/api/v1/projects/${projectId}/analytics/mastery-trend`,
    );
    return res.data.map((p) => ({ date: p.date, score: p.score, assessmentId: p.assessment_id }));
  },
};
