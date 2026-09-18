import * as React from "react";
import { FileText, FileUp, Loader2, TriangleAlert, Upload } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { toApiError } from "@/api/client";
import { useMaterialsStore } from "@/stores/useMaterialsStore";

const MAX_CLIENT_BYTES = 25 * 1024 * 1024;

export function UploadDialog({
  open,
  onOpenChange,
  onUpload,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onUpload: (file: File, title: string) => Promise<void>;
}) {
  const [file, setFile] = React.useState<File | null>(null);
  const [title, setTitle] = React.useState("");
  const [pending, setPending] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [dragging, setDragging] = React.useState(false);
  const inputRef = React.useRef<HTMLInputElement>(null);
  // Real upload progress lives in the store (updated via Axios callback).
  const progress = useMaterialsStore((s) => s.uploadState.progress);

  React.useEffect(() => {
    if (open) {
      setFile(null);
      setTitle("");
      setPending(false);
      setError(null);
    }
  }, [open]);

  function pickFile(f: File | null) {
    setError(null);
    if (!f) {
      setFile(null);
      return;
    }
    const isPdf = f.type === "application/pdf" || f.name.toLowerCase().endsWith(".pdf");
    if (!isPdf) {
      setFile(null);
      setError("Only PDF files are accepted.");
      return;
    }
    if (f.size === 0) {
      setFile(null);
      setError("The selected file is empty.");
      return;
    }
    if (f.size > MAX_CLIENT_BYTES) {
      setFile(null);
      setError("This file exceeds the 25 MB upload limit.");
      return;
    }
    setFile(f);
  }

  function formatSize(bytes: number): string {
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  // Upload progress comes from the store via the Axios upload callback;
  // this dialog tracks only the request lifecycle.
  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!file || pending) return;
    setPending(true);
    setError(null);
    try {
      await onUpload(file, title);
    } catch (err) {
      setError(toApiError(err).message);
    } finally {
      setPending(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FileUp className="h-5 w-5 text-primary" aria-hidden="true" />
            Upload PDF
          </DialogTitle>
          <DialogDescription>
            The file is stored and processed in the background. You can close this dialog —
            processing continues on the server.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="mt-4 flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <label htmlFor="upload-title" className="text-sm font-medium">
              Title <span className="font-normal text-muted-foreground">(optional)</span>
            </label>
            <Input
              id="upload-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Defaults to the file name"
              maxLength={200}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <span id="upload-file-label" className="text-sm font-medium">
              PDF file
            </span>
            <div
              role="button"
              tabIndex={0}
              aria-labelledby="upload-file-label"
              onClick={() => inputRef.current?.click()}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  inputRef.current?.click();
                }
              }}
              onDragOver={(e) => {
                e.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragging(false);
                pickFile(e.dataTransfer.files?.[0] ?? null);
              }}
              className={`flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-4 py-6 text-center transition-colors ${
                dragging
                  ? "border-primary bg-primary/5"
                  : "border-border bg-muted/30 hover:border-primary/50 hover:bg-muted/50"
              }`}
            >
              <span className="flex h-10 w-10 items-center justify-center rounded-full bg-[hsl(var(--primary)/0.08)] text-primary">
                <FileUp className="h-5 w-5" aria-hidden="true" />
              </span>
              <span className="text-sm">
                <span className="font-semibold text-primary">Click to browse</span>{" "}
                <span className="text-muted-foreground">or drag &amp; drop a PDF here</span>
              </span>
              <span className="text-xs text-muted-foreground">PDF only · up to 25 MB</span>
              <input
                ref={inputRef}
                type="file"
                accept="application/pdf,.pdf"
                aria-labelledby="upload-file-label"
                onChange={(e) => pickFile(e.target.files?.[0] ?? null)}
                className="sr-only"
              />
            </div>
            {file ? (
              <p className="flex items-center gap-1.5 rounded-lg border bg-card px-2.5 py-2 text-xs text-muted-foreground">
                <FileText className="h-3.5 w-3.5 shrink-0 text-primary" aria-hidden="true" />
                <span className="truncate font-medium text-foreground">{file.name}</span>
                <span className="shrink-0">· {formatSize(file.size)}</span>
              </p>
            ) : null}
          </div>
          {pending ? (
            <div
              className="h-2 overflow-hidden rounded bg-muted"
              role="progressbar"
              aria-valuenow={progress}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-label="Upload progress"
            >
              <div className="h-full bg-primary transition-all" style={{ width: `${progress}%` }} />
            </div>
          ) : null}
          {error ? (
            <p role="alert" className="flex items-center gap-1.5 text-sm text-destructive">
              <TriangleAlert className="h-4 w-4 shrink-0" aria-hidden="true" />
              {error}
            </p>
          ) : null}
          <div className="flex justify-end gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={pending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={pending || !file}>
              {pending ? (
                <span className="inline-flex items-center gap-2">
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                  Uploading…
                </span>
              ) : (
                <span className="inline-flex items-center gap-2">
                  <Upload className="h-4 w-4" aria-hidden="true" />
                  Upload
                </span>
              )}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
