import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { I18nProvider } from "../i18n";

const { api } = vi.hoisted(() => {
  const character = { id: "c1", name: "Nikita", version: 1, image_style: "real", avatar_filename: "a.png", avatar_prompt: "identity" };
  return {
    api: {
      getCharacters: vi.fn().mockResolvedValue([character]),
      getCheckpoints: vi.fn().mockResolvedValue({ checkpoints: [{ name: "model.safetensors", family: "real", usable: true }] }),
      getLibrary: vi.fn().mockResolvedValue([]),
      getLoras: vi.fn().mockResolvedValue({ loras: [] }),
      getCharacterLoras: vi.fn().mockResolvedValue([]),
      getPoses: vi.fn().mockResolvedValue([]),
      getPresets: vi.fn().mockResolvedValue([]),
      getCollections: vi.fn().mockResolvedValue([]),
      getDefaults: vi.fn().mockResolvedValue({ chat_model: "", image_checkpoint: "", video_model: "wan" }),
      getVideos: vi.fn().mockResolvedValue([]),
      getJobSummary: vi.fn().mockResolvedValue({ active: [], failed: [], active_count: 0, failed_count: 0 }),
      getDatasetSources: vi.fn().mockResolvedValue([
        { id: "s1", name: "QA Source", kind: "nextcloud", status: "ready", total: 10, imported: 10, classified: 10, images: 10, videos: 0 },
      ]),
      getDatasetImages: vi.fn().mockResolvedValue([]),
      fetchBlob: vi.fn().mockRejectedValue(new Error("no blob in tests")),
    },
  };
});

vi.mock("../api", () => ({ default: api, api }));

import ImagePlayground from "../components/ImagePlayground";
import VideoPlayground from "../components/VideoPlayground";
import DatasetPlayground from "../components/DatasetPlayground";

function renderPage(ui: React.ReactElement) {
  return render(<I18nProvider><MemoryRouter>{ui}</MemoryRouter></I18nProvider>);
}

describe("Images page reachability", () => {
  it("keeps the core actions reachable after the redesign", async () => {
    renderPage(<ImagePlayground onLogout={() => {}} />);
    await waitFor(() => expect(api.getLibrary).toHaveBeenCalled());
    expect(screen.getByRole("button", { name: "Generate" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Grid" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Review" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Trash" })).toBeInTheDocument();
    expect(screen.getByLabelText("Library mode")).toBeInTheDocument();
    expect(screen.getByLabelText("Status")).toBeInTheDocument();
    expect(screen.getAllByLabelText("Style").length).toBeGreaterThan(0);
  });
});

describe("Video page reachability", () => {
  it("keeps source, model cards and generate reachable", async () => {
    renderPage(<VideoPlayground onLogout={() => {}} />);
    await waitFor(() => expect(api.getVideos).toHaveBeenCalled());
    expect(screen.getByRole("button", { name: "Generate video" })).toBeInTheDocument();
    expect(screen.getByRole("radiogroup", { name: "Model" })).toBeInTheDocument();
    expect(screen.getByText("Motion presets")).toBeInTheDocument();
  });
});

describe("Dataset page reachability", () => {
  it("keeps the import and progress areas reachable", async () => {
    renderPage(<DatasetPlayground onLogout={() => {}} />);
    await waitFor(() => expect(api.getDatasetSources).toHaveBeenCalled());
    expect(screen.getByRole("button", { name: /New source/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Classify unclassified" })).toBeInTheDocument();
    // Export lives inside the overflow disclosure: assert it is present in the DOM.
    expect(screen.getByText("Export JSONL")).toBeInTheDocument();
  });
});
