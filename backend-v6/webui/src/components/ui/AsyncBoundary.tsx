import { ReactNode } from "react";

interface Props {
  loading: boolean;
  empty: boolean;
  skeleton?: "grid" | "list" | "spinner";
  loadingText: string;
  error?: string | null;
  onRetry?: () => void;
  emptyState?: ReactNode;
  children: ReactNode;
}

export default function AsyncBoundary({ loading, empty, skeleton = "spinner", loadingText, error, onRetry, emptyState, children }: Props) {
  if (loading) {
    if (skeleton === "grid") {
      return <div className="skeleton-grid">{Array.from({ length: 8 }).map((_, index) => <div className="skeleton-card" key={index} />)}</div>;
    }
    return <div className="empty-memory" role="status"><span className="spinner" /><p>{loadingText}</p></div>;
  }
  if (error) {
    return <div className="empty-memory" role="alert">
      <p>{error}</p>
      {onRetry && <button type="button" onClick={onRetry}>Retry</button>}
    </div>;
  }
  if (empty) return <>{emptyState ?? <div className="empty-memory"><p>{loadingText}</p></div>}</>;
  return <>{children}</>;
}
