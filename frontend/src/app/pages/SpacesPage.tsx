import { ChevronLeft, ChevronRight, Layers, Plus, Search, SearchX } from "lucide-react";
import * as React from "react";

import { toApiError } from "@/api/client";
import { useToast } from "@/components/ui/toast";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PageContainer, PageHeader } from "@/components/layout/PageHeader";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { SectionLoading, SkeletonEntryCards } from "@/components/ui";
import { SpaceCard } from "@/features/spaces/components/SpaceCard";
import {
  SpaceFormDialog,
  type SpaceFormValues,
} from "@/features/spaces/components/SpaceFormDialog";
import { useSpacesStore } from "@/stores/useSpacesStore";

function useDebouncedValue(value: string, delayMs: number): string {
  const [debounced, setDebounced] = React.useState(value);
  React.useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(t);
  }, [value, delayMs]);
  return debounced;
}

export function SpacesPage() {
  const items = useSpacesStore((s) => s.items);
  const total = useSpacesStore((s) => s.total);
  const page = useSpacesStore((s) => s.page);
  const pageSize = useSpacesStore((s) => s.pageSize);
  const status = useSpacesStore((s) => s.status);
  const error = useSpacesStore((s) => s.error);
  const fetchSpaces = useSpacesStore((s) => s.fetch);
  const createSpace = useSpacesStore((s) => s.create);
  const restoreSpace = useSpacesStore((s) => s.restore);
  const { push } = useToast();

  const [dialogOpen, setDialogOpen] = React.useState(false);
  const [searchInput, setSearchInput] = React.useState("");
  const [showArchived, setShowArchived] = React.useState(false);
  const search = useDebouncedValue(searchInput, 300);

  React.useEffect(() => {
    void fetchSpaces({ page: 1, search, includeArchived: showArchived });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search, showArchived]);

  async function handleCreate(values: SpaceFormValues) {
    try {
      await createSpace(values);
      setDialogOpen(false);
      push("Space created.");
    } catch (e) {
      push(`Could not create space: ${toApiError(e).message}`);
      throw e;
    }
  }

  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const searching = search.trim().length > 0;

  return (
    <PageContainer>
      <PageHeader
        title="Spaces"
        description="Organize your learning into spaces, then projects."
        eyebrow="Learning areas"
        icon={Layers}
        crumbs={[{ label: "Home", to: "/" }, { label: "Spaces" }]}
        actions={
          <Button onClick={() => setDialogOpen(true)}>
            <Plus className="h-4 w-4" aria-hidden="true" />
            New Space
          </Button>
        }
      />

      <div className="mb-4 flex max-w-xl flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <label htmlFor="spaces-search" className="sr-only">
            Search spaces
          </label>
          <Search
            className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden="true"
          />
          <Input
            id="spaces-search"
            placeholder="Search spaces…"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            className="pl-9"
          />
        </div>
        <label className="flex cursor-pointer items-center gap-2 text-sm text-muted-foreground">
          <input
            type="checkbox"
            checked={showArchived}
            onChange={(e) => setShowArchived(e.target.checked)}
            className="h-4 w-4 accent-primary"
          />
          Show archived
        </label>
      </div>

      {status === "loading" && items.length === 0 ? (
        <SectionLoading label="Loading spaces">
          <SkeletonEntryCards count={3} />
        </SectionLoading>
      ) : null}

      {status === "error" ? (
        <ErrorState
          title="Could not load spaces"
          description={error ?? undefined}
          onRetry={() => void fetchSpaces({ page, search })}
        />
      ) : null}

      {status === "ready" && total === 0 && !searching ? (
        <EmptyState
          title="No learning spaces yet."
          description="Create a space to organize your learning projects."
          icon={Layers}
        />
      ) : null}

      {status === "ready" && total === 0 && searching ? (
        <EmptyState
          title="No spaces match your search."
          description={`Nothing found for "${search}".`}
          icon={SearchX}
        />
      ) : null}

      {items.length > 0 ? (
        <>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {items.map((space) => (
              <SpaceCard
                key={space.id}
                space={space}
                onRestore={(id) =>
                  void restoreSpace(id).catch((e: unknown) =>
                    push(`Could not restore space: ${toApiError(e).message}`),
                  )
                }
              />
            ))}
          </div>
          <div className="mt-6 flex items-center justify-between text-sm text-muted-foreground">
            <span>
              Page {page} of {totalPages} · {total} {total === 1 ? "space" : "spaces"}
            </span>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1 || status === "loading"}
                onClick={() => void fetchSpaces({ page: page - 1, search })}
              >
                <ChevronLeft className="h-4 w-4" aria-hidden="true" />
                Previous
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= totalPages || status === "loading"}
                onClick={() => void fetchSpaces({ page: page + 1, search })}
              >
                Next
                <ChevronRight className="h-4 w-4" aria-hidden="true" />
              </Button>
            </div>
          </div>
        </>
      ) : null}

      <SpaceFormDialog open={dialogOpen} onOpenChange={setDialogOpen} onSubmit={handleCreate} />
    </PageContainer>
  );
}
