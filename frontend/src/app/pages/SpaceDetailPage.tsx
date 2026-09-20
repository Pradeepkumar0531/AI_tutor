import { Archive, ArrowLeft, FolderKanban, Pencil, Plus, Search } from "lucide-react";
import * as React from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { toApiError } from "@/api/client";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PageContainer, Breadcrumbs } from "@/components/layout/PageHeader";
import { EmptyState, ErrorState } from "@/components/ui/states";
import {
  SectionLabel,
  SectionLoading,
  SkeletonEntryCards,
  SkeletonHeading,
  SkeletonStat,
  SkeletonText,
} from "@/components/ui";
import { useToast } from "@/components/ui/toast";
import { ProjectCard } from "@/features/projects/components/ProjectCard";
import {
  ProjectFormDialog,
  type ProjectFormValues,
} from "@/features/projects/components/ProjectFormDialog";
import {
  SpaceFormDialog,
  type SpaceFormValues,
} from "@/features/spaces/components/SpaceFormDialog";
import { useProjectsStore } from "@/stores/useProjectsStore";
import { useSpacesStore } from "@/stores/useSpacesStore";

export function SpaceDetailPage() {
  const { spaceId } = useParams<{ spaceId: string }>();
  const navigate = useNavigate();
  const { push } = useToast();

  const space = useSpacesStore((s) => s.current);
  const spaceStatus = useSpacesStore((s) => s.status);
  const spaceError = useSpacesStore((s) => s.error);
  const fetchOneSpace = useSpacesStore((s) => s.fetchOne);
  const updateSpace = useSpacesStore((s) => s.update);
  const archiveSpace = useSpacesStore((s) => s.archive);

  const projects = useProjectsStore((s) => s.items);
  const projectsTotal = useProjectsStore((s) => s.total);
  const projectsStatus = useProjectsStore((s) => s.status);
  const projectsSpaceId = useProjectsStore((s) => s.spaceId);
  const fetchProjects = useProjectsStore((s) => s.fetch);
  const createProject = useProjectsStore((s) => s.create);

  const [editOpen, setEditOpen] = React.useState(false);
  const [archiveOpen, setArchiveOpen] = React.useState(false);
  const [archiving, setArchiving] = React.useState(false);
  const [projectDialogOpen, setProjectDialogOpen] = React.useState(false);
  const [searchInput, setSearchInput] = React.useState("");

  React.useEffect(() => {
    if (spaceId) void fetchOneSpace(spaceId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [spaceId]);

  // Project list: debounced search within a space, but an immediate scoped
  // fetch when the space itself changes (no 300ms window showing the previous
  // space's projects; the store also drops that space's rows synchronously).
  const loadedSpace = React.useRef<string | null>(null);
  React.useEffect(() => {
    if (!spaceId) return;
    if (loadedSpace.current !== spaceId) {
      loadedSpace.current = spaceId;
      setSearchInput("");
      void fetchProjects({ spaceId, page: 1, search: "" });
      return;
    }
    const t = setTimeout(() => void fetchProjects({ spaceId, page: 1, search: searchInput }), 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchInput, spaceId]);

  if (!spaceId) {
    return (
      <PageContainer>
        <ErrorState title="Space not found" description="This space does not exist." />
      </PageContainer>
    );
  }

  async function handleEdit(values: SpaceFormValues) {
    if (!spaceId) return;
    try {
      await updateSpace(spaceId, values);
      setEditOpen(false);
      push("Space updated.");
    } catch (e) {
      push(`Could not update space: ${toApiError(e).message}`);
      throw e;
    }
  }

  async function handleArchive() {
    if (!spaceId) return;
    setArchiving(true);
    try {
      await archiveSpace(spaceId);
      push("Space archived.");
      navigate("/spaces");
    } catch (e) {
      push(`Could not archive space: ${toApiError(e).message}`);
    } finally {
      setArchiving(false);
      setArchiveOpen(false);
    }
  }

  async function handleCreateProject(values: ProjectFormValues) {
    if (!spaceId) return;
    try {
      const project = await createProject({ ...values, spaceId });
      setProjectDialogOpen(false);
      push("Project created.");
      navigate(`/projects/${project.id}`);
    } catch (e) {
      push(`Could not create project: ${toApiError(e).message}`);
      throw e;
    }
  }

  if (spaceStatus === "loading" && !space) {
    return (
      <PageContainer>
        <SectionLoading label="Loading space" className="flex flex-col gap-4">
          <div>
            <SectionLabel>Space</SectionLabel>
            <SkeletonHeading className="mt-1 w-56" />
            <SkeletonText lines={1} className="mt-2 max-w-md" />
          </div>
          <SkeletonEntryCards count={3} />
        </SectionLoading>
      </PageContainer>
    );
  }

  // Route identity: the component instance is reused across client-side
  // navigation, so the first render for space B still holds space A (the
  // fetch effect hasn't run yet). Never render it — show the skeleton until
  // the store holds the space for THIS route.
  if (space && space.id !== spaceId) {
    return (
      <PageContainer>
        <SectionLoading label="Loading space" className="flex flex-col gap-4">
          <div>
            <SectionLabel>Space</SectionLabel>
            <SkeletonHeading className="mt-1 w-56" />
            <SkeletonText lines={1} className="mt-2 max-w-md" />
          </div>
          <SkeletonEntryCards count={3} />
        </SectionLoading>
      </PageContainer>
    );
  }

  if (spaceStatus === "error" || !space) {
    return (
      <PageContainer>
        <ErrorState
          title="Space not found"
          description={spaceError ?? "This space does not exist or you cannot access it."}
        />
        <p className="mt-4 text-sm">
          <Link
            to="/spaces"
            className="inline-flex items-center gap-1.5 font-medium text-primary hover:underline"
          >
            <ArrowLeft className="h-4 w-4" aria-hidden="true" />
            Back to spaces
          </Link>
        </p>
      </PageContainer>
    );
  }

  // List scope: the store tags rows with the space they were fetched for.
  // Until the new space's fetch starts, the rows on screen belong to the
  // previous space — hide them and show skeletons instead.
  const listFresh = projectsSpaceId === spaceId;
  const visibleProjects = listFresh ? projects : [];

  return (
    <PageContainer>
      <Breadcrumbs items={[{ label: "Spaces", to: "/spaces" }, { label: space.name }]} />
      <div className="card-dark mt-3 rounded-[10px] border p-5 sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <SectionLabel>Space</SectionLabel>
            <h1 className="mt-1 text-[28px] font-semibold leading-tight tracking-tight">
              {space.name}
            </h1>
            <p className="mt-1 max-w-2xl text-sm leading-relaxed text-primary-foreground/75">
              {space.description || "No description yet."}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="secondary" size="sm" onClick={() => setEditOpen(true)}>
              <Pencil className="h-4 w-4" aria-hidden="true" />
              Edit space
            </Button>
            <Button variant="secondary" size="sm" onClick={() => setArchiveOpen(true)}>
              <Archive className="h-4 w-4" aria-hidden="true" />
              Archive
            </Button>
            <Button variant="secondary" size="sm" onClick={() => setProjectDialogOpen(true)}>
              <Plus className="h-4 w-4" aria-hidden="true" />
              New Project
            </Button>
          </div>
        </div>
      </div>

      {!listFresh ? (
        <div className="mb-6 mt-4 flex flex-wrap gap-3" aria-label="Loading project statistics">
          <SkeletonStat />
          <SkeletonStat />
        </div>
      ) : (
        <div className="mb-6 mt-4 flex flex-wrap gap-3">
          <div className="card-dark rounded-[10px] border px-4 py-3">
            <p className="eyebrow">Projects</p>
            <p className="mt-1 text-xl font-semibold leading-none tracking-tight">{projectsTotal}</p>
          </div>
          <div className="card-dark rounded-[10px] border px-4 py-3">
            <p className="eyebrow">Materials</p>
            <p className="mt-1 text-xl font-semibold leading-none tracking-tight">
              {projects.reduce((sum, p) => sum + (p.materialCount ?? 0), 0)}
            </p>
          </div>
        </div>
      )}

      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h2 className="flex items-center gap-2 text-lg font-semibold">
          <FolderKanban className="h-5 w-5 text-primary" aria-hidden="true" />
          Projects{" "}
          <span className="font-normal text-muted-foreground">
            {listFresh ? `(${projectsTotal})` : ""}
          </span>
        </h2>
        <div className="relative w-full max-w-xs">
          <label htmlFor="space-project-search" className="sr-only">
            Search projects in this space
          </label>
          <Search
            className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden="true"
          />
          <Input
            id="space-project-search"
            placeholder="Search projects…"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            className="pl-9"
          />
        </div>
      </div>

      {!listFresh || (projectsStatus === "loading" && visibleProjects.length === 0) ? (
        <SectionLoading label="Loading projects">
          <SkeletonEntryCards count={3} />
        </SectionLoading>
      ) : null}

      {listFresh && projectsStatus === "ready" && visibleProjects.length === 0 ? (
        <EmptyState
          title="No projects in this space yet."
          description="Create a project to start learning."
          icon={FolderKanban}
        />
      ) : null}

      {visibleProjects.length > 0 ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {visibleProjects.map((p) => (
            <ProjectCard key={p.id} project={p} />
          ))}
        </div>
      ) : null}

      <SpaceFormDialog
        open={editOpen}
        onOpenChange={setEditOpen}
        initial={space}
        onSubmit={handleEdit}
      />
      <ProjectFormDialog
        open={projectDialogOpen}
        onOpenChange={setProjectDialogOpen}
        presetSpaceId={spaceId}
        onSubmit={handleCreateProject}
      />
      <ConfirmDialog
        open={archiveOpen}
        onOpenChange={setArchiveOpen}
        title="Archive this space?"
        description={`"${space.name}" and its projects will be hidden. You can restore them later — nothing is deleted.`}
        confirmLabel="Archive space"
        pending={archiving}
        onConfirm={() => void handleArchive()}
      />
    </PageContainer>
  );
}
