import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import AsyncBoundary from "../components/ui/AsyncBoundary";
import StatusBadge from "../components/ui/StatusBadge";
import JobProgress from "../components/ui/JobProgress";

describe("AsyncBoundary", () => {
  it("shows the loading skeleton while loading", () => {
    const { container } = render(
      <AsyncBoundary loading empty={false} skeleton="grid" loadingText="Loading…">
        <p>content</p>
      </AsyncBoundary>,
    );
    expect(container.querySelector(".skeleton-grid")).toBeInTheDocument();
    expect(screen.queryByText("content")).not.toBeInTheDocument();
  });

  it("shows the empty state when loaded and empty", () => {
    render(
      <AsyncBoundary loading={false} empty skeleton="grid" loadingText="Loading…" emptyState={<p>Nothing here</p>}>
        <p>content</p>
      </AsyncBoundary>,
    );
    expect(screen.getByText("Nothing here")).toBeInTheDocument();
    expect(screen.queryByText("content")).not.toBeInTheDocument();
  });

  it("renders children when loaded with data", () => {
    render(
      <AsyncBoundary loading={false} empty={false} loadingText="Loading…">
        <p>content</p>
      </AsyncBoundary>,
    );
    expect(screen.getByText("content")).toBeInTheDocument();
  });

  it("shows error with retry", () => {
    const onRetry = vi.fn();
    render(
      <AsyncBoundary loading={false} empty={false} loadingText="Loading…" error="boom" onRetry={onRetry}>
        <p>content</p>
      </AsyncBoundary>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalledOnce();
    expect(screen.getByRole("alert")).toHaveTextContent("boom");
  });
});

describe("StatusBadge", () => {
  it("maps statuses to tones", () => {
    const { container } = render(<StatusBadge status="approved" />);
    expect(container.querySelector(".status-badge.ok")).toBeInTheDocument();
  });

  it("uses the label when provided", () => {
    render(<StatusBadge status="failed" label="Failed" />);
    expect(screen.getByText("Failed")).toBeInTheDocument();
  });
});

describe("JobProgress", () => {
  it("clamps percent and exposes ARIA values", () => {
    render(<JobProgress percent={140} label="job #1" />);
    const bar = screen.getByRole("progressbar", { name: "job #1" });
    expect(bar).toHaveAttribute("aria-valuenow", "100");
    expect(bar.querySelector("i")).toHaveStyle({ width: "100%" });
  });
});
