import { apiClient } from "./client";

export interface MasteryItem {
  conceptId: string;
  conceptName: string;
  masteryScore: number;
  confidence: number;
  trend: "IMPROVING" | "STABLE" | "DECLINING";
  evidenceCount: number;
  recentPerformance: string[];
  hasEvidence: boolean;
  updatedAt: string | null;
}

export interface MasteryDetail extends MasteryItem {
  evidenceQuestions: number;
  contributingAssessments: string[];
}

export interface MasteryHistoryItem {
  id: string;
  assessmentId: string | null;
  previousScore: number | null;
  newScore: number;
  confidence: number;
  createdAt: string;
}

interface BackendMastery {
  concept_id: string;
  concept_name: string;
  mastery_score: number;
  confidence: number;
  trend: MasteryItem["trend"];
  evidence_count: number;
  recent_performance: string[];
  has_evidence: boolean;
  updated_at: string | null;
  evidence_questions?: number;
  contributing_assessments?: string[];
}

interface BackendHistory {
  id: string;
  assessment_id: string | null;
  previous_score: number | null;
  new_score: number;
  confidence: number;
  created_at: string;
}

interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

function toItem(m: BackendMastery): MasteryItem {
  return {
    conceptId: m.concept_id,
    conceptName: m.concept_name,
    masteryScore: m.mastery_score,
    confidence: m.confidence,
    trend: m.trend,
    evidenceCount: m.evidence_count,
    recentPerformance: m.recent_performance ?? [],
    hasEvidence: m.has_evidence,
    updatedAt: m.updated_at,
  };
}

export const masteryApi = {
  async list(
    projectId: string,
    params: { page?: number; pageSize?: number; sort?: string } = {},
  ): Promise<{ items: MasteryItem[]; total: number }> {
    const res = await apiClient.get<Page<BackendMastery>>(`/api/v1/projects/${projectId}/mastery`, {
      params: {
        page: params.page ?? 1,
        page_size: params.pageSize ?? 20,
        sort: params.sort ?? "lowest",
      },
    });
    return { items: res.data.items.map(toItem), total: res.data.total };
  },

  async detail(projectId: string, conceptId: string): Promise<MasteryDetail> {
    const res = await apiClient.get<BackendMastery>(
      `/api/v1/projects/${projectId}/mastery/${conceptId}`,
    );
    return {
      ...toItem(res.data),
      evidenceQuestions: res.data.evidence_questions ?? 0,
      contributingAssessments: res.data.contributing_assessments ?? [],
    };
  },

  async history(projectId: string, conceptId: string): Promise<MasteryHistoryItem[]> {
    const res = await apiClient.get<Page<BackendHistory>>(
      `/api/v1/projects/${projectId}/mastery/${conceptId}/history`,
      { params: { page_size: 50 } },
    );
    return res.data.items.map((h) => ({
      id: h.id,
      assessmentId: h.assessment_id,
      previousScore: h.previous_score,
      newScore: h.new_score,
      confidence: h.confidence,
      createdAt: h.created_at,
    }));
  },
};
