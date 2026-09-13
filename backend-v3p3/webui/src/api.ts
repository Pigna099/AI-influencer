// API types
export interface ApiError {
  detail: string;
}

export interface OllamaModel {
  name: string;
  size: number;
  family: string;
  parameter_size: string;
  quantization: string;
  capabilities?: string[];
  chat_capable?: boolean;
  kind?: "chat" | "coding" | "embedding";
}

export interface CheckpointInfo {
  name: string;
  family: "real" | "anime" | "pony" | "video";
  usable: boolean;
}

export interface CharacterProfile {
  description: string;
  appearance: string;
  background: string;
  personality_traits: string;
  tone_of_voice: string;
  speech_style: string;
  vocabulary: string;
  likes: string;
  dislikes: string;
  boundaries: string;
  relationship_style: string;
  language: string;
  custom_instructions: string;
}

export interface Character {
  id: string;
  name: string;
  profile: CharacterProfile;
  version: number;
  avatar_filename?: string | null;
  image_checkpoint?: string | null;
  image_style?: "anime" | "real" | null;
  ppv_enabled?: boolean;
  ppv_price_cents?: number;
  created_at: string;
}

export interface Conversation {
  fan_id?: string | null;
  memory_status?: string;
  images_enabled?: boolean;
  greeting_error?: string;
  id: string;
  character_id: string;
  title: string;
  model: string;
  character_snapshot: {
    id: string;
    name: string;
    profile: CharacterProfile;
    version: number;
  };
  created_at: string;
  updated_at: string | null;
}

export interface ChatImage {
  id: string;
  message_id: string;
  conversation_id: string;
  prompt: string;
  seed: number;
  nsfw: boolean;
  price_cents: number;
  unlocked: boolean;
  unlocked_at: string | null;
  created_at: string;
}

export interface Message {
  id: string;
  conversation_id: string;
  role: "user" | "assistant";
  content: string;
  model: string | null;
  ollama_metrics: {
    request_seconds?: number;
    kind?: string;
    done_reason?: string;
    guarded?: boolean;
    guard_reason?: string;
    photo_requested?: boolean;
    image_sent?: boolean;
    image_error?: string;
    image_seconds?: number;
    total_duration: number | null;
    load_duration: number | null;
    prompt_eval_count: number | null;
    eval_count: number | null;
    eval_duration: number | null;
  } | null;
  images?: ChatImage[];
  created_at: string;
}

export interface Memory {
  id: string;
  character_id: string;
  content: string;
  category: string;
  importance: number;
  embedding_model: string;
  source_message_id: string | null;
  active: boolean;
  created_at: string;
  last_retrieved_at: string | null;
}

export interface LibraryImage {
  id: string;
  character_id: string;
  filename: string;
  caption: string;
  tags: string[];
  prompt: string;
  negative_prompt: string;
  checkpoint: string | null;
  loras: { name: string; weight: number }[];
  seed: number;
  style: "anime" | "real";
  status: "draft" | "approved" | "rejected";
  rating: number;
  source: string;
  used_count: number;
  created_at: string;
  updated_at: string | null;
}

export interface LibraryGenerateInput {
  prompt: string;
  negative?: string;
  style?: "anime" | "real";
  checkpoint?: string;
  loras: { name: string; weight: number }[];
  count: number;
  seed?: number;
  classify: boolean;
}

export interface DatasetSource {
  id: string;
  name: string;
  kind: "telegram" | "urls" | "folder";
  reference: string;
  character_id: string | null;
  status: string;
  total: number;
  imported: number;
  classified: number;
  images: number;
  videos: number;
  error: string | null;
  created_at: string;
  updated_at: string | null;
}

export interface DatasetImage {
  id: string;
  source_id: string;
  filename: string;
  kind: "image" | "video";
  has_thumb: boolean;
  width: number;
  height: number;
  status: "pending" | "ready" | "failed" | "blocked";
  caption: string;
  details: Record<string, string>;
  tags: string[];
  created_at: string;
  updated_at: string | null;
}

export interface GpuProcess {
  pid: number;
  name: string;
  kind: "ollama" | "comfyui" | "process";
  vram: number;
}

export interface GpuStatus {
  index: number;
  name: string;
  memory_total: number;
  memory_used: number;
  memory_free: number;
  utilization: number;
  memory_utilization: number;
  power_watts: number | null;
  power_limit: number | null;
  temperature: number | null;
  processes: GpuProcess[];
}

export interface GpuReport {
  available: boolean;
  error?: string;
  gpus: GpuStatus[];
}

