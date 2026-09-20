import { BookOpen, CheckCircle2, ChevronDown, Loader2, Quote, Search, XCircle } from "lucide-react";
import * as React from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { SectionLabel, SectionLoading, SkeletonConceptRows, SkeletonText } from "@/components/ui";
import { useFirstVisible } from "@/hooks/useFirstVisible";
import { knowledgeApi } from "@/api/knowledge";
import { toApiError } from "@/api/client";
import { useKnowledgeStore } from "@/stores/useKnowledgeStore";
import { useMaterialsStore } from "@/stores/useMaterialsStore";
import type { Concept } from "@/types";

function StatusBadge({ status }: { status: string }) {
  const tone = status === "READY" ? "success" : status === "FAILED" ? "danger" : "default";
  return (
    <Badge tone={tone}>
      <span className="inline-flex items-center gap-1">
        {status === "READY" ? (
          <CheckCircle2 className="h-3 w-3" aria-hidden="true" />
        ) : status === "FAILED" ? (
          <XCircle className="h-3 w-3" aria-hidden="true" />
        ) : (
          <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />
        )}
        {status}
      </span>
    </Badge>
  );
}

function ConceptCard({ concept }: { concept: Concept }) {
  const [open, setOpen] = React.useState(false);
  // Provenance (linked materials, pages, chunk count) lives on the concept
  // DETAIL endpoint; the list response carries names only. Fetch on first
  // expand so the list stays light and the expander shows real sources.
  const [detail, setDetail] = React.useState<Concept | null>(null);
  const [detailState, setDetailState] = React.useState<"idle" | "loading" | "ready" | "error">(
    "idle",
  );
  const [detailError, setDetailError] = React.useState<string | null>(null);

  function loadDetail() {
    if (detailState === "loading" || detailState === "ready") return;
    setDetailState("loading");
    setDetailError(null);
    knowledgeApi
      .concept(concept.projectId, concept.id)
      .then((d) => {
        setDetail(d);
        setDetailState("ready");
      })
      .catch((e) => {
        setDetailError(toApiError(e).message);
        setDetailState("error");
      });
  }

  function toggle() {
    const next = !open;
    setOpen(next);
    if (next) loadDetail();
  }

  const shown = detail ?? concept;
  return (
    <div className="rounded-lg border p-3">
      <button
        type="button"
        onClick={toggle}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-2 text-left"
      >
        <span className="font-medium">{concept.name}</span>
        <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
          {open ? "Hide" : "Provenance"}
          <ChevronDown
            className={`h-3.5 w-3.5 transition-transform ${open ? "rotate-180" : ""}`}
            aria-hidden="true"
          />
        </span>
      </button>
      {concept.description ? (
        <p className="mt-1 text-sm text-muted-foreground">{concept.description}</p>
      ) : null}
      {open ? (
        <div className="mt-2 text-sm">
          {detailState === "loading" ? (
            <p className="text-muted-foreground" role="status">
              Loading provenance…
            </p>
          ) : detailState === "error" ? (
            <p className="text-muted-foreground">
              Could not load provenance{detailError ? `: ${detailError}` : ""}{" "}
              <button
                type="button"
                onClick={loadDetail}
                className="font-medium text-primary underline-offset-2 hover:underline"
              >
                Retry
              </button>
            </p>
          ) : shown.materials && shown.materials.length > 0 ? (
            <ul className="list-disc pl-5">
              {shown.materials.map((m) => (
                <li key={m.id}>{m.name}</li>
              ))}
            </ul>
          ) : (
            <p className="text-muted-foreground">No linked materials.</p>
          )}
          {detailState === "ready" && shown.pages && shown.pages.length > 0 ? (
            <p className="mt-1 text-xs text-muted-foreground">Pages: {shown.pages.join(", ")}</p>
          ) : null}
          {detailState === "ready" && typeof shown.chunkCount === "number" ? (
            <p className="text-xs text-muted-foreground">Supporting chunks: {shown.chunkCount}</p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

export function KnowledgeSection({ projectId }: { projectId: string }) {
  const status = useKnowledgeStore((s) => s.status);
  const totals = useKnowledgeStore((s) => s.totals);
  const statusState = useKnowledgeStore((s) => s.statusState);
  const concepts = useKnowledgeStore((s) => s.concepts);
  const conceptsTotal = useKnowledgeStore((s) => s.conceptsTotal);
  const conceptsState = useKnowledgeStore((s) => s.conceptsState);
  const search = useKnowledgeStore((s) => s.search);
  const searchState = useKnowledgeStore((s) => s.searchState);
  const error = useKnowledgeStore((s) => s.error);
  const fetchStatus = useKnowledgeStore((s) => s.fetchStatus);
  const fetchConcepts = useKnowledgeStore((s) => s.fetchConcepts);
  const runSearch = useKnowledgeStore((s) => s.runSearch);

  const [query, setQuery] = React.useState("");
  const [sectionRef, visible] = useFirstVisible<HTMLElement>();
  const prevStatus = React.useRef<string | null>(null);
  // Material changes drive knowledge: an upload flips QUEUED→READY and the
  // knowledge job may complete between polls without ever showing PROCESSING.
  const materialsSignature = useMaterialsStore((s) =>
    s.items.map((m) => `${m.id}:${m.status}`).join(","),
  );

  React.useEffect(() => {
    if (!visible) return;
    void fetchStatus(projectId);
    void fetchConcepts(projectId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, visible]);

  React.useEffect(() => {
    if (!visible) return;
    void fetchStatus(projectId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, materialsSignature, visible]);

  // While non-terminal (PENDING or PROCESSING), poll status; when it flips
  // to READY, reload concepts once. PENDING must poll too: a freshly READY
  // material briefly reports PENDING before its knowledge job is claimed,
  // and without polling the UI would sit on PENDING forever. The server is
  // the source of truth — no fake progress is synthesized.
  React.useEffect(() => {
    if (!visible) return;
    if (statusState !== "ready" || !status) return;
    if (status === "PROCESSING" || status === "PENDING") {
      const timer = setInterval(() => {
        if (document.visibilityState !== "hidden") void fetchStatus(projectId);
      }, 4000);
      prevStatus.current = status;
      return () => clearInterval(timer);
    }
    if (status === "READY" && prevStatus.current !== "READY") {
      void fetchConcepts(projectId);
    }
    prevStatus.current = status;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status, statusState, projectId]);

  const submitSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (query.trim()) void runSearch(projectId, query.trim());
  };

  return (
    <section
      aria-labelledby="knowledge-heading"
      id="section-knowledge"
      ref={sectionRef}
      className="scroll-mt-24"
    >
      <SectionLabel id="knowledge-heading">Knowledge</SectionLabel>
      <Card variant="light" className="mt-2">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between gap-2">
            <CardTitle className="flex min-w-0 items-center gap-2.5 text-[15px]">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[hsl(var(--primary)/0.08)] text-primary">
                <BookOpen className="h-4 w-4" aria-hidden="true" />
              </span>
              Concepts
            </CardTitle>
            {status ? <StatusBadge status={status} /> : null}
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {statusState === "loading" && !status ? (
            <SectionLoading label="Loading knowledge status">
              <SkeletonText lines={1} className="max-w-xs" />
              <SkeletonConceptRows rows={2} />
            </SectionLoading>
          ) : null}
          {statusState === "error" ? (
            <ErrorState
              title="Could not load knowledge"
              description={error ?? undefined}
              onRetry={() => void fetchStatus(projectId)}
            />
          ) : null}
          {status && totals ? (
            <p className="text-sm text-muted-foreground">
              {totals.chunks_embedded}/{totals.chunks_total} chunks embedded · {totals.concepts}{" "}
              concepts · {totals.materials_ready} materials ready
            </p>
          ) : null}

          {conceptsState === "loading" && concepts.length === 0 ? (
            <SectionLoading label="Loading concepts">
              <SkeletonConceptRows rows={3} />
            </SectionLoading>
          ) : null}
          {concepts.length > 0 ? (
            <div className="space-y-2">
              {concepts.map((c) => (
                <ConceptCard key={c.id} concept={c} />
              ))}
              {conceptsTotal > concepts.length ? (
                <p className="text-xs text-muted-foreground">
                  Showing {concepts.length} of {conceptsTotal} concepts.
                </p>
              ) : null}
            </div>
          ) : conceptsState === "ready" ? (
            <EmptyState
              title="No concepts yet."
              description="Concepts appear after project materials finish knowledge processing."
            />
          ) : null}

          <form onSubmit={submitSearch} className="flex gap-2">
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search project knowledge…"
              aria-label="Search project knowledge"
            />
            <Button type="submit" disabled={searchState === "loading" || !query.trim()}>
              <Search className="h-4 w-4" aria-hidden="true" />
              {searchState === "loading" ? "Searching…" : "Search"}
            </Button>
          </form>

          {searchState === "error" ? (
            <ErrorState
              title="Search failed"
              description={error ?? undefined}
              onRetry={() => query.trim() && void runSearch(projectId, query.trim())}
            />
          ) : null}
          {search && searchState === "ready" ? (
            <div className="space-y-2">
              {search.insufficient_evidence ? (
                <EmptyState
                  title="Not enough evidence."
                  description="I couldn't find enough evidence in this project's materials to answer that confidently."
                />
              ) : (
                search.results.map((r) => (
                  <div key={r.chunk_id} className="rounded-lg border p-3">
                    <p className="text-sm">{r.text}</p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {r.material_name} — {r.page_start != null ? `Page ${r.page_start}` : "Page ?"}{" "}
                      · {Math.round(r.similarity * 100)}% match
                    </p>
                  </div>
                ))
              )}
              {search.citations.length > 0 ? (
                <div className="text-xs text-muted-foreground">
                  <p className="flex items-center gap-1 font-medium">
                    <Quote className="h-3.5 w-3.5" aria-hidden="true" />
                    Citations
                  </p>
                  <ul className="list-disc pl-5">
                    {search.citations.map((c) => (
                      <li key={c.chunk_id}>{c.label}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
          ) : null}
        </CardContent>
      </Card>
    </section>
  );
}
