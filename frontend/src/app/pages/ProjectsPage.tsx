import { ChevronLeft, ChevronRight, FolderKanban, Plus, Search } from "lucide-react";
import * as React from "react";

import { toApiError } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PageContainer, PageHeader } from "@/components/layout/PageHeader";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { SectionLoading, SkeletonEntryCards } from "@/components/ui";
import { useToast } from "@/components/ui/toast";
import { ProjectCard } from "@/features/projects/components/ProjectCard";
import {
  ProjectFormDialog,
  type ProjectFormValues,
} from "@/features/projects/components/ProjectFormDialog";
import { useProjectsStore } from "@/stores/useProjectsStore";
import { useSpacesStore } from "@/stores/useSpacesStore";

export function ProjectsPage() {
  const items = useProjectsStore((s) => s.items);
  const total = useProjectsStore((s) => s.total);
  const page = useProjectsStore((s) => s.page);
  const pageSize = useProjectsStore((s) => s.pageSize);
  const status = useProjectsStore((s) => s.status);
  const error = useProjectsStore((s) => s.error);
  const fetchProjects = useProjectsStore((s) => s.fetch);
  const createProject = useProjectsStore((s) => s.create);
  const restoreProject = useProjectsStore((s) => s.restore);

  const spaces = useSpacesStore((s) => s.items);
  const fetchSpaces = useSpacesStore((s) => s.fetch);
  const { push } = useToast();

  const [dialogOpen, setDialogOpen] = React.useState(false);
  const [spaceFilter, setSpaceFilter] = React.useState<string>("");
  const [searchInput, setSearchInput] = React.useState("");
  const [search, setSearch] = React.useState("");
  const [showArchived, setShowArchived] = React.useState(false);

  React.useEffect(() => {
    void fetchSpaces({ page: 1 });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  React.useEffect(() => {
    const t = setTimeout(() => setSearch(searchInput), 300);
    return () => clearTimeout(t);
  }, [searchInput]);

  React.useEffect(() => {
    void fetchProjects({
      spaceId: spaceFilter || null,
      page: 1,
      search,
      includeArchived: showArchived,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [spaceFilter, search, showArchived]);

  async function handleCreate(values: ProjectFormValues) {
    try {
      await createProject(values);
      setDialogOpen(false);
      push("Project created.");
    } catch (e) {
      push(`Could not create project: ${toApiError(e).message}`);
      throw e;
    }
  }

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <PageContainer>
      <PageHeader
        title="Projects"
        description="Every project lives in a space and becomes a learning workspace."
        eyebrow="Projects"
        icon={FolderKanban}
        crumbs={[{ label: "Home", to: "/" }, { label: "Projects" }]}
        actions={
          <Button onClick={() => setDialogOpen(true)}>
            <Plus className="h-4 w-4" aria-hidden="true" />
            New Project
          </Button>
        }
      />

      <div className="mb-4 flex max-w-xl flex-col gap-3 sm:flex-row">
        <div className="relative flex-1">
          <label htmlFor="projects-search" className="sr-only">
            Search projects
          </label>
          <Search
            className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden="true"
          />
          <Input
            id="projects-search"
            placeholder="Search projects…"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            className="pl-9"
          />
        </div>
        <div>
          <label htmlFor="projects-space-filter" className="sr-only">
            Filter by space
          </label>
          <select
            id="projects-space-filter"
            value={spaceFilter}
            onChange={(e) => setSpaceFilter(e.target.value)}
            className="h-10 w-full rounded-lg border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:w-48"
          >
            <option value="">All spaces</option>
            {spaces.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
          <label className="flex cursor-pointer items-center gap-2 whitespace-nowrap text-sm text-muted-foreground">
            <input
              type="checkbox"
              checked={showArchived}
              onChange={(e) => setShowArchived(e.target.checked)}
              className="h-4 w-4 accent-primary"
            />
            Show archived
          </label>
        </div>
      </div>

      {status === "loading" && items.length === 0 ? (
        <SectionLoading label="Loading projects">
          <SkeletonEntryCards count={3} />
        </SectionLoading>
      ) : null}

      {status === "error" ? (
        <ErrorState
          title="Could not load projects"
          description={error ?? undefined}
          onRetry={() => void fetchProjects({ spaceId: spaceFilter || null, page, search })}
        />
      ) : null}

      {status === "ready" && total === 0 ? (
        <EmptyState
          title="No projects yet."
          description="Create a project inside one of your spaces to begin."
          icon={FolderKanban}
        />
      ) : null}

      {items.length > 0 ? (
        <>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {items.map((project) => (
              <ProjectCard
                key={project.id}
                project={project}
                onRestore={(id) =>
                  void restoreProject(id).catch((e: unknown) =>
                    push(`Could not restore project: ${toApiError(e).message}`),
                  )
                }
              />
            ))}
          </div>
          <div className="mt-6 flex items-center justify-between text-sm text-muted-foreground">
            <span>
              Page {page} of {totalPages} · {total} {total === 1 ? "project" : "projects"}
            </span>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1 || status === "loading"}
                onClick={() =>
                  void fetchProjects({ spaceId: spaceFilter || null, page: page - 1, search })
                }
              >
                <ChevronLeft className="h-4 w-4" aria-hidden="true" />
                Previous
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= totalPages || status === "loading"}
                onClick={() =>
                  void fetchProjects({ spaceId: spaceFilter || null, page: page + 1, search })
                }
              >
                Next
                <ChevronRight className="h-4 w-4" aria-hidden="true" />
              </Button>
            </div>
          </div>
        </>
      ) : null}

      <ProjectFormDialog open={dialogOpen} onOpenChange={setDialogOpen} onSubmit={handleCreate} />
    </PageContainer>
  );
}
