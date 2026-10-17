import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { I18nProvider } from "../i18n";

const { JOB } = vi.hoisted(() => ({ JOB: {
  id: "job-1",
  character_id: "c1",
  lora_id: "l1",
  name: "nikita_qwen_fp8",
  status: "failed",
  family: "qwen-image",
  progress: null,
  error: "checkpoint not found",
  error_info: {
    code: "checkpoint_missing",
    summary: "The base checkpoint for this family is missing.",
    remediation: "Download the checkpoint or pick another family.",
    technical_details: "FileNotFoundError: qwen_image_2512_bf16.safetensors",
  },
  created_at: "2026-10-14T10:00:00Z",
  updated_at: "2026-10-14T10:05:00Z",
} }));

vi.mock("../api", () => {
  const api = {
    getCharacters: vi.fn().mockResolvedValue([{ id: "c1", name: "Nikita", version: 1, image_style: "real" }]),
    getCheckpoints: vi.fn().mockResolvedValue({ checkpoints: [] }),
    getCharacterLoras: vi.fn().mockResolvedValue([]),
    getTrainingJobs: vi.fn().mockResolvedValue([JOB]),
    getDatasets: vi.fn().mockResolvedValue([]),
    getPoses: vi.fn().mockResolvedValue([]),
    getJobSummary: vi.fn().mockResolvedValue({ active: [], failed: [], active_count: 0, failed_count: 0 }),
    getIdentityRuns: vi.fn().mockResolvedValue([]),
    interruptGeneration: vi.fn(),
  };
  return { default: api, api };
});

import LoraPlayground from "../components/LoraPlayground";

function renderPage() {
  return render(
    <I18nProvider>
      <MemoryRouter>
        <LoraPlayground onLogout={() => {}} />
      </MemoryRouter>
    </I18nProvider>,
  );
}

describe("LoraPlayground structured errors", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders summary, remediation and a model-management link for checkpoint_missing", async () => {
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /Training/ }));
    await waitFor(() => expect(screen.getByText("The base checkpoint for this family is missing.")).toBeInTheDocument());
    expect(screen.getByText("Download the checkpoint or pick another family.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open model management (Home)" })).toBeInTheDocument();
    expect(screen.getByText("nikita_qwen_fp8")).toBeInTheDocument();
  });

  it("hides the raw log path behind a details disclosure", async () => {
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /Training/ }));
    await waitFor(() => expect(screen.getByText("Technical details")).toBeInTheDocument());
    expect(screen.getByText(/FileNotFoundError/)).toBeInTheDocument();
  });
});

import { resetLoraWorkspaceState } from "../hooks/useLoraWorkspaceState";
import { api } from "../api";

const TWO_CHARACTERS = [
  { id: "c1", name: "Nikita", version: 1, image_style: "real" },
  { id: "c2", name: "Akula", version: 1, image_style: "real" },
];

describe("LoraPlayground workspace persistence", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    resetLoraWorkspaceState();
    vi.mocked(api.getCharacters).mockResolvedValue(TWO_CHARACTERS as never);
  });

  it("restores character and stage after a route switch (unmount/remount)", async () => {
    const first = renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /Akula/ }));
    fireEvent.click(screen.getByRole("button", { name: /LoRA dataset/ }));
    await waitFor(() => expect(screen.getByRole("button", { name: /LoRA dataset/ })).toHaveAttribute("aria-current", "step"));
    first.unmount();

    renderPage();
    const datasetStep = await screen.findByRole("button", { name: /LoRA dataset/ });
    await waitFor(() => expect(datasetStep).toHaveAttribute("aria-current", "step"));
    const akula = screen.getByRole("button", { name: /Akula/ });
    await waitFor(() => expect(akula.className).toContain("selected"));
  });

  it("restores the saved workspace after a reload (sessionStorage)", async () => {
    const first = renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /Akula/ }));
    fireEvent.click(screen.getByRole("button", { name: /Training/ }));
    await waitFor(() => expect(screen.getByRole("button", { name: /Training/ })).toHaveAttribute("aria-current", "step"));
    first.unmount();

    const saved = window.sessionStorage.getItem("lora_workspace_v1");
    expect(saved).toContain('"characterId":"c2"');
    resetLoraWorkspaceState();
    window.sessionStorage.setItem("lora_workspace_v1", saved || "");

    renderPage();
    const trainingStep = await screen.findByRole("button", { name: /Training/ });
    await waitFor(() => expect(trainingStep).toHaveAttribute("aria-current", "step"));
    await waitFor(() => expect(screen.getByRole("button", { name: /Akula/ }).className).toContain("selected"));
  });

  it("falls back to the first character when the saved one no longer exists", async () => {
    window.sessionStorage.setItem("lora_workspace_v1", JSON.stringify({
      version: 1,
      state: { characterId: "deleted", stage: "dataset", scrollTop: 0, guideOpen: false, updatedAt: 1 },
    }));
    renderPage();
    const nikita = await screen.findByRole("button", { name: /Nikita/ });
    await waitFor(() => expect(nikita.className).toContain("selected"));
    expect(screen.getByRole("button", { name: /LoRA dataset/ })).toHaveAttribute("aria-current", "step");
    expect(window.sessionStorage.getItem("lora_workspace_v1")).toContain('"characterId":"c1"');
  });
});
