import * as React from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  Archive,
  ArrowLeft,
  Cpu,
  Database,
  FileText,
  Hash,
  Image as ImageIcon,
  Layers,
  Loader2,
  RotateCcw,
  TriangleAlert,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";

import { toApiError } from "@/api/client";
import { knowledgeApi } from "@/api/knowledge";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PageContainer, PageHeader } from "@/components/layout/PageHeader";
import { EmptyState, ErrorState } from "@/components/ui/states";
import {
  SectionLabel,
  SectionLoading,
  SkeletonHeading,
  SkeletonList,
  SkeletonText,
} from "@/components/ui";
import { useToast } from "@/components/ui/toast";
import { DocumentImagesSection } from "@/features/materials/components/DocumentImagesSection";
import { MaterialStatusBadge } from "@/features/materials/components/MaterialStatusBadge";
import { PdfViewer } from "@/features/materials/components/PdfViewer";
import { useMaterialsStore } from "@/stores/useMaterialsStore";
import { useProjectsStore } from "@/stores/useProjectsStore";

const CHUNKS_PAGE_SIZE = 10;

export function MaterialDetailPage() {
  const { projectId, materialId } = useParams<{ projectId: string; materialId: string }>();
  const navigate = useNavigate();
  const { push } = useToast();

  const detail = useMaterialsStore((s) => s.current);
  const error = useMaterialsStore((s) => s.error);
  const refreshOne = useMaterialsStore((s) => s.refreshOne);
  const reprocess = useMaterialsStore((s) => s.reprocess);
  const archive = useMaterialsStore((s) => s.archive);
  const chunks = useMaterialsStore((s) => s.chunks);
  const chunksTotal = useMaterialsStore((s) => s.chunksTotal);
  const chunksPage = useMaterialsStore((s) => s.chunksPage);
  const fetchChunks = useMaterialsStore((s) => s.fetchChunks);
  const fetchProject = useProjectsStore((s) => s.fetchOne);
  const project = useProjectsStore((s) => s.current);

  const [loading, setLoading] = React.useState(true);
  const [retrying, setRetrying] = React.useState(false);
  const [knowledgeRetrying, setKnowledgeRetrying] = React.useState(false);
  const [archiveOpen, setArchiveOpen] = React.useState(false);
  const [archiving, setArchiving] = React.useState(false);
  const [chunksLoading, setChunksLoading] = React.useState(false);

  React.useEffect(() => {
    if (!projectId || !materialId) return;
    setLoading(true);
    void refreshOne(projectId, materialId).finally(() => setLoading(false));
    void fetchProject(projectId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, materialId]);

  React.useEffect(() => {
    if (!projectId || !materialId || detail?.status !== "READY") return;
    setChunksLoading(true);
    void fetchChunks(projectId, materialId, 1).finally(() => setChunksLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, materialId, detail?.status]);

  const knowledge = detail?.knowledge ?? null;
  // Material READY means extraction finished; Tutor search needs embeddings
  // too. While that second stage is non-terminal, re-read the (real) detail
  // until it settles — the same visibility-aware pattern as material
  // polling, and it stops on READY/FAILED.
  const knowledgePending =
    detail?.status === "READY" &&
    knowledge !== null &&
    (knowledge.status === "PENDING" || knowledge.status === "PROCESSING");
  const knowledgeFailed = detail?.status === "READY" && knowledge?.status === "FAILED";

  React.useEffect(() => {
    if (!projectId || !materialId || !knowledgePending) return;
    const timer = setInterval(() => {
      if (document.visibilityState !== "hidden") void refreshOne(projectId, materialId);
    }, 4000);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, materialId, knowledgePending]);

  if (!projectId || !materialId) {
    return (
      <PageContainer>
        <ErrorState title="Material not found" description="This material does not exist." />
      </PageContainer>
    );
  }

  if (loading && !detail) {
    return (
      <PageContainer>
        <SectionLoading label="Loading material" className="flex flex-col gap-4">
          <div>
            <SectionLabel>Material</SectionLabel>
            <SkeletonHeading className="mt-1 w-64" />
            <SkeletonText lines={1} className="mt-2 max-w-md" />
          </div>
          <SkeletonList rows={2} />
        </SectionLoading>
      </PageContainer>
    );
  }

  if (!detail) {
    return (
      <PageContainer>
        <ErrorState
          title="Material not found"
          description={error ?? "This material does not exist or you cannot access it."}
        />
        <p className="mt-4 text-sm">
          <Link
            to={`/projects/${projectId}`}
            className="inline-flex items-center gap-1.5 font-medium text-primary hover:underline"
          >
            <ArrowLeft className="h-4 w-4" aria-hidden="true" />
            Back to project
          </Link>
        </p>
      </PageContainer>
    );
  }

  async function handleRetry() {
    setRetrying(true);
    try {
      await reprocess(projectId as string, materialId as string);
      push("Reprocessing started.");
    } catch (e) {
      push(`Could not start reprocessing: ${toApiError(e).message}`);
    } finally {
      setRetrying(false);
    }
  }

  async function handleKnowledgeRetry() {
    setKnowledgeRetrying(true);
    try {
      await knowledgeApi.reprocess(projectId as string, materialId as string);
      push("Tutor search preparation restarted.");
      await refreshOne(projectId as string, materialId as string);
    } catch (e) {
      push(`Could not restart preparation: ${toApiError(e).message}`);
    } finally {
      setKnowledgeRetrying(false);
    }
  }

  async function handleArchive() {
    setArchiving(true);
    try {
      await archive(projectId as string, materialId as string);
      push("Material archived.");
      navigate(`/projects/${projectId}`);
    } catch (e) {
      push(`Could not archive material: ${toApiError(e).message}`);
    } finally {
      setArchiving(false);
      setArchiveOpen(false);
    }
  }

  function gotoChunksPage(page: number) {
    setChunksLoading(true);
    void fetchChunks(projectId as string, materialId as string, page).finally(() =>
      setChunksLoading(false),
    );
  }

  const totalPages = Math.max(1, Math.ceil(chunksTotal / CHUNKS_PAGE_SIZE));

  return (
    <PageContainer>
      <PageHeader
        title={detail.name}
        description={detail.originalFilename ?? "PDF material"}
        eyebrow="Material"
        icon={FileText}
        crumbs={[
          { label: "Projects", to: "/projects" },
          { label: project?.name ?? "Project", to: `/projects/${projectId}` },
          { label: detail.name },
        ]}
        actions={
          <>
            {detail.status === "FAILED" ? (
              <Button variant="outline" onClick={() => void handleRetry()} disabled={retrying}>
                {retrying ? (
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                ) : (
                  <RotateCcw className="h-4 w-4" aria-hidden="true" />
                )}
                {retrying ? "Starting…" : "Retry processing"}
              </Button>
            ) : null}
            <Button variant="outline" onClick={() => setArchiveOpen(true)}>
              <Archive className="h-4 w-4" aria-hidden="true" />
              Archive
            </Button>
          </>
        }
      />

      <div className="mb-6 flex flex-wrap items-center gap-x-6 gap-y-1 text-sm text-muted-foreground">
        <MaterialStatusBadge status={detail.status} />
        {detail.document?.pageCount != null ? (
          <span className="inline-flex items-center gap-1.5">
            <FileText className="h-3.5 w-3.5" aria-hidden="true" />
            {detail.document.pageCount} pages
          </span>
        ) : null}
        {detail.chunkCount != null && detail.chunkCount > 0 ? (
          <span className="inline-flex items-center gap-1.5">
            <Layers className="h-3.5 w-3.5" aria-hidden="true" />
            {detail.chunkCount} chunks
          </span>
        ) : null}
        {detail.imageCount != null && detail.imageCount > 0 ? (
          <span className="inline-flex items-center gap-1.5">
            <ImageIcon className="h-3.5 w-3.5" aria-hidden="true" />
            {detail.imageCount} {detail.imageCount === 1 ? "image" : "images"}
          </span>
        ) : null}
        {detail.document?.extractionMethod ? (
          <span className="inline-flex items-center gap-1.5">
            <Cpu className="h-3.5 w-3.5" aria-hidden="true" />
            via {detail.document.extractionMethod.toLowerCase()}
          </span>
        ) : null}
        {detail.knowledge ? (
          <span className="inline-flex items-center gap-1.5">
            <Database className="h-3.5 w-3.5" aria-hidden="true" />
            {detail.knowledge.status === "READY"
              ? `Ready for Tutor search (${detail.knowledge.embedded}/${detail.knowledge.total} chunks embedded)`
              : `Knowledge: ${detail.knowledge.status.toLowerCase()} (${detail.knowledge.embedded}/
              ${detail.knowledge.total} chunks embedded)`}
          </span>
        ) : null}
      </div>

      {detail.status === "FAILED" ? (
        <Card variant="light" className="mb-4">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <TriangleAlert className="h-5 w-5 text-destructive" aria-hidden="true" />
              Processing failed
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              {detail.processingError ?? "Processing failed for an unknown reason."}
            </p>
          </CardContent>
        </Card>
      ) : null}

      {knowledgePending ? (
        <Card variant="light" className="mb-4">
          <CardContent className="flex items-start gap-2.5 pt-6">
            <Loader2
              className="mt-0.5 h-4 w-4 shrink-0 animate-spin text-primary"
              aria-hidden="true"
            />
            <div>
              <p className="text-sm font-medium">Preparing for Tutor search</p>
              <p className="mt-1 text-sm text-muted-foreground" role="status">
                Your material is ready, but we&apos;re still preparing it for Tutor search.
                {knowledge && knowledge.total > 0
                  ? ` ${knowledge.embedded}/${knowledge.total} chunks embedded.`
                  : ""}{" "}
                This page updates automatically.
              </p>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {knowledgeFailed ? (
        <Card variant="light" className="mb-4 border-destructive/30">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <TriangleAlert className="h-5 w-5 text-destructive" aria-hidden="true" />
              Tutor search preparation failed
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              The PDF itself is ready
              {knowledge && knowledge.total > 0
                ? ` (${knowledge.embedded}/${knowledge.total} chunks embedded)`
                : ""}
              , but preparing it for Tutor search failed, so the tutor may say evidence is missing
              until preparation succeeds.
            </p>
            <Button
              variant="outline"
              onClick={() => void handleKnowledgeRetry()}
              disabled={knowledgeRetrying}
              className="mt-3"
            >
              {knowledgeRetrying ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              ) : (
                <RotateCcw className="h-4 w-4" aria-hidden="true" />
              )}
              {knowledgeRetrying ? "Starting…" : "Retry Tutor search prep"}
            </Button>
          </CardContent>
        </Card>
      ) : null}

      <div className="mb-4">
        <PdfViewer
          projectId={projectId as string}
          materialId={materialId as string}
          status={detail.status}
          title={detail.originalFilename ?? detail.name}
          pageCount={detail.document?.pageCount ?? detail.pageCount}
        />
      </div>

      {detail.status === "READY" && detail.document ? (
        <Card variant="light">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileText className="h-5 w-5 text-primary" aria-hidden="true" />
              Extracted content
            </CardTitle>
          </CardHeader>
          <CardContent>
            {chunksLoading && chunks.length === 0 ? (
              <SectionLoading label="Loading extracted text">
                <SkeletonText lines={4} />
              </SectionLoading>
            ) : chunks.length === 0 ? (
              <EmptyState title="No chunks to show." />
            ) : (
              <>
                <ol className="flex flex-col gap-4">
                  {chunks.map((c) => (
                    <li key={c.id} className="rounded-lg border p-4">
                      <p className="mb-2 flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
                        <Hash className="h-3.5 w-3.5" aria-hidden="true" />
                        Chunk {c.chunkIndex + 1}
                        {c.pageStart != null ? ` · Page ${c.pageStart}` : null}
                        {c.pageEnd != null && c.pageEnd !== c.pageStart ? `–${c.pageEnd}` : null}
                      </p>
                      <p className="whitespace-pre-wrap text-sm">{c.content}</p>
                    </li>
                  ))}
                </ol>
                <div className="mt-4 flex items-center justify-between text-sm text-muted-foreground">
                  <span>
                    Page {chunksPage} of {totalPages} · {chunksTotal}{" "}
                    {chunksTotal === 1 ? "chunk" : "chunks"}
                  </span>
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={chunksPage <= 1 || chunksLoading}
                      onClick={() => gotoChunksPage(chunksPage - 1)}
                    >
                      <ChevronLeft className="h-4 w-4" aria-hidden="true" />
                      Previous
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={chunksPage >= totalPages || chunksLoading}
                      onClick={() => gotoChunksPage(chunksPage + 1)}
                    >
                      Next
                      <ChevronRight className="h-4 w-4" aria-hidden="true" />
                    </Button>
                  </div>
                </div>
              </>
            )}
          </CardContent>
        </Card>
      ) : null}

      {detail.status !== "READY" && detail.status !== "FAILED" ? (
        <Card variant="light">
          <CardContent className="pt-6">
            <EmptyState
              title={detail.status === "QUEUED" ? "Queued for processing." : "Processing…"}
              description="The worker is extracting text and building chunks. This page updates automatically."
            />
          </CardContent>
        </Card>
      ) : null}

      <DocumentImagesSection
        projectId={projectId as string}
        materialId={materialId as string}
        status={detail.status}
      />

      <ConfirmDialog
        open={archiveOpen}
        onOpenChange={setArchiveOpen}
        title="Archive this material?"
        description={`"${detail.name}" and its extracted content will be hidden. Nothing is deleted — you can restore it later.`}
        confirmLabel="Archive material"
        pending={archiving}
        onConfirm={() => void handleArchive()}
      />
    </PageContainer>
  );
}
