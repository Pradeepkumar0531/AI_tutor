import { Link } from "react-router-dom";
import { ArchiveRestore, Calendar, Layers } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { Space } from "@/types";

export function SpaceCard({
  space,
  onRestore,
}: {
  space: Space;
  onRestore?: (id: string) => void;
}) {
  const count = space.projectCount ?? 0;
  const archived = space.archivedAt !== null;
  return (
    <Link
      to={`/spaces/${space.id}`}
      className="group block rounded-[10px] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      aria-label={`Open space ${space.name}`}
    >
      <Card variant="light" accent className="card-lift h-full group-hover:border-primary/40">
        <CardHeader className="pb-3">
          <div className="flex items-start justify-between gap-2">
            <CardTitle className="flex min-w-0 items-center gap-2.5 text-[15px] line-clamp-1">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[hsl(var(--primary)/0.08)] text-primary">
                <Layers className="h-4 w-4 shrink-0" aria-hidden="true" />
              </span>
              <span className="truncate">{space.name}</span>
            </CardTitle>
            <div className="flex shrink-0 items-center gap-1.5">
              {archived ? <Badge tone="warning">Archived</Badge> : null}
              <Badge>
                {count} {count === 1 ? "project" : "projects"}
              </Badge>
            </div>
          </div>
        </CardHeader>
        <CardContent className="pt-0">
          <p className="line-clamp-2 min-h-10 text-sm leading-relaxed text-muted-foreground">
            {space.description || "No description yet."}
          </p>
          <div className="mt-3 flex items-center justify-between gap-2">
            <p className="font-mono-tech inline-flex items-center gap-1.5 text-[11px] uppercase tracking-[0.08em] text-muted-foreground">
              <Calendar className="h-3 w-3" aria-hidden="true" />
              Updated {new Date(space.updatedAt).toLocaleDateString()}
            </p>
            {archived && onRestore ? (
              <Button
                size="sm"
                variant="outline"
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  onRestore(space.id);
                }}
              >
                <ArchiveRestore className="h-3.5 w-3.5" aria-hidden="true" />
                Restore
              </Button>
            ) : null}
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}
