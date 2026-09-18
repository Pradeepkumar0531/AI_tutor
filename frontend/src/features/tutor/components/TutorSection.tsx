import {
  Bot,
  CheckCircle2,
  Loader2,
  Plus,
  Quote,
  SendHorizontal,
  TriangleAlert,
} from "lucide-react";
import * as React from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { SectionLabel, SectionLoading, SkeletonTutorMessage } from "@/components/ui";
import { useTutorStore } from "@/stores/useTutorStore";
import type { TutorMessage } from "@/types";

function pageLabel(c: { page_start: number | null; page_end: number | null }): string {
  if (c.page_start == null && c.page_end == null) return "page unknown";
  if (c.page_end == null || c.page_end === c.page_start) return `Page ${c.page_start}`;
  return `Pages ${c.page_start}–${c.page_end}`;
}

function AssistantBadges({ message }: { message: TutorMessage }) {
  // Flags are app-computed from retrieval accounting (persisted server-side),
  // never parsed out of model prose.
  return (
    <div className="mt-2 flex flex-wrap gap-1">
      {message.grounded ? (
        <Badge tone="success">
          <span className="inline-flex items-center gap-1">
            <CheckCircle2 className="h-3 w-3" aria-hidden="true" />
            Grounded in your materials
          </span>
        </Badge>
      ) : null}
      {message.insufficientEvidence ? (
        <Badge tone="default">
          <span className="inline-flex items-center gap-1">
            <TriangleAlert className="h-3 w-3" aria-hidden="true" />
            Not enough evidence
          </span>
        </Badge>
      ) : null}
    </div>
  );
}

