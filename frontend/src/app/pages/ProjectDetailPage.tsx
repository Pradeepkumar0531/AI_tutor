import * as React from "react";
import { Link, NavLink, Outlet, useNavigate, useParams } from "react-router-dom";
import { Archive, ArrowLeft, FileText, Gauge, Pencil, Target } from "lucide-react";

import { toApiError } from "@/api/client";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { Button } from "@/components/ui/button";
import { PageContainer, Breadcrumbs } from "@/components/layout/PageHeader";
import { ErrorState } from "@/components/ui/states";
import {
  SectionLabel,
  SectionLoading,
  SkeletonHeading,
  SkeletonList,
  SkeletonStat,
  SkeletonText,
  SlowHint,
} from "@/components/ui";
import { useSlowHint } from "@/hooks/useSlowHint";
import { useMasteryStore } from "@/stores/useMasteryStore";
import { useToast } from "@/components/ui/toast";
import {
  ProjectFormDialog,
  type ProjectFormValues,
} from "@/features/projects/components/ProjectFormDialog";
import { PROJECT_TABS } from "@/app/pages/project/ProjectTabs";
import { useMaterialsStore } from "@/stores/useMaterialsStore";
import { useProjectsStore } from "@/stores/useProjectsStore";
import { useSpacesStore } from "@/stores/useSpacesStore";
import { cn } from "@/lib/utils";

