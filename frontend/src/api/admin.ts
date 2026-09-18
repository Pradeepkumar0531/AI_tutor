import { apiClient } from "./client";

export interface AdminOverview {
  users: number;
  admins: number;
  spaces: number;
  projects: number;
  materials: number;
  materialsReady: number;
  assessments: number;
  quizAttempts: number;
  tutorConversations: number;
  tutorMessages: number;
  activeRecommendations: number;
  events: number;
  aiCalls: number;
  evaluationRuns: number;
  jobs: Record<string, number>;
}

export interface AdminUser {
  id: string;
  email: string;
  displayName: string;
  role: string;
  isActive: boolean;
  lastLoginAt: string | null;
  createdAt: string;
}

export interface AdminEvent {
  id: string;
  eventType: string;
  userId: string | null;
  projectId: string | null;
  entityType: string | null;
  entityId: string | null;
  createdAt: string;
}

export interface AdminJob {
  id: string;
  jobType: string;
  status: string;
  attemptCount: number;
  maxRetries: number;
  materialId: string | null;
  projectId: string | null;
  errorSummary: string | null;
  createdAt: string;
  startedAt: string | null;
  completedAt: string | null;
}

export interface AdminHealth {
  overall: string;
  api: string;
  database: string;
  databaseConfigured: boolean;
  ai: Record<string, unknown>;
  storage: Record<string, unknown>;
  queue: Record<string, unknown>;
}

export interface AdminAiSummaryItem {
  feature: string;
  provider: string;
  model: string;
  requests: number;
  failures: number;
  avgLatencyMs: number;
  inputTokens: number;
  outputTokens: number;
  estimatedCostUsd: number;
}

export interface AdminEvaluationSummary {
  runId: string;
  createdAt: string | null;
  total: number;
  passed: number;
  failed: number;
  byCategory: { category: string; total: number; passed: number }[];
  recentFailures: { caseId: string; category: string; reason: string }[];
}

export interface AdminEvaluationRun {
  id: string;
  triggeredById: string | null;
  totalCases: number;
  passed: number;
  failed: number;
  createdAt: string;
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
}

interface BackendUser {
  id: string;
  email: string;
  display_name: string;
  role: string;
  is_active: boolean;
  last_login_at: string | null;
  created_at: string;
}

function toUser(u: BackendUser): AdminUser {
  return {
    id: u.id,
    email: u.email,
    displayName: u.display_name,
    role: u.role,
    isActive: u.is_active,
    lastLoginAt: u.last_login_at,
    createdAt: u.created_at,
  };
}

interface BackendEvent {
  id: string;
  event_type: string;
  user_id: string | null;
  project_id: string | null;
  entity_type: string | null;
  entity_id: string | null;
  created_at: string;
}

function toEvent(e: BackendEvent): AdminEvent {
  return {
    id: e.id,
    eventType: e.event_type,
    userId: e.user_id,
    projectId: e.project_id,
    entityType: e.entity_type,
    entityId: e.entity_id,
    createdAt: e.created_at,
  };
}