function MessageBubble({ message }: { message: TutorMessage }) {
  const isUser = message.role === "USER";
  return (
    <div className={isUser ? "flex justify-end" : "flex justify-start"}>
      <div
        className={
          isUser
            ? "max-w-[85%] rounded-[10px] bg-primary px-3.5 py-2.5 text-sm leading-relaxed text-primary-foreground sm:max-w-[75%]"
            : "max-w-[85%] rounded-[10px] border bg-card px-3.5 py-2.5 text-sm leading-relaxed sm:max-w-[75%]"
        }
      >
        <p className="whitespace-pre-wrap">{message.content}</p>
        {!isUser ? <AssistantBadges message={message} /> : null}
        {!isUser && message.citations.length > 0 ? (
          <ul className="mt-2.5 space-y-1.5 border-t pt-2.5">
            <li className="flex items-center gap-1 text-[11px] font-semibold uppercase tracking-[0.1em] text-muted-foreground">
              <Quote className="h-3 w-3" aria-hidden="true" />
              Sources
            </li>
            {message.citations.map((c) => (
              <li
                key={c.chunk_id}
                className="rounded-md border bg-secondary/60 px-2 py-1.5 text-xs leading-relaxed"
              >
                <span className="font-medium">
                  {c.label || `${c.material_name} — ${pageLabel(c)}`}
                </span>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </div>
  );
}

export function TutorSection({ projectId }: { projectId: string }) {
  const conversations = useTutorStore((s) => s.conversations);
  const conversationsState = useTutorStore((s) => s.conversationsState);
  const activeId = useTutorStore((s) => s.activeId);
  const messages = useTutorStore((s) => s.messages);
  const messagesState = useTutorStore((s) => s.messagesState);
  const sendState = useTutorStore((s) => s.sendState);
  const error = useTutorStore((s) => s.error);
  const fetchConversations = useTutorStore((s) => s.fetchConversations);
  const createConversation = useTutorStore((s) => s.createConversation);
  const selectConversation = useTutorStore((s) => s.selectConversation);
  const sendMessage = useTutorStore((s) => s.sendMessage);

  const [draft, setDraft] = React.useState("");
  const threadRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    void fetchConversations(projectId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  // Recommendation deep-link (?tutor=Concept): prefill the composer once so
  // the learner can review before sending. Never auto-sends. Reads
  // window.location directly so the section works with or without a Router.
  React.useEffect(() => {
    try {
      const suggested = new URLSearchParams(window.location.search).get("tutor");
      if (suggested && suggested.trim() && !draft) {
        setDraft(`Can you help me understand ${suggested.trim()}?`);
        const url = new URL(window.location.href);
        url.searchParams.delete("tutor");
        window.history.replaceState(null, "", url.toString());
      }
    } catch {
      // Non-browser/test environments without location: composer stays empty.
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  React.useEffect(() => {
    const el = threadRef.current;
    if (el && typeof el.scrollTo === "function") {
      el.scrollTo({ top: el.scrollHeight });
    }
  }, [messages.length, sendState]);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (draft.trim() && sendState !== "sending") {
      void sendMessage(projectId, draft.trim());
      setDraft("");
    }
  };

  return (
    <section aria-labelledby="tutor-heading">
      <SectionLabel id="tutor-heading">Tutor</SectionLabel>
      <Card className="mt-2">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between gap-2">
            <CardTitle className="flex min-w-0 items-center gap-2.5 text-[15px]">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[hsl(var(--primary)/0.08)] text-primary">
                <Bot className="h-4 w-4" aria-hidden="true" />
              </span>
              <span className="truncate">
                {conversations.length > 0 && activeId
                  ? conversations.find((c) => c.id === activeId)?.title || "Conversation"
                  : "Tutor"}
              </span>
            </CardTitle>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => void createConversation(projectId)}
            >
              <Plus className="h-4 w-4" aria-hidden="true" />
              New conversation
            </Button>
          </div>
          <p className="mt-2 rounded-lg border bg-secondary/60 px-3 py-2 text-xs leading-relaxed text-muted-foreground">
            Grounded in this project&apos;s materials. Answers cite the exact source — when evidence
            is missing, the tutor says so instead of guessing.
          </p>
        </CardHeader>
        <CardContent className="space-y-4">
          {conversationsState === "loading" && conversations.length === 0 ? (
            <SectionLoading label="Loading conversations">
              <div className="flex flex-wrap gap-1.5" aria-hidden="true">
                <div className="skel h-8 w-28 rounded-lg" />
                <div className="skel h-8 w-24 rounded-lg" />
              </div>
              <SkeletonTutorMessage />
            </SectionLoading>
          ) : null}
          {conversationsState === "error" ? (
            <ErrorState
              title="Could not load tutor"
              description={error ?? undefined}
              onRetry={() => void fetchConversations(projectId)}
            />
          ) : null}

          {conversations.length > 1 ? (
            <div className="flex flex-wrap gap-1" role="listbox" aria-label="Conversations">
              {conversations.map((c, i) => (
                <Button
                  key={c.id}
                  type="button"
                  variant={c.id === activeId ? "default" : "outline"}
                  size="sm"
                  role="option"
                  aria-selected={c.id === activeId}
                  onClick={() => void selectConversation(projectId, c.id)}
                >
                  {c.title || `Conversation ${conversations.length - i}`}
                </Button>
              ))}
            </div>
          ) : null}

          {messagesState === "loading" && messages.length === 0 ? (
            <SectionLoading label="Loading messages">
              <SkeletonTutorMessage />
            </SectionLoading>
          ) : null}
          {messagesState === "error" ? (
            <ErrorState
              title="Could not load messages"
              description={error ?? undefined}
              onRetry={() =>
                activeId
                  ? void selectConversation(projectId, activeId)
                  : void fetchConversations(projectId)
              }
            />
          ) : null}

          {messagesState === "ready" && messages.length === 0 ? (
            <EmptyState
              title="Ask about your materials."
              description="Grounded answers cite the exact material and page. When evidence is missing, the tutor says so instead of guessing."
              icon={Bot}
            />
          ) : null}

          {messages.length > 0 || sendState === "sending" ? (
            <div ref={threadRef} className="max-h-96 space-y-3 overflow-y-auto" aria-live="polite">
              {messages.map((m) => (
                <MessageBubble key={m.id} message={m} />
              ))}
              {sendState === "sending" ? (
                <SectionLoading label="Tutor is thinking">
                  <SkeletonTutorMessage thinking />
                </SectionLoading>
              ) : null}
            </div>
          ) : null}

          {sendState === "error" ? (
            <ErrorState title="Message failed" description={error ?? undefined} />
          ) : null}

          <form onSubmit={submit} className="sticky bottom-0 flex gap-2 border-t bg-card pt-3">
            <Input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="Ask the tutor…"
              aria-label="Ask the tutor"
              disabled={sendState === "sending" || !activeId}
              className="min-h-10"
            />
            <Button type="submit" disabled={sendState === "sending" || !draft.trim() || !activeId}>
              {sendState === "sending" ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              ) : (
                <SendHorizontal className="h-4 w-4" aria-hidden="true" />
              )}
              {sendState === "sending" ? "Sending…" : "Send"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </section>
  );
}
