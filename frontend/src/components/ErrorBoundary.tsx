import { Component, type ErrorInfo, type ReactNode } from "react";
import { Alert, Button } from "./ui";

interface Props {
  children: ReactNode;
  /** Changing this (e.g. the route) clears the error, so navigating away recovers. */
  resetKey?: string;
}

interface State {
  error: Error | null;
}

/** Catches a crash in one page so the menu, freshness line and disclaimer stay usable. */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Page crashed", error, info.componentStack);
  }

  componentDidUpdate(prev: Props) {
    if (this.state.error && prev.resetKey !== this.props.resetKey) this.setState({ error: null });
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;
    return (
      <div className="space-y-3">
        <Alert tone="error">
          <p className="font-medium">This page hit an error and couldn't be shown.</p>
          <p className="mt-1">{error.message || String(error)}</p>
          <p className="mt-1">
            Your data is safe: nothing was changed. Try again, or open another page from the menu. If it keeps happening, the
            browser console has the details.
          </p>
        </Alert>
        <Button variant="secondary" onClick={() => this.setState({ error: null })}>
          Try again
        </Button>
      </div>
    );
  }
}
