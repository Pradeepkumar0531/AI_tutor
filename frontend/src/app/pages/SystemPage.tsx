import * as React from "react";
import { RefreshCw, Server } from "lucide-react";

import { getHealth, getReadiness } from "@/api";
import { API_BASE_URL, toApiError } from "@/api/client";
import { PageContainer, PageHeader } from "@/components/layout/PageHeader";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  ErrorState,
  LoadingState,
} from "@/components/ui";

export function SystemPage() {
  const [health, setHealth] = React.useState<unknown>(null);
  const [readiness, setReadiness] = React.useState<unknown>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(true);

  const run = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [h, r] = await Promise.all([getHealth(), getReadiness()]);
      setHealth(h);
      setReadiness(r);
    } catch (e) {
      setError(toApiError(e).message);
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    void run();
  }, [run]);

  return (
    <PageContainer>
      <PageHeader
        title="System status"
        description="Development-only connectivity check between frontend and backend."
        icon={Server}
        crumbs={[{ label: "Home", to: "/" }, { label: "System" }]}
        actions={
          <Button variant="outline" size="sm" onClick={run}>
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
            Refresh
          </Button>
        }
      />
      <div className="grid gap-4">
        <Card variant="light">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Server className="h-5 w-5 text-primary" aria-hidden="true" />
              API <Badge tone={error ? "danger" : "info"}>{API_BASE_URL}</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? <LoadingState label="Contacting backend…" /> : null}
            {error && !loading ? (
              <ErrorState title="Backend unreachable" description={error} onRetry={run} />
            ) : null}
            {!loading && !error ? (
              <pre className="overflow-auto rounded-lg bg-muted p-4 text-xs">
                {JSON.stringify({ health, readiness }, null, 2)}
              </pre>
            ) : null}
          </CardContent>
        </Card>
      </div>
    </PageContainer>
  );
}