interface BackendJob {
  id: string;
  job_type: string;
  status: string;
  attempt_count: number;
  max_retries: number;
  material_id: string | null;
  project_id: string | null;
  error_summary: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

function toJob(j: BackendJob): AdminJob {
  return {
    id: j.id,
    jobType: j.job_type,
    status: j.status,
    attemptCount: j.attempt_count,
    maxRetries: j.max_retries,
    materialId: j.material_id,
    projectId: j.project_id,
    errorSummary: j.error_summary,
    createdAt: j.created_at,
    startedAt: j.started_at,
    completedAt: j.completed_at,
  };
}

function toPage<T, B>(
  p: { items: B[]; total: number; page: number; page_size: number },
  fn: (b: B) => T,
): Page<T> {
  return { items: p.items.map(fn), total: p.total, page: p.page, pageSize: p.page_size };
}

export interface ActivityFilters {
  userId?: string;
  spaceId?: string;
  projectId?: string;
  eventType?: string;
  since?: string;
  until?: string;
}

export const adminApi = {
  async overview(): Promise<AdminOverview> {
    const res = await apiClient.get("/api/v1/admin/overview");
    const d = res.data;
    return {
      users: d.users,
      admins: d.admins,
      spaces: d.spaces,
      projects: d.projects,
      materials: d.materials,
      materialsReady: d.materials_ready,
      assessments: d.assessments,
      quizAttempts: d.quiz_attempts,
      tutorConversations: d.tutor_conversations,
      tutorMessages: d.tutor_messages,
      activeRecommendations: d.active_recommendations,
      events: d.events,
      aiCalls: d.ai_calls,
      evaluationRuns: d.evaluation_runs,
      jobs: d.jobs ?? {},
    };
  },

  async users(limit = 25, offset = 0, search?: string): Promise<Page<AdminUser>> {
    const params: Record<string, string | number> = { limit, offset };
    if (search?.trim()) params.search = search.trim();
    const res = await apiClient.get("/api/v1/admin/users", { params });
    return toPage(res.data, toUser);
  },

  async userJourney(userId: string): Promise<unknown> {
    const res = await apiClient.get(`/api/v1/admin/users/${userId}`);
    return res.data;
  },

  async activity(
    filters: ActivityFilters & { limit?: number; offset?: number } = {},
  ): Promise<Page<AdminEvent>> {
    const { limit = 25, offset = 0, ...rest } = filters;
    const params: Record<string, string | number> = { limit, offset };
    if (rest.userId) params.user_id = rest.userId;
    if (rest.spaceId) params.space_id = rest.spaceId;
    if (rest.projectId) params.project_id = rest.projectId;
    if (rest.eventType) params.event_type = rest.eventType;
    if (rest.since) params.since = rest.since;
    if (rest.until) params.until = rest.until;
    const res = await apiClient.get("/api/v1/admin/activity", { params });
    return toPage(res.data, toEvent);
  },

  async jobs(status?: string, limit = 25, offset = 0): Promise<Page<AdminJob>> {
    const params: Record<string, string | number> = { limit, offset };
    if (status) params.status = status;
    const res = await apiClient.get("/api/v1/admin/jobs", { params });
    return toPage(res.data, toJob);
  },

  async health(): Promise<AdminHealth> {
    const res = await apiClient.get("/api/v1/admin/health");
    const d = res.data;
    return {
      overall: d.overall,
      api: d.api,
      database: d.database,
      databaseConfigured: d.database_configured,
      ai: d.ai ?? {},
      storage: d.storage ?? {},
      queue: d.queue ?? {},
    };
  },

  async aiSummary(userId?: string): Promise<AdminAiSummaryItem[]> {
    const res = await apiClient.get("/api/v1/admin/ai-usage/summary", {
      params: userId ? { user_id: userId } : {},
    });
    return (res.data ?? []).map(
      (r: {
        feature: string;
        provider: string;
        model: string;
        requests: number;
        failures: number;
        avg_latency_ms: number;
        input_tokens: number;
        output_tokens: number;
        estimated_cost_usd: number;
      }) => ({
        feature: r.feature,
        provider: r.provider,
        model: r.model,
        requests: r.requests,
        failures: r.failures,
        avgLatencyMs: r.avg_latency_ms,
        inputTokens: r.input_tokens,
        outputTokens: r.output_tokens,
        estimatedCostUsd: r.estimated_cost_usd,
      }),
    );
  },

  async evaluationSummary(): Promise<AdminEvaluationSummary | null> {
    const res = await apiClient.get("/api/v1/admin/evaluations/summary");
    if (!res.data) return null;
    const d = res.data;
    return {
      runId: d.run_id,
      createdAt: d.created_at,
      total: d.total,
      passed: d.passed,
      failed: d.failed,
      byCategory: (d.by_category ?? []).map(
        (c: { category: string; total: number; passed: number }) => ({
          category: c.category,
          total: c.total,
          passed: c.passed,
        }),
      ),
      recentFailures: (d.recent_failures ?? []).map(
        (f: { case_id: string; category: string; reason: string }) => ({
          caseId: f.case_id,
          category: f.category,
          reason: f.reason,
        }),
      ),
    };
  },

  async evaluationRuns(limit = 10): Promise<AdminEvaluationRun[]> {
    const res = await apiClient.get("/api/v1/admin/evaluations", { params: { limit } });
    return (res.data.items ?? []).map(
      (r: {
        id: string;
        triggered_by_id: string | null;
        total_cases: number;
        passed: number;
        failed: number;
        created_at: string;
      }) => ({
        id: r.id,
        triggeredById: r.triggered_by_id,
        totalCases: r.total_cases,
        passed: r.passed,
        failed: r.failed,
        createdAt: r.created_at,
      }),
    );
  },

  async runEvaluations(): Promise<AdminEvaluationRun> {
    const res = await apiClient.post("/api/v1/admin/evaluations/run");
    const d = res.data;
    return {
      id: d.id,
      triggeredById: d.triggered_by_id,
      totalCases: d.total_cases,
      passed: d.passed,
      failed: d.failed,
      createdAt: d.created_at,
    };
  },
};
