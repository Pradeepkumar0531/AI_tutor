import { Archive, ArrowLeft, FolderKanban, Layers, Pencil, Plus, Search } from "lucide-react";
import * as React from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { toApiError } from "@/api/client";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PageContainer, PageHeader } from "@/components/layout/PageHeader";
import { EmptyState, ErrorState } from "@/components/ui/states";
import {
  SectionLabel,
  SectionLoading,
  SkeletonEntryCards,
  SkeletonHeading,
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

  // Project list with debounced search (also covers the initial load).
  React.useEffect(() => {
    if (!spaceId) return;
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

  return (
    <PageContainer>
      <PageHeader
        title={space.name}
        description={space.description || "No description yet."}
        eyebrow="Space"
        icon={Layers}
        crumbs={[{ label: "Spaces", to: "/spaces" }, { label: space.name }]}
        actions={
          <>
            <Button variant="outline" onClick={() => setEditOpen(true)}>
              <Pencil className="h-4 w-4" aria-hidden="true" />
              Edit space
            </Button>
            <Button variant="outline" onClick={() => setArchiveOpen(true)}>
              <Archive className="h-4 w-4" aria-hidden="true" />
              Archive
            </Button>
            <Button onClick={() => setProjectDialogOpen(true)}>
              <Plus className="h-4 w-4" aria-hidden="true" />
              New Project
            </Button>
          </>
        }
      />

      <div className="mb-6 flex flex-wrap gap-3">
        <div className="rounded-[10px] border bg-card px-4 py-3">
          <p className="eyebrow">Projects</p>
          <p className="mt-1 text-xl font-semibold leading-none tracking-tight">{projectsTotal}</p>
        </div>
        <div className="rounded-[10px] border bg-card px-4 py-3">
          <p className="eyebrow">Materials</p>
          <p className="mt-1 text-xl font-semibold leading-none tracking-tight">
            {projects.reduce((sum, p) => sum + (p.materialCount ?? 0), 0)}
          </p>
        </div>
      </div>

      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h2 className="flex items-center gap-2 text-lg font-semibold">
          <FolderKanban className="h-5 w-5 text-primary" aria-hidden="true" />
          Projects <span className="font-normal text-muted-foreground">({projectsTotal})</span>
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

      {projectsStatus === "loading" && projects.length === 0 ? (
        <SectionLoading label="Loading projects">
          <SkeletonEntryCards count={3} />
        </SectionLoading>
      ) : null}

      {projectsStatus === "ready" && projects.length === 0 ? (
        <EmptyState
          title="No projects in this space yet."
          description="Create a project to start learning."
          icon={FolderKanban}
        />
      ) : null}

      {projects.length > 0 ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {projects.map((p) => (
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
