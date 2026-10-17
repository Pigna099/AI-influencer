import { useCallback, useState } from "react";

export type LoraStage = "character" | "dataset" | "training";

export const LORA_STAGES: LoraStage[] = ["character", "dataset", "training"];

export interface LoraWorkspaceStateV1 {
  characterId: string;
  stage: LoraStage;
  datasetId?: string;
  expandedIdentityRunId?: string;
  expandedLoraId?: string;
  scrollTop: number;
  guideOpen: boolean;
  updatedAt: number;
}

const STORAGE_KEY = "lora_workspace_v1";

const EMPTY: LoraWorkspaceStateV1 = {
  characterId: "",
  stage: "character",
  scrollTop: 0,
  guideOpen: true,
  updatedAt: 0,
};

let memory: LoraWorkspaceStateV1 | null = null;

function storage(): Storage | null {
  try {
    return typeof window === "undefined" ? null : window.sessionStorage;
  } catch {
    return null;
  }
}

function read(): LoraWorkspaceStateV1 {
  if (memory) return memory;
  const store = storage();
  if (store) {
    try {
      const raw = store.getItem(STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw) as { version?: number; state?: Partial<LoraWorkspaceStateV1> };
        if (parsed?.version === 1 && parsed.state && typeof parsed.state === "object") {
          const state = { ...EMPTY, ...parsed.state };
          if (!LORA_STAGES.includes(state.stage)) state.stage = "character";
          if (typeof state.scrollTop !== "number" || !Number.isFinite(state.scrollTop)) state.scrollTop = 0;
          memory = state;
          return memory;
        }
      }
    } catch {
      /* corrupted storage falls back to defaults */
    }
  }
  memory = { ...EMPTY };
  return memory;
}

function write(state: LoraWorkspaceStateV1) {
  memory = state;
  const store = storage();
  if (!store) return;
  try {
    store.setItem(STORAGE_KEY, JSON.stringify({ version: 1, state }));
  } catch {
    /* storage full or unavailable: keep in-memory state */
  }
}

export function readLoraScrollTop(): number {
  return read().scrollTop;
}

export function saveLoraScroll(scrollTop: number) {
  const current = read();
  if (current.scrollTop === scrollTop) return;
  write({ ...current, scrollTop, updatedAt: Date.now() });
}

export function resetLoraWorkspaceState() {
  memory = null;
  storage()?.removeItem(STORAGE_KEY);
}

export function useLoraWorkspaceState() {
  const [workspace, setWorkspace] = useState<LoraWorkspaceStateV1>(read);
  const updateWorkspace = useCallback((patch: Partial<LoraWorkspaceStateV1>) => {
    const next = { ...read(), ...patch, updatedAt: Date.now() };
    write(next);
    setWorkspace(next);
  }, []);
  return { workspace, updateWorkspace };
}