export interface HealthStatus {
  status: string;
  text_provider: string;
  image_provider: string;
  fanvue_enabled: boolean;
}

// API Client
export const getApiBaseUrl = (): string => {
  // Vite environment variables are prefixed with VITE_
  // We'll use the same origin by default
  return "";
};

export class ApiClient {
  async request<T = unknown>(endpoint: string, options?: RequestInit): Promise<T> {
    const apiKey = sessionStorage.getItem("api_key");
    const baseUrl = getApiBaseUrl();
    const lang = localStorage.getItem("ui_lang") === "en" ? "en" : "it";
    
    const headers: HeadersInit = {
      "Content-Type": "application/json",
      "X-Language": lang,
      ...((options?.headers as Record<string, string>) || {}),
    };
    
    if (apiKey) {
      headers["X-API-Key"] = apiKey;
    }
    
    const response = await fetch(`${baseUrl}${endpoint}`, {
      ...options,
      headers,
    });
    
    if (!response.ok) {
      const fallbackMessage = lang === "en" ? `HTTP error ${response.status}` : `Errore HTTP ${response.status}`;
      const error = await response.json().catch(() => ({detail: fallbackMessage}));
      const message = typeof error.detail === "string" ? error.detail : JSON.stringify(error.detail);
      throw new Error(message || fallbackMessage);
    }

    return (await response.json()) as T;
  }

  async getHealth(): Promise<HealthStatus> {
    return this.request("/health");
  }

  async getModels(): Promise<{models: OllamaModel[]}> {
    return this.request("/api/ollama/models");
  }

  async getCharacters(): Promise<Character[]> {
    return this.request("/api/characters");
  }

  async createCharacter(data: {name: string; profile: CharacterProfile}): Promise<Character> {
    return this.request("/api/characters", {method: "POST", body: JSON.stringify(data)});
  }

  async updateCharacter(id: string, data: {name?: string; profile?: CharacterProfile}): Promise<Character> {
    return this.request(`/api/characters/${id}`, {method: "PUT", body: JSON.stringify(data)});
  }

  async getCharacter(id: string): Promise<Character> {
    return this.request(`/api/characters/${id}`);
  }

  async cloneCharacter(id: string, name?: string): Promise<Character> {
    return this.request(`/api/characters/${id}/clone`, {
      method: "POST",
      body: JSON.stringify({ ...(name ? { name } : {}) }),
    });
  }

  async generateAvatar(id: string): Promise<Character> {
    return this.request(`/api/characters/${id}/avatar`, { method: "POST" });
  }

  async getCheckpoints(): Promise<{available: boolean; checkpoints: CheckpointInfo[]}> {
    return this.request("/api/images/checkpoints");
  }

  async setPpv(id: string, data: {enabled: boolean; price_cents: number}): Promise<Character> {
    return this.request(`/api/characters/${id}/ppv`, { method: "PUT", body: JSON.stringify(data) });
  }

  async unlockChatImage(id: string): Promise<ChatImage & {payment: {amount_cents: number; simulated: boolean}}> {
    return this.request(`/api/chat-images/${id}/unlock`, { method: "POST" });
  }

  async getGpuStatus(): Promise<GpuReport> {
    return this.request("/api/system/gpus");
  }

  async setImageCheckpoint(id: string, checkpoint: string | null): Promise<Character> {
    return this.request(`/api/characters/${id}/image-checkpoint`, {
      method: "PUT",
      body: JSON.stringify({ checkpoint }),
    });
  }

  async setImageStyle(id: string, style: "anime" | "real" | null): Promise<Character> {
    return this.request(`/api/characters/${id}/image-style`, {
      method: "PUT",
      body: JSON.stringify({ style }),
    });
  }

  async getLoras(): Promise<{available: boolean; loras: string[]}> {
    return this.request("/api/images/loras");
  }

  async getLibrary(characterId: string, params: {status?: string; style?: string; limit?: number} = {}): Promise<LibraryImage[]> {
    const query = new URLSearchParams();
    if (params.status) query.set("status", params.status);
    if (params.style) query.set("style", params.style);
    query.set("limit", String(params.limit ?? 60));
    return this.request(`/api/characters/${characterId}/library?${query.toString()}`);
  }

