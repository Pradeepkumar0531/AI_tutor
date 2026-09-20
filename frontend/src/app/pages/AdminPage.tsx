import {
  Activity,
  Bot,
  Cpu,
  Eye,
  Filter,
  FlaskConical,
  HeartPulse,
  LayoutDashboard,
  Play,
  ShieldCheck,
  Users,
  type LucideIcon,
} from "lucide-react";
import * as React from "react";

import { PageContainer, PageHeader } from "@/components/layout/PageHeader";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  EmptyState,
  ErrorState,
  Input,
  SectionLoading,
  SkeletonList,
  SkeletonStat,
  SkeletonTable,
  SkeletonText,
  Table,
  Tbody,
  Td,
  Th,
  Thead,
  Tr,
} from "@/components/ui";
import { useAdminStore } from "@/stores/useAdminStore";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Card variant="light">
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="rounded-[10px] border bg-card p-3">
      <p className="eyebrow">{label}</p>
      <p className="mt-1.5 text-xl font-semibold tracking-tight">{value}</p>
    </div>
  );
}

export function AdminPage() {
  const [tab, setTab] = React.useState("overview");
  const [journeyId, setJourneyId] = React.useState("");
  const [jobFilter, setJobFilter] = React.useState("");
  const [userSearch, setUserSearch] = React.useState("");
  const [aiUser, setAiUser] = React.useState("");
  const [actEventType, setActEventType] = React.useState("");
  const [actUserId, setActUserId] = React.useState("");
  const [actProjectId, setActProjectId] = React.useState("");
  const [actSpaceId, setActSpaceId] = React.useState("");
  const [actSince, setActSince] = React.useState("");
  const [actUntil, setActUntil] = React.useState("");
  const store = useAdminStore();

  React.useEffect(() => {
    void store.fetchOverview();
    // Health and the other heavy datasets load lazily when their tab is
    // selected (see below) — initial /admin load is Overview only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  React.useEffect(() => {
    if (tab === "users" && store.usersState === "idle") void store.fetchUsers();
    if (tab === "activity" && store.activityState === "idle") void store.fetchActivity();
    if (tab === "jobs" && store.jobsState === "idle") void store.fetchJobs();
    if (tab === "ai" && store.aiState === "idle") void store.fetchAi();
    if (tab === "eval" && store.evalState === "idle") void store.fetchEval();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

  const tabs: { id: string; label: string; icon: LucideIcon }[] = [
    { id: "overview", label: "Overview", icon: LayoutDashboard },
    { id: "users", label: "Users", icon: Users },
    { id: "activity", label: "Activity", icon: Activity },
    { id: "jobs", label: "Background Processing", icon: Cpu },
    { id: "ai", label: "AI Usage", icon: Bot },
    { id: "eval", label: "AI Evaluation", icon: FlaskConical },
    { id: "health", label: "System Health", icon: HeartPulse },
  ];

  return (
    <PageContainer>
      <PageHeader
        title="Admin dashboard"
        description="Platform operations: users, activity, jobs, AI usage, evaluation, and system health. Admin-only."
        eyebrow="Administration"
        icon={ShieldCheck}
        crumbs={[{ label: "Admin" }]}
      />
      <div
        className="sticky top-0 z-10 -mx-6 mb-6 flex gap-1 overflow-x-auto border-b bg-background/95 px-6 backdrop-blur"
        role="tablist"
        aria-label="Admin sections"
      >
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            role="tab"
            aria-selected={tab === t.id}
            className={
              tab === t.id
                ? "-mb-px whitespace-nowrap border-b-2 border-primary px-3 py-2.5 text-sm font-semibold text-primary"
                : "-mb-px whitespace-nowrap border-b-2 border-transparent px-3 py-2.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
            }
          >
            <span className="inline-flex items-center gap-1.5">
              <t.icon className="h-4 w-4" aria-hidden="true" />
              {t.label}
            </span>
          </button>
        ))}
      </div>
      {store.error ? (
        <ErrorState
          title="Admin request failed"
          description={store.error}
          onRetry={() => store.fetchOverview()}
        />
      ) : null}

      {tab === "overview" ? (
        store.overviewState === "loading" || store.overviewState === "idle" ? (
          <SectionLoading label="Loading overview">
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <SkeletonStat />
              <SkeletonStat />
              <SkeletonStat />
              <SkeletonStat />
              <SkeletonStat />
              <SkeletonStat />
              <SkeletonStat />
              <SkeletonStat />
            </div>
          </SectionLoading>
        ) : store.overview ? (
          <div className="flex flex-col gap-4">
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <Stat label="Users" value={store.overview.users} />
              <Stat label="Admins" value={store.overview.admins} />
              <Stat label="Spaces" value={store.overview.spaces} />
              <Stat label="Projects" value={store.overview.projects} />
              <Stat label="Materials" value={store.overview.materials} />
              <Stat label="Materials ready" value={store.overview.materialsReady} />
              <Stat label="Assessments" value={store.overview.assessments} />
              <Stat label="Quiz attempts" value={store.overview.quizAttempts} />
              <Stat label="Tutor conversations" value={store.overview.tutorConversations} />
              <Stat label="Tutor messages" value={store.overview.tutorMessages} />
              <Stat label="Active recommendations" value={store.overview.activeRecommendations} />
              <Stat label="AI calls" value={store.overview.aiCalls} />
              <Stat label="Evaluation runs" value={store.overview.evaluationRuns} />
              <Stat label="Events" value={store.overview.events} />
            </div>
            <div className="grid gap-4 lg:grid-cols-2">
              <Section title="Learning activity">
                <dl className="grid grid-cols-2 gap-2 text-sm">
                  <div>
                    <dt className="text-muted-foreground">Assessments</dt>
                    <dd className="font-medium">{store.overview.assessments}</dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">Quiz attempts</dt>
                    <dd className="font-medium">{store.overview.quizAttempts}</dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">Tutor conversations</dt>
                    <dd className="font-medium">{store.overview.tutorConversations}</dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">Tutor messages</dt>
                    <dd className="font-medium">{store.overview.tutorMessages}</dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">Platform events</dt>
                    <dd className="font-medium">{store.overview.events}</dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground">Evaluation runs</dt>
                    <dd className="font-medium">{store.overview.evaluationRuns}</dd>
                  </div>
                </dl>
                <div className="mt-3 flex flex-wrap gap-2">
                  <Button variant="outline" size="sm" onClick={() => setTab("activity")}>
                    Open Activity
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => setTab("eval")}>
                    Open AI Evaluation
                  </Button>
                </div>
              </Section>
              <Section title="Background processing">
                {Object.keys(store.overview.jobs).length === 0 ? (
                  <p className="text-sm text-muted-foreground">No jobs recorded yet.</p>
                ) : (
                  <ul className="flex flex-wrap gap-1.5">
                    {Object.entries(store.overview.jobs).map(([status, count]) => (
                      <li key={status}>
                        <Badge tone={status === "FAILED" ? "danger" : "default"}>
                          {status}: {count}
                        </Badge>
                      </li>
                    ))}
                  </ul>
                )}
                <div className="mt-3 flex flex-wrap gap-2">
                  <Button variant="outline" size="sm" onClick={() => setTab("jobs")}>
                    Open Background Processing
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => setTab("ai")}>
                    Open AI Usage
                  </Button>
                </div>
              </Section>
            </div>
          </div>
        ) : null
      ) : null}

      {tab === "users" ? (
        <Section title="Users">
          <div className="mb-3 flex gap-2">
            <Input
              placeholder="Filter by email…"
              value={userSearch}
              onChange={(e) => setUserSearch(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") void store.fetchUsers(userSearch.trim());
              }}
              aria-label="Filter users by email"
            />
            <Button variant="outline" onClick={() => void store.fetchUsers(userSearch.trim())}>
              <Filter className="h-4 w-4" aria-hidden="true" />
              Apply
            </Button>
          </div>
          {store.usersState === "loading" || store.usersState === "idle" ? (
            <SectionLoading label="Loading users">
              <SkeletonTable rows={5} cols={4} />
            </SectionLoading>
          ) : store.users && store.users.items.length > 0 ? (
            <div className="flex flex-col gap-3">
              <Table>
                <Thead>
                  <Tr>
                    <Th>Email</Th>
                    <Th>Role</Th>
                    <Th>Active</Th>
                    <Th>Inspect</Th>
                  </Tr>
                </Thead>
                <Tbody>
                  {store.users.items.map((u) => (
                    <Tr key={u.id}>
                      <Td>{u.email}</Td>
                      <Td>
                        <Badge tone={u.role === "admin" ? "info" : "default"}>{u.role}</Badge>
                      </Td>
                      <Td>{u.isActive ? "yes" : "no"}</Td>
                      <Td>
                        <Button
                          variant="outline"
                          onClick={() => {
                            setJourneyId(u.id);
                            void store.fetchJourney(u.id);
                          }}
                        >
                          <Eye className="h-4 w-4" aria-hidden="true" />
                          Inspect
                        </Button>
                      </Td>
                    </Tr>
                  ))}
                </Tbody>
              </Table>
              <p className="text-xs text-muted-foreground">Total: {store.users.total}</p>
              {store.journeyState === "loading" ? (
                <SectionLoading label="Loading user journey">
                  <SkeletonText lines={3} />
                </SectionLoading>
              ) : null}
              {store.journeyState === "ready" && store.journey ? (
                <JourneyView journey={store.journey as Journey} />
              ) : null}
              {store.journeyState === "ready" && !store.journey && journeyId ? (
                <EmptyState
                  title="User not found"
                  description="The inspected user no longer exists."
                />
              ) : null}
            </div>
          ) : (
            <EmptyState title="No users" description="No users registered yet." />
          )}
        </Section>
      ) : null}

      {tab === "activity" ? (
        <Section title="Platform activity">
          <div className="mb-3 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
            <Input
              placeholder="Event type (e.g. MATERIAL_UPLOADED)"
              value={actEventType}
              onChange={(e) => setActEventType(e.target.value)}
              aria-label="Filter activity by event type"
            />
            <Input
              placeholder="User ID"
              value={actUserId}
              onChange={(e) => setActUserId(e.target.value)}
              aria-label="Filter activity by user ID"
            />
            <Input
              placeholder="Project ID"
              value={actProjectId}
              onChange={(e) => setActProjectId(e.target.value)}
              aria-label="Filter activity by project ID"
            />
            <Input
              placeholder="Space ID"
              value={actSpaceId}
              onChange={(e) => setActSpaceId(e.target.value)}
              aria-label="Filter activity by space ID"
            />
            <Input
              type="datetime-local"
              value={actSince}
              onChange={(e) => setActSince(e.target.value)}
              aria-label="Filter activity since"
            />
            <Input
              type="datetime-local"
              value={actUntil}
              onChange={(e) => setActUntil(e.target.value)}
              aria-label="Filter activity until"
            />
          </div>
          <div className="mb-3 flex gap-2">
            <Button
              variant="outline"
              onClick={() =>
                void store.fetchActivity({
                  eventType: actEventType.trim() || undefined,
                  userId: actUserId.trim() || undefined,
                  projectId: actProjectId.trim() || undefined,
                  spaceId: actSpaceId.trim() || undefined,
                  since: actSince ? new Date(actSince).toISOString() : undefined,
                  until: actUntil ? new Date(actUntil).toISOString() : undefined,
                })
              }
            >
              <Filter className="h-4 w-4" aria-hidden="true" />
              Apply
            </Button>
            <Button
              variant="ghost"
              onClick={() => {
                setActEventType("");
                setActUserId("");
                setActProjectId("");
                setActSpaceId("");
                setActSince("");
                setActUntil("");
                void store.fetchActivity({});
              }}
            >
              Reset
            </Button>
          </div>
          {store.activityState === "loading" || store.activityState === "idle" ? (
            <SectionLoading label="Loading activity">
              <SkeletonTable rows={5} cols={4} />
            </SectionLoading>
          ) : store.activity && store.activity.items.length > 0 ? (
            <div className="flex flex-col gap-3">
              <Table>
                <Thead>
                  <Tr>
                    <Th>Type</Th>
                    <Th>When</Th>
                    <Th>User</Th>
                    <Th>Project</Th>
                  </Tr>
                </Thead>
                <Tbody>
                  {store.activity.items.map((e) => (
                    <Tr key={e.id}>
                      <Td>{e.eventType}</Td>
                      <Td>{new Date(e.createdAt).toLocaleString()}</Td>
                      <Td>{e.userId ? e.userId.slice(0, 8) : "—"}</Td>
                      <Td>{e.projectId ? e.projectId.slice(0, 8) : "—"}</Td>
                    </Tr>
                  ))}
                </Tbody>
              </Table>
              <p className="text-xs text-muted-foreground">Total: {store.activity.total}</p>
            </div>
          ) : (
            <EmptyState
              title="No activity"
              description="No platform events match the current filters."
            />
          )}
        </Section>
      ) : null}

      {tab === "jobs" ? (
        <Section title="Background Processing">
          <div className="mb-3 flex gap-2">
            <Input
              placeholder="Filter by status (e.g. FAILED)"
              value={jobFilter}
              onChange={(e) => setJobFilter(e.target.value)}
              aria-label="Filter jobs by status"
            />
            <Button
              variant="outline"
              onClick={() => void store.fetchJobs(jobFilter.trim() || undefined)}
            >
              <Filter className="h-4 w-4" aria-hidden="true" />
              Apply
            </Button>
          </div>
          {store.jobsState === "loading" || store.jobsState === "idle" ? (
            <SectionLoading label="Loading jobs">
              <SkeletonTable rows={5} cols={5} />
            </SectionLoading>
          ) : store.jobs && store.jobs.items.length > 0 ? (
            <Table>
              <Thead>
                <Tr>
                  <Th>Type</Th>
                  <Th>Status</Th>
                  <Th>Attempts</Th>
                  <Th>Error</Th>
                  <Th>Created</Th>
                </Tr>
              </Thead>
              <Tbody>
                {store.jobs.items.map((j) => (
                  <Tr key={j.id}>
                    <Td>{j.jobType}</Td>
                    <Td>
                      <Badge tone={j.status === "FAILED" ? "danger" : "default"}>{j.status}</Badge>
                    </Td>
                    <Td>
                      {j.attemptCount}/{j.maxRetries}
                    </Td>
                    <Td>{j.errorSummary ?? "—"}</Td>
                    <Td>{new Date(j.createdAt).toLocaleString()}</Td>
                  </Tr>
                ))}
              </Tbody>
            </Table>
          ) : (
            <EmptyState title="No jobs" description="No background jobs match." />
          )}
        </Section>
      ) : null}

      {tab === "ai" ? (
        <Section title="AI usage">
          <div className="mb-3 flex gap-2">
            <Input
              placeholder="Filter by user ID…"
              value={aiUser}
              onChange={(e) => setAiUser(e.target.value)}
              aria-label="Filter AI usage by user ID"
            />
            <Button
              variant="outline"
              onClick={() => void store.fetchAi(aiUser.trim() || undefined)}
            >
              <Filter className="h-4 w-4" aria-hidden="true" />
              Apply
            </Button>
          </div>
          {store.aiState === "loading" || store.aiState === "idle" ? (
            <SectionLoading label="Loading AI usage">
              <SkeletonTable rows={4} cols={5} />
            </SectionLoading>
          ) : store.aiSummary.length > 0 ? (
            <Table>
              <Thead>
                <Tr>
                  <Th>Feature</Th>
                  <Th>Provider</Th>
                  <Th>Model</Th>
                  <Th>Requests</Th>
                  <Th>Failures</Th>
                  <Th>Avg ms</Th>
                  <Th>Est. cost</Th>
                </Tr>
              </Thead>
              <Tbody>
                {store.aiSummary.map((r) => (
                  <Tr key={`${r.feature}-${r.provider}-${r.model}`}>
                    <Td>{r.feature}</Td>
                    <Td>{r.provider}</Td>
                    <Td>{r.model}</Td>
                    <Td>{r.requests}</Td>
                    <Td>{r.failures}</Td>
                    <Td>{r.avgLatencyMs}</Td>
                    <Td>${r.estimatedCostUsd.toFixed(6)}</Td>
                  </Tr>
                ))}
              </Tbody>
            </Table>
          ) : (
            <EmptyState
              title="No AI usage recorded"
              description="Usage rows appear after tutor, quiz, or knowledge AI calls."
            />
          )}
        </Section>
      ) : null}

      {tab === "eval" ? (
        <Section title="AI evaluation">
          <div className="mb-3">
            <Button onClick={() => void store.runEval()} disabled={store.running}>
              <Play className="h-4 w-4" aria-hidden="true" />
              {store.running ? "Running…" : "Run evaluation suite"}
            </Button>
          </div>
          {store.evalState === "loading" || store.evalState === "idle" ? (
            <SectionLoading label="Loading evaluation">
              <SkeletonText lines={2} />
              <SkeletonList rows={2} />
            </SectionLoading>
          ) : store.evalSummary ? (
            <div className="flex flex-col gap-2">
              <p className="text-sm">
                Last run: {store.evalSummary.passed}/{store.evalSummary.total} passed
                {store.evalSummary.createdAt
                  ? ` (${new Date(store.evalSummary.createdAt).toLocaleString()})`
                  : ""}
              </p>
              <ul className="flex flex-col gap-1 text-sm">
                {store.evalSummary.byCategory.map((c) => (
                  <li key={c.category}>
                    {c.category}: {c.passed}/{c.total} passed
                  </li>
                ))}
              </ul>
              {store.evalSummary.recentFailures.length > 0 ? (
                <div>
                  <p className="text-sm font-medium">Recent failures</p>
                  <ul className="flex flex-col gap-1 text-sm text-muted-foreground">
                    {store.evalSummary.recentFailures.map((f) => (
                      <li key={f.caseId}>
                        {f.caseId}: {f.reason}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
          ) : (
            <EmptyState
              title="No evaluation runs"
              description="Run the suite to produce the first result."
            />
          )}
        </Section>
      ) : null}

      {tab === "health" ? (
        <Section title="System Health">
          {store.healthState === "loading" || store.healthState === "idle" ? (
            <SectionLoading label="Loading system health">
              <SkeletonText lines={4} />
            </SectionLoading>
          ) : store.health ? (
            <dl className="grid grid-cols-2 gap-2 text-sm">
              <div>
                <dt className="text-muted-foreground">Overall</dt>
                <dd className="font-medium">{store.health.overall}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">API</dt>
                <dd className="font-medium">{store.health.api}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Database</dt>
                <dd className="font-medium">
                  {store.health.database}
                  {store.health.databaseConfigured ? "" : " (not configured)"}
                </dd>
              </div>
              <div>
                <dt className="text-muted-foreground">AI providers</dt>
                <dd className="font-medium">{JSON.stringify(store.health.ai)}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Storage</dt>
                <dd className="font-medium">{JSON.stringify(store.health.storage)}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Queue</dt>
                <dd className="font-medium">{JSON.stringify(store.health.queue)}</dd>
              </div>
            </dl>
          ) : (
            <EmptyState title="Health unavailable" description="Could not load system health." />
          )}
        </Section>
      ) : null}
    </PageContainer>
  );
}

interface Journey {
  user: { email: string; role: string; displayName?: string };
  project_ids: string[];
  spaces: { id: string; name: string }[];
  assessments: { id: string; status: string }[];
  recommendations: { id: string; title: string; type: string }[];
  mastery_concepts: number;
  mastery_avg: number;
  ai_requests: number;
  ai_estimated_cost_usd: number;
  recent_events: { id: string; event_type: string }[];
}

function JourneyView({ journey }: { journey: Journey }) {
  return (
    <div className="flex flex-col gap-2 rounded-lg border p-3">
      <p className="font-medium">
        {journey.user.email} ({journey.user.role})
      </p>
      <p className="text-sm text-muted-foreground">
        {journey.project_ids.length} projects · {journey.spaces.length} spaces ·{" "}
        {journey.assessments.length} recent assessments · mastery {journey.mastery_avg}% over{" "}
        {journey.mastery_concepts} concepts · {journey.ai_requests} AI requests (~$
        {journey.ai_estimated_cost_usd.toFixed(6)})
      </p>
      {journey.recommendations.length > 0 ? (
        <ul className="text-sm">
          {journey.recommendations.map((r) => (
            <li key={r.id}>
              {r.title} ({r.type})
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
