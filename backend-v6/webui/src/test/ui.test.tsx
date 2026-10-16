import { describe, expect, it, vi } from "vitest";
import { useState } from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import AsyncBoundary from "../components/ui/AsyncBoundary";
import StatusBadge from "../components/ui/StatusBadge";
import JobProgress from "../components/ui/JobProgress";
import InspectorDrawer from "../components/ui/InspectorDrawer";

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

describe("InspectorDrawer", () => {
  it("closes on Escape and restores focus to the trigger", async () => {
    function Harness() {
      const [open, setOpen] = useState(false);
      return <>
        <button onClick={() => setOpen(true)}>Open panel</button>
        <InspectorDrawer open={open} onClose={() => setOpen(false)} title="Generator" closeLabel="Close">content</InspectorDrawer>
      </>;
    }
    render(<Harness />);
    const trigger = screen.getByRole("button", { name: "Open panel" });
    trigger.focus();
    fireEvent.click(trigger);
    expect(screen.getByRole("dialog", { name: "Generator" })).toBeInTheDocument();
    fireEvent.keyDown(window, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    await waitFor(() => expect(document.activeElement).toBe(trigger));
  });

  it("does not render when closed", () => {
    render(<InspectorDrawer open={false} onClose={() => {}} title="Hidden" closeLabel="Close">x</InspectorDrawer>);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
