import * as React from "react";
import { Loader2, Plus, TriangleAlert } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { toApiError } from "@/api/client";
import { useSpacesStore } from "@/stores/useSpacesStore";
import type { Project } from "@/types";

export interface ProjectFormValues {
  spaceId: string;
  name: string;
  description: string;
  learningGoal: string;
}

const DIFFICULTIES = ["", "EASY", "MEDIUM", "HARD"] as const;

export function ProjectFormDialog({
  open,
  onOpenChange,
  initial,
  presetSpaceId,
  onSubmit,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  initial?: Project | null;
  presetSpaceId?: string | null;
  onSubmit: (values: ProjectFormValues & { difficulty?: string }) => Promise<void>;
}) {
  const spaces = useSpacesStore((s) => s.items);
  const [spaceId, setSpaceId] = React.useState(initial?.spaceId ?? presetSpaceId ?? "");
  const [name, setName] = React.useState(initial?.name ?? "");
  const [description, setDescription] = React.useState(initial?.description ?? "");
  const [learningGoal, setLearningGoal] = React.useState(initial?.learningGoal ?? "");
  const [difficulty, setDifficulty] = React.useState(initial?.difficulty ?? "");
  const [pending, setPending] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (open) {
      setSpaceId(initial?.spaceId ?? presetSpaceId ?? "");
      setName(initial?.name ?? "");
      setDescription(initial?.description ?? "");
      setLearningGoal(initial?.learningGoal ?? "");
      setDifficulty(initial?.difficulty ?? "");
      setError(null);
    }
  }, [open, initial, presetSpaceId]);

  const valid = spaceId !== "" && name.trim().length > 0;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (pending || !valid) return;
    setPending(true);
    setError(null);
    try {
      await onSubmit({
        spaceId,
        name: name.trim(),
        description: description.trim(),
        learningGoal: learningGoal.trim(),
        difficulty: difficulty || undefined,
      });
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
          <DialogTitle>{initial ? "Edit project" : "New project"}</DialogTitle>
          <DialogDescription>
            {initial
              ? "Update this project's metadata."
              : "Projects live inside a space and hold all learning materials."}
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="mt-4 flex flex-col gap-4">
          {!initial ? (
            <div className="flex flex-col gap-1.5">
              <label htmlFor="project-space" className="text-sm font-medium">
                Space
              </label>
              <select
                id="project-space"
                value={spaceId}
                onChange={(e) => setSpaceId(e.target.value)}
                required
                className="h-10 w-full rounded-lg border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <option value="" disabled>
                  Select a space
                </option>
                {spaces.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
            </div>
          ) : null}
          <div className="flex flex-col gap-1.5">
            <label htmlFor="project-name" className="text-sm font-medium">
              Name
            </label>
            <Input
              id="project-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Operating Systems"
              maxLength={160}
              required
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label htmlFor="project-description" className="text-sm font-medium">
              Description <span className="font-normal text-muted-foreground">(optional)</span>
            </label>
            <Textarea
              id="project-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="What will you learn?"
              rows={3}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label htmlFor="project-goal" className="text-sm font-medium">
              Learning goal <span className="font-normal text-muted-foreground">(optional)</span>
            </label>
            <Input
              id="project-goal"
              value={learningGoal}
              onChange={(e) => setLearningGoal(e.target.value)}
              placeholder="e.g. Understand process scheduling"
            />
          </div>
          {initial ? (
            <div className="flex flex-col gap-1.5">
              <label htmlFor="project-difficulty" className="text-sm font-medium">
                Difficulty <span className="font-normal text-muted-foreground">(optional)</span>
              </label>
              <select
                id="project-difficulty"
                value={difficulty}
                onChange={(e) => setDifficulty(e.target.value)}
                className="h-10 w-full rounded-lg border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <option value="">Not set</option>
                {DIFFICULTIES.filter(Boolean).map((d) => (
                  <option key={d} value={d}>
                    {d.charAt(0) + d.slice(1).toLowerCase()}
                  </option>
                ))}
              </select>
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
            <Button type="submit" disabled={pending || !valid}>
              {pending ? (
                <span className="inline-flex items-center gap-2">
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                  Saving…
                </span>
              ) : initial ? (
                "Save changes"
              ) : (
                <span className="inline-flex items-center gap-2">
                  <Plus className="h-4 w-4" aria-hidden="true" />
                  Create project
                </span>
              )}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
