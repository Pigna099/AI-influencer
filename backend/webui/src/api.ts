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
}

export interface CharacterProfile {
  description: string;
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
  created_at: string;
}

export interface Conversation {
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

export interface Message {
  id: string;
  conversation_id: string;
  role: "user" | "assistant";
  content: string;
  model: string | null;
  ollama_metrics: {
    total_duration: number | null;
    load_duration: number | null;
    prompt_eval_count: number | null;
    eval_count: number | null;
    eval_duration: number | null;
  } | null;
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
    
    const headers: HeadersInit = {
      "Content-Type": "application/json",
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
      try {
        const error = (await response.json()) as ApiError;
        throw new Error(error.detail || `API error: ${response.status}`);
      } catch {
        throw new Error(`API error: ${response.status}`);
      }
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

  async getConversations(characterId: string): Promise<Conversation[]> {
    return this.request(`/api/characters/${characterId}/conversations`);
  }

  async createConversation(characterId: string, data: {title?: string; model: string}): Promise<Conversation> {
    return this.request(`/api/characters/${characterId}/conversations`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  async updateConversation(id: string, data: {title?: string; model?: string}): Promise<Conversation> {
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
