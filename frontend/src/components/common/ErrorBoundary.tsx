import { Component, type ReactNode } from "react";

import { ErrorState } from "@/components/ui";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error): void {
    console.error("Unhandled UI error", error);
  }

  render(): ReactNode {
    if (this.state.error) {
      // Generic message only: raw error text can carry paths, URLs, or
      // provider details that must never reach the learner's screen.
      return (
        <ErrorState
          title="Something went wrong"
          description="Please try again. If the problem persists, contact support."
          onRetry={() => this.setState({ error: null })}
        />
      );
    }
    return this.props.children;
  }
}