export function ProjectDetailPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const { push } = useToast();

  const project = useProjectsStore((s) => s.current);
  const status = useProjectsStore((s) => s.status);
  const error = useProjectsStore((s) => s.error);
  const fetchOne = useProjectsStore((s) => s.fetchOne);
  const updateProject = useProjectsStore((s) => s.update);
  const archiveProject = useProjectsStore((s) => s.archive);

  const spaces = useSpacesStore((s) => s.items);
  const fetchSpace = useSpacesStore((s) => s.fetchOne);

  const materialItems = useMaterialsStore((s) => s.items);
  const materialProjectId = useMaterialsStore((s) => s.projectId);
  const masteryItems = useMasteryStore((s) => s.items);

  const [editOpen, setEditOpen] = React.useState(false);
  const [archiveOpen, setArchiveOpen] = React.useState(false);
  const [archiving, setArchiving] = React.useState(false);

  React.useEffect(() => {
    if (projectId) void fetchOne(projectId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  const spaceId = project?.spaceId;
  React.useEffect(() => {
    if (spaceId && !spaces.some((s) => s.id === spaceId)) void fetchSpace(spaceId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [spaceId]);

  if (!projectId) {
    return (
      <PageContainer>
        <ErrorState title="Project not found" description="This project does not exist." />
      </PageContainer>
    );
  }

  // Route identity: the component instance is reused across client-side
  // navigation, so the first render for project B still holds project A (the
  // fetch effect hasn't run yet). Never render it — show the skeleton until
  // the store holds the project for THIS route. The error branch below still
  // handles genuine load failures (store clears `current` on error).
  if (project && project.id !== projectId) {
    return <ProjectDetailSkeleton />;
  }

  if (status === "loading" && !project) {
    return <ProjectDetailSkeleton />;
  }

  if (status === "error" || !project) {
    return (
      <PageContainer>
        <ErrorState
          title="Project not found"
          description={error ?? "This project does not exist or you cannot access it."}
        />
        <p className="mt-4 text-sm">
          <Link
            to="/projects"
            className="inline-flex items-center gap-1.5 font-medium text-primary hover:underline"
          >
            <ArrowLeft className="h-4 w-4" aria-hidden="true" />
            Back to projects
          </Link>
        </p>
      </PageContainer>
    );
  }

  const spaceName = spaces.find((s) => s.id === project.spaceId)?.name ?? "Space";
  const materialCount = project.materialCount ?? 0;
  const tracked = materialProjectId === project.id ? materialItems : [];
  const readyCount = tracked.filter((m) => m.status === "READY").length;
  const masteryAvg =
    masteryItems.length > 0
      ? Math.round(
          (masteryItems.reduce((sum, m) => sum + (m.masteryScore ?? 0), 0) / masteryItems.length) *
            100,
        )
      : null;

  async function handleEdit(values: ProjectFormValues) {
    const current = useProjectsStore.getState().current;
    if (!current) return;
    try {
      await updateProject(current.id, {
        name: values.name,
        description: values.description,
        learningGoal: values.learningGoal,
      });
      setEditOpen(false);
      push("Project updated.");
    } catch (e) {
      push(`Could not update project: ${toApiError(e).message}`);
      throw e;
    }
  }

  async function handleArchive() {
    const current = useProjectsStore.getState().current;
    if (!current) return;
    setArchiving(true);
    try {
      await archiveProject(current.id);
      push("Project archived.");
      navigate(`/spaces/${current.spaceId}`);
    } catch (e) {
      push(`Could not archive project: ${toApiError(e).message}`);
    } finally {
      setArchiving(false);
      setArchiveOpen(false);
    }
  }

  return (
    <PageContainer>
      <Breadcrumbs
        items={[
          { label: "Spaces", to: "/spaces" },
          { label: spaceName, to: `/spaces/${project.spaceId}` },
          { label: project.name },
        ]}
      />
      <div className="card-dark mt-3 rounded-[10px] border p-5 sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <SectionLabel>Project</SectionLabel>
            <h1 className="mt-1 text-[28px] font-semibold leading-tight tracking-tight">
              {project.name}
            </h1>
            <p className="mt-1 max-w-2xl text-sm leading-relaxed text-primary-foreground/75">
              {project.description || project.learningGoal || "Your learning workspace."}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="secondary" size="sm" onClick={() => setEditOpen(true)}>
              <Pencil className="h-4 w-4" aria-hidden="true" />
              Edit project
            </Button>
            <Button variant="secondary" size="sm" onClick={() => setArchiveOpen(true)}>
              <Archive className="h-4 w-4" aria-hidden="true" />
              Archive
            </Button>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap gap-x-6 gap-y-1 text-sm text-primary-foreground/75">
          {project.learningGoal ? (
            <span className="inline-flex items-center gap-1.5">
              <Target className="h-3.5 w-3.5" aria-hidden="true" />
              Goal: {project.learningGoal}
            </span>
          ) : null}
          {project.difficulty ? (
            <span className="inline-flex items-center gap-1.5">
              <Gauge className="h-3.5 w-3.5" aria-hidden="true" />
              Difficulty: {project.difficulty.toLowerCase()}
            </span>
          ) : null}
          <span className="inline-flex items-center gap-1.5">
            <FileText className="h-3.5 w-3.5" aria-hidden="true" />
            {materialCount} {materialCount === 1 ? "material" : "materials"}
          </span>
        </div>
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        <div className="card-dark rounded-[10px] border p-4">
          <p className="eyebrow">Materials ready</p>
          <p className="mt-2 text-[26px] font-semibold leading-none tracking-tight">
            {tracked.length > 0 ? `${readyCount}/${tracked.length}` : materialCount}
          </p>
          <p className="mt-1.5 text-xs text-primary-foreground/70">
            {tracked.length > 0 ? "tracked in this session" : "total materials"}
          </p>
        </div>
        <div className="card-dark rounded-[10px] border p-4">
          <p className="eyebrow">Average mastery</p>
          <p className="mt-2 text-[26px] font-semibold leading-none tracking-tight">
            {masteryAvg !== null ? `${masteryAvg}%` : "—"}
          </p>
          <p className="mt-1.5 text-xs text-primary-foreground/70">
            across {masteryItems.length} concepts
          </p>
        </div>
        <div className="card-dark rounded-[10px] border p-4">
          <p className="eyebrow">Processing</p>
          <p className="mt-2 text-[26px] font-semibold leading-none tracking-tight">
            {tracked.length > 0 ? tracked.length - readyCount : 0}
          </p>
          <p className="mt-1.5 text-xs text-primary-foreground/70">materials pending</p>
        </div>
      </div>

      <nav
        aria-label="Project"
        className="sticky top-0 z-10 -mx-6 mt-6 border-b bg-background/95 px-6 backdrop-blur"
      >
        <div className="flex gap-1 overflow-x-auto">
          {PROJECT_TABS.map((t) => (
            <NavLink
              key={t.to}
              to={t.to}
              className={({ isActive }) =>
                cn(
                  "-mb-px whitespace-nowrap border-b-2 px-3 py-2.5 text-sm transition-colors",
                  isActive
                    ? "border-primary font-semibold text-primary"
                    : "border-transparent text-muted-foreground hover:text-foreground",
                )
              }
            >
              {t.label}
            </NavLink>
          ))}
        </div>
      </nav>

      <div className="mt-6">
        <Outlet />
      </div>

      <ProjectFormDialog
        open={editOpen}
        onOpenChange={setEditOpen}
        initial={project}
        presetSpaceId={project.spaceId}
        onSubmit={handleEdit}
      />
      <ConfirmDialog
        open={archiveOpen}
        onOpenChange={setArchiveOpen}
        title="Archive this project?"
        description={`"${project.name}" will be hidden along with its future materials and history. Nothing is deleted — you can restore it later.`}
        confirmLabel="Archive project"
        pending={archiving}
        onConfirm={() => void handleArchive()}
      />
    </PageContainer>
  );
}

function ProjectDetailSkeleton() {
  const slow = useSlowHint(true);
  return (
    <PageContainer>
      <SectionLoading label="Loading project" className="flex flex-col gap-4">
        <SkeletonText lines={1} className="max-w-40" />
        <div>
          <SectionLabel>Project</SectionLabel>
          <SkeletonHeading className="mt-1 w-64" />
          <SkeletonText lines={1} className="mt-2 max-w-md" />
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          <SkeletonStat />
          <SkeletonStat />
          <SkeletonStat />
        </div>
        <SkeletonList rows={2} />
        <SlowHint show={slow}>Still loading your project…</SlowHint>
      </SectionLoading>
    </PageContainer>
  );
}