  async generateLibraryImages(characterId: string, data: LibraryGenerateInput): Promise<LibraryImage[]> {
    return this.request(`/api/characters/${characterId}/library/generate`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  async patchLibraryItem(id: string, data: {status?: string; rating?: number; caption?: string; tags?: string[]}): Promise<LibraryImage> {
    return this.request(`/api/library/${id}`, { method: "PATCH", body: JSON.stringify(data) });
  }

  async deleteLibraryItem(id: string): Promise<{deleted: boolean}> {
    return this.request(`/api/library/${id}`, { method: "DELETE" });
  }

  async classifyLibraryItem(id: string): Promise<LibraryImage> {
    return this.request(`/api/library/${id}/classify`, { method: "POST" });
  }

  async augmentPrompt(characterId: string, data: {prompt: string; style: string; direction: string}): Promise<{prompt: string}> {
    return this.request(`/api/characters/${characterId}/library/prompt`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  async getDatasetSources(): Promise<DatasetSource[]> {
    return this.request("/api/dataset/sources");
  }

  async createDatasetSource(data: {name: string; kind: string; reference: string; limit: number; classify: boolean}): Promise<DatasetSource> {
    return this.request("/api/dataset/sources", { method: "POST", body: JSON.stringify(data) });
  }

  async getDatasetSource(id: string): Promise<DatasetSource> {
    return this.request(`/api/dataset/sources/${id}`);
  }

  async deleteDatasetSource(id: string): Promise<{deleted: boolean}> {
    return this.request(`/api/dataset/sources/${id}`, { method: "DELETE" });
  }

  async classifyDatasetSource(id: string): Promise<{started: boolean}> {
    return this.request(`/api/dataset/sources/${id}/classify`, { method: "POST" });
  }

  async datasetProfile(id: string): Promise<{profile: CharacterProfile}> {
    return this.request(`/api/dataset/sources/${id}/profile`, { method: "POST" });
  }

  async exportDataset(id: string): Promise<Blob> {
    return this.fetchBlob(`/api/dataset/sources/${id}/export`);
  }

  async getDatasetImages(sourceId: string, params: {status?: string; limit?: number} = {}): Promise<DatasetImage[]> {
    const query = new URLSearchParams({ source_id: sourceId });
    if (params.status) query.set("status", params.status);
    query.set("limit", String(params.limit ?? 200));
    return this.request(`/api/dataset/images?${query.toString()}`);
  }

  async deleteDatasetImage(id: string): Promise<{deleted: boolean}> {
    return this.request(`/api/dataset/images/${id}`, { method: "DELETE" });
  }

  async sendPhoto(conversationId: string, data: {scene?: string; caption?: string; locked?: boolean; price_cents?: number}): Promise<Message> {
    return this.request(`/api/conversations/${conversationId}/photo`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  async fetchBlob(endpoint: string): Promise<Blob> {
    const apiKey = sessionStorage.getItem("api_key");
    const headers: Record<string, string> = { "X-Language": localStorage.getItem("ui_lang") === "en" ? "en" : "it" };
    if (apiKey) headers["X-API-Key"] = apiKey;
    const response = await fetch(`${getApiBaseUrl()}${endpoint}`, { headers });
    if (!response.ok) throw new Error(`Errore HTTP ${response.status}`);
    return response.blob();
  }

  async getConversations(characterId: string): Promise<Conversation[]> {
    return this.request(`/api/characters/${characterId}/conversations`);
  }

  async createConversation(characterId: string, data: {title?: string; model: string}): Promise<Conversation> {
    return this.request(`/api/characters/${characterId}/conversations`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  async updateConversation(id: string, data: {title?: string; model?: string; images_enabled?: boolean}): Promise<Conversation> {
    return this.request(`/api/conversations/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    });
  }

  async getConversation(id: string): Promise<Conversation> {
    return this.request(`/api/conversations/${id}`);
  }

  async getConversationMessages(conversationId: string): Promise<Message[]> {
    return this.request(`/api/conversations/${conversationId}/messages`);
  }

  async sendMessage(conversationId: string, content: string): Promise<Message> {
    return this.request(`/api/conversations/${conversationId}/messages`, {
      method: "POST",
      body: JSON.stringify({content}),
    });
  }

  async getMemories(characterId: string): Promise<Memory[]> {
    return this.request(`/api/characters/${characterId}/memories`);
  }

  async deleteMemory(id: string): Promise<void> {
    await this.request(`/api/memories/${id}`, {method: "DELETE"});
  }

  async clearMemories(characterId: string): Promise<{deleted: boolean; count: number}> {
    return this.request(`/api/characters/${characterId}/memories`, {method: "DELETE"});
  }

  async deleteCharacter(id: string): Promise<{deleted: boolean; id: string}> {
    return this.request(`/api/characters/${id}`, {method: "DELETE"});
  }
}

export const api = new ApiClient();
