import { apiClient } from "./client";

export type GrowthStatus = "IMPROVING" | "STABLE" | "REQUIRING_ATTENTION";

export interface ConceptGrowthItem {
  conceptId: string;
  conceptName: string;
  status: GrowthStatus;
  masteryScore: number;
  confidence: number;
  trend: "IMPROVING" | "STABLE" | "DECLINING";
  changeScore: number | null;
  summary: string;
}

export interface ProjectGrowth {
  projectId: string;
  status: GrowthStatus;
  hasEvidence: boolean;
  overallMastery: number;
  averageConfidence: number;
  conceptsImproving: number;
  conceptsStable: number;
  conceptsRequiringAttention: number;
  assessedConcepts: number;
  assessmentCount: number;
  questionsAnswered: number;
  updatedAt: string | null;
  concepts: ConceptGrowthItem[];
}

export interface GrowthHistoryPoint {
  date: string;
  score: number;
  assessmentId: string;
}

interface BackendGrowth {
  project_id: string;
  status: GrowthStatus;
  has_evidence: boolean;
  overall_mastery: number;
  average_confidence: number;
  concepts_improving: number;
  concepts_stable: number;
  concepts_requiring_attention: number;
  assessed_concepts: number;
  assessment_count: number;
  questions_answered: number;
  updated_at: string | null;
  concepts: {
    concept_id: string;
    concept_name: string;
    status: GrowthStatus;
    mastery_score: number;
    confidence: number;
    trend: ConceptGrowthItem["trend"];
    change_score: number | null;
    summary: string;
  }[];
}

function toGrowth(g: BackendGrowth): ProjectGrowth {
  return {
    projectId: g.project_id,
    status: g.status,
    hasEvidence: g.has_evidence,
    overallMastery: g.overall_mastery,
    averageConfidence: g.average_confidence,
    conceptsImproving: g.concepts_improving,
    conceptsStable: g.concepts_stable,
    conceptsRequiringAttention: g.concepts_requiring_attention,
    assessedConcepts: g.assessed_concepts,
    assessmentCount: g.assessment_count,
    questionsAnswered: g.questions_answered,
    updatedAt: g.updated_at,
    concepts: (g.concepts ?? []).map((c) => ({
      conceptId: c.concept_id,
      conceptName: c.concept_name,
      status: c.status,
      masteryScore: c.mastery_score,
      confidence: c.confidence,
      trend: c.trend,
      changeScore: c.change_score,
      summary: c.summary,
    })),
  };
}

export const growthApi = {
  async get(projectId: string): Promise<ProjectGrowth> {
    const res = await apiClient.get<BackendGrowth>(`/api/v1/projects/${projectId}/growth`);
    return toGrowth(res.data);
  },

  async history(projectId: string): Promise<GrowthHistoryPoint[]> {
    const res = await apiClient.get<{
      items: { date: string; score: number; assessment_id: string }[];
    }>(`/api/v1/projects/${projectId}/growth/history`);
    return res.data.items.map((p) => ({
      date: p.date,
      score: p.score,
      assessmentId: p.assessment_id,
    }));
  },
};
