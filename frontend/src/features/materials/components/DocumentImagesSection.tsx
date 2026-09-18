import * as React from "react";
import { Image as ImageIcon, ImageOff } from "lucide-react";

import { materialsApi } from "@/api/materials";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { SectionLoading, SkeletonList } from "@/components/ui";
import { useMaterialsStore } from "@/stores/useMaterialsStore";
import type { DocumentImage } from "@/types";

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function ImageThumbnail({
  projectId,
  materialId,
  image,
}: {
  projectId: string;
  materialId: string;
  image: DocumentImage;
}) {
  const [url, setUrl] = React.useState<string | null>(null);
  const [failed, setFailed] = React.useState(false);

  React.useEffect(() => {
    let alive = true;
    let objectUrl: string | null = null;
    setUrl(null);
    setFailed(false);
    materialsApi
      .imageBlob(projectId, materialId, image.id)
      .then((blob) => {
        if (!alive) return;
        objectUrl = URL.createObjectURL(blob);
        setUrl(objectUrl);
      })
      .catch(() => {
        if (alive) setFailed(true);
      });
    return () => {
      alive = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [projectId, materialId, image.id]);

  if (failed) {
    return (
      <div
        role="img"
        aria-label={`Image ${image.imageIndex + 1} on page ${image.pageNumber} failed to load`}
        className="flex h-32 w-full flex-col items-center justify-center gap-1.5 rounded-md bg-muted text-xs text-muted-foreground"
      >
        <ImageOff className="h-5 w-5" aria-hidden="true" />
        Preview unavailable
      </div>
    );
  }
  if (!url) {
    return (
      <div
        aria-label="Loading image preview"
        className="h-32 w-full animate-pulse rounded-md bg-muted"
      />
    );
  }
  return (
    <img
      src={url}
      alt={`Extracted image ${image.imageIndex + 1} from page ${image.pageNumber}`}
      className="max-h-48 w-full rounded-md border object-contain"
      loading="lazy"
      onError={() => setFailed(true)}
    />
  );
}

export function DocumentImagesSection({
  projectId,
  materialId,
  status,
}: {
  projectId: string;
  materialId: string;
  status: string;
}) {
  const images = useMaterialsStore((s) => s.images);
  const imagesState = useMaterialsStore((s) => s.imagesState);
  const imagesError = useMaterialsStore((s) => s.imagesError);
  const fetchImages = useMaterialsStore((s) => s.fetchImages);

  // (Re)load when the material finishes processing: polling the metadata
  // list too early would permanently show "no images".
  React.useEffect(() => {
    if (status === "READY") void fetchImages(projectId, materialId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, materialId, status]);

  return (
    <Card className="mt-4">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ImageIcon className="h-5 w-5 text-primary" aria-hidden="true" />
          Images
        </CardTitle>
      </CardHeader>
      <CardContent>
        {status !== "READY" ? (
          <p className="text-sm text-muted-foreground">
            {status === "FAILED"
              ? "Processing failed, so no images are available."
              : "Processing… images will appear here once extraction finishes."}
          </p>
        ) : imagesState === "loading" ? (
          <SectionLoading label="Loading images">
            <SkeletonList rows={2} />
          </SectionLoading>
        ) : imagesState === "error" ? (
          <ErrorState
            title="Could not load images"
            description={imagesError ?? undefined}
            onRetry={() => void fetchImages(projectId, materialId)}
          />
        ) : images.length === 0 ? (
          <EmptyState title="No embedded images were detected." icon={ImageOff} />
        ) : (
          <ol className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {images.map((image) => (
              <li key={image.id} className="rounded-lg border p-3">
                <ImageThumbnail projectId={projectId} materialId={materialId} image={image} />
                <p className="mt-2 text-sm font-medium">
                  Page {image.pageNumber} · Image {image.imageIndex + 1}
                </p>
                <p className="text-xs text-muted-foreground">
                  {image.width}×{image.height} · {image.mimeType} · {formatBytes(image.fileSize)}
                </p>
              </li>
            ))}
          </ol>
        )}
      </CardContent>
    </Card>
  );
}
