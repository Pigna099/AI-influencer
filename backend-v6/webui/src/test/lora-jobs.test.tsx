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
