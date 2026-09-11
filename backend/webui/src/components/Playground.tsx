import { useState, useEffect, useCallback } from "react";
import { api, Character, Conversation, Message, Memory, OllamaModel, HealthStatus, CharacterProfile } from "../api";
import CharacterCard from "./CharacterCard";
import CharacterForm from "./CharacterForm";
import ChatPanel from "./ChatPanel";
import RightPanel from "./RightPanel";

interface PlaygroundProps {
  onLogout: () => void;
}

export default function Playground({ onLogout }: PlaygroundProps) {
  const [activeTab, setActiveTab] = useState<"list" | "create" | "edit">("list");
  const [characters, setCharacters] = useState<Character[]>([]);
  const [selectedCharacter, setSelectedCharacter] = useState<Character | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [selectedConversation, setSelectedConversation] = useState<Conversation | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [memories, setMemories] = useState<Memory[]>([]);
  const [models, setModels] = useState<OllamaModel[]>([]);
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [editingCharacter, setEditingCharacter] = useState<Character | null>(null);

  const loadCharacters = useCallback(async () => {
    try {
      const data = await api.getCharacters();
      setCharacters(data);
    } catch (err) {
      setError("Failed to load characters");
      console.error(err);
    }
  }, []);

  const loadConversations = useCallback(async (characterId: string) => {
    try {
      const data = await api.getConversations(characterId);
      setConversations(data);
    } catch (err) {
      setError("Failed to load conversations");
      console.error(err);
    }
  }, []);

  const loadMessages = useCallback(async (conversationId: string) => {
    try {
      const data = await api.getConversationMessages(conversationId);
      setMessages(data);
    } catch (err) {
      setError("Failed to load messages");
      console.error(err);
    }
  }, []);

  const loadMemories = useCallback(async (characterId: string) => {
    try {
      const data = await api.getMemories(characterId);
      setMemories(data);
    } catch (err) {
      console.error(err);
      setMemories([]);
    }
  }, []);

  const loadModels = useCallback(async () => {
    try {
      const data = await api.getModels();
      setModels(data.models);
    } catch (err) {
      console.error(err);
      setModels([]);
    }
  }, []);

  const loadHealth = useCallback(async () => {
    try {
      const data = await api.getHealth();
      setHealth(data);
    } catch (err) {
      console.error(err);
    }
  }, []);

  useEffect(() => {
    loadCharacters();
    loadModels();
    loadHealth();
  }, [loadCharacters, loadModels, loadHealth]);

  const handleSelectCharacter = (character: Character) => {
    setSelectedCharacter(character);
    loadConversations(character.id);
    loadMemories(character.id);
    setActiveTab("list");
  };

  const handleCreateCharacter = async (data: {name: string; profile: CharacterProfile}) => {
    try {
      const newCharacter = await api.createCharacter(data);
      setCharacters([...characters, newCharacter]);
      setShowForm(false);
      setError(null);
    } catch (err) {
      setError("Failed to create character");
      console.error(err);
    }
  };

  const handleUpdateCharacter = async (data: {name?: string; profile?: CharacterProfile}) => {
    if (!editingCharacter) return;
    try {
      const updated = await api.updateCharacter(editingCharacter.id, data);
      setCharacters(characters.map(c => c.id === updated.id ? updated : c));
      if (selectedCharacter?.id === updated.id) {
        setSelectedCharacter(updated);
      }
      setShowForm(false);
      setEditingCharacter(null);
      setError(null);
    } catch (err) {
      setError("Failed to update character");
      console.error(err);
    }
  };

  const handleSelectConversation = (conversation: Conversation) => {
    setSelectedConversation(conversation);
    loadMessages(conversation.id);
  };

  const handleSendMessage = useCallback(async (content: string) => {
    if (!selectedConversation) return;
    setLoading(true);
    setError(null);
    try {
      const message = await api.sendMessage(selectedConversation.id, content);
      setMessages(prev => [...prev, message]);
    } catch (err) {
      setError("Failed to send message");
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [selectedConversation]);

  const handleNewConversation = useCallback(async (model: string) => {
    console.log("handleNewConversation called with model:", model);
    if (!selectedCharacter) {
      setError("Please select a character first");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const conversation = await api.createConversation(selectedCharacter.id, {
        model,
        title: `Conversation with ${selectedCharacter.name}`,
      });
      console.log("Conversation created:", conversation);
      setSelectedConversation(conversation);
      loadMessages(conversation.id);
      setError(null);
    } catch (err) {
      console.error("Failed to create conversation:", err);
      setError("Failed to create conversation: " + (err?.toString() || "Unknown error"));
    } finally {
      setLoading(false);
    }
  }, [selectedCharacter, loadMessages]);

  const handleClearMemories = async () => {
    if (!selectedCharacter) return;
    if (!window.confirm("Are you sure you want to clear all memories?")) return;
    try {
      await api.clearMemories(selectedCharacter.id);
      setMemories([]);
      setError(null);
    } catch (err) {
      setError("Failed to clear memories");
      console.error(err);
    }
  };

  const handleDeleteMemory = async (memoryId: string) => {
    try {
      await api.deleteMemory(memoryId);
      setMemories(memories.filter(m => m.id !== memoryId));
      setError(null);
    } catch (err) {
      setError("Failed to delete memory");
      console.error(err);
    }
  };

  return (
    <div className="flex flex-col h-full">
      <header className="bg-gray-900 border-b border-gray-800 px-6 py-4 flex justify-between items-center">
        <div className="flex items-center space-x-4">
          <h1 className="text-2xl font-bold text-blue-400">AI Influencer Playground v2</h1>
          <span className="text-sm text-gray-500">Character Chat & Memory System</span>
        </div>
        <div className="flex items-center space-x-4">
          {health && (
            <div className="flex items-center space-x-2 text-sm">
              <span className={`flex items-center space-x-1 ${health.status === "ok" ? "text-green-400" : "text-red-400"}`}>
                <span className="w-2 h-2 rounded-full bg-current"></span>
                <span>Backend: {health.status}</span>
              </span>
            </div>
          )}
          <button
            onClick={onLogout}
            className="px-4 py-2 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-lg transition-colors text-sm"
          >
            Logout
          </button>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        <div className="w-1/3 border-r border-gray-800 flex flex-col bg-gray-900">
          <div className="p-4 border-b border-gray-800">
            <div className="flex space-x-2">
              <button
                onClick={() => setActiveTab("list")}
                className={`px-4 py-2 rounded-lg transition-colors ${activeTab === "list" ? "bg-blue-600 text-white" : "bg-gray-800 text-gray-400 hover:bg-gray-700"}`}
              >
                List Characters
              </button>
              <button
                onClick={() => {
                  setEditingCharacter(null);
                  setShowForm(true);
                }}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
              >
                + New Character
              </button>
            </div>
          </div>

          {showForm ? (
            <CharacterForm
              character={editingCharacter || undefined}
              onSave={editingCharacter ? handleUpdateCharacter : handleCreateCharacter}
              onCancel={() => {
                setShowForm(false);
                setEditingCharacter(null);
              }}
            />
          ) : activeTab === "list" ? (
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {characters.map((character) => (
                <CharacterCard
                  key={character.id}
                  character={character}
                  onClick={() => handleSelectCharacter(character)}
                />
              ))}
            </div>
          ) : null}
        </div>

        <div className="w-1/3 flex flex-col bg-gray-900">
          {selectedCharacter ? (
            <>
              <div className="p-4 border-b border-gray-800 bg-gray-900/50">
                <div className="flex justify-between items-start">
                  <div>
                    <h2 className="text-xl font-semibold text-white">{selectedCharacter.name}</h2>
                    <p className="text-sm text-gray-500">
                      {selectedCharacter.profile.personality_traits || "No personality defined"}
                    </p>
                  </div>
                  <button
                    onClick={() => {
                      setEditingCharacter(selectedCharacter);
                      setShowForm(true);
                    }}
                    className="px-3 py-1 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-lg text-sm transition-colors"
                  >
                    Edit Profile
                  </button>
                </div>
              </div>

              <div className="flex-1 overflow-y-auto p-4 space-y-4">
                {selectedConversation ? (
                  <ChatPanel
                    conversation={selectedConversation}
                    messages={messages}
                    onSendMessage={handleSendMessage}
                    loading={loading}
                    error={error}
                  />
                ) : (
                  <div className="flex-1 flex flex-col items-center justify-center text-gray-500 space-y-4">
                    <div className="w-16 h-16 border-2 border-gray-700 rounded-full flex items-center justify-center">
                      <span className="text-3xl">💬</span>
                    </div>
                    <p>Select or create a conversation to start chatting</p>
                    <div className="flex flex-wrap justify-center gap-2 max-w-md">
                      {models.length > 0 ? (
                        models.map(model => (
                          <button
                            key={model.name}
                            onClick={() => handleNewConversation(model.name)}
                            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors text-sm"
                          >
                            Start with {model.name.replace(/:latest$/, "")}
                          </button>
                        ))
                      ) : (
                        <p className="text-red-400 text-center">No Ollama models available</p>
                      )}
                    </div>
                  </div>
                )}

                <div className="space-y-2">
                  <h3 className="text-sm font-medium text-gray-400 uppercase">Conversations</h3>
                  {conversations.map((conv) => (
                    <button
                      key={conv.id}
                      onClick={() => handleSelectConversation(conv)}
                      className={`w-full text-left p-3 rounded-lg transition-colors ${selectedConversation?.id === conv.id ? "bg-blue-900/30 border border-blue-700" : "bg-gray-800 hover:bg-gray-700 border border-gray-700"}`}
                    >
                      <div className="font-medium text-white">{conv.title}</div>
                      <div className="text-xs text-gray-500 flex items-center space-x-2 mt-1">
                        <span>{new Date(conv.created_at).toLocaleDateString()}</span>
                        <span>•</span>
                        <span>{conv.model.replace(/:latest$/, "")}</span>
                        <span>•</span>
                        <span>{conv.character_snapshot.name}</span>
                      </div>
                    </button>
                  ))}
                  {conversations.length === 0 && (
                    <p className="text-sm text-gray-600 text-center py-4">No conversations yet</p>
                  )}
                </div>
              </div>
            </>
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center text-gray-500">
              <div className="w-20 h-20 border-2 border-gray-700 rounded-full flex items-center justify-center mb-6">
                <span className="text-4xl">👤</span>
              </div>
              <p className="text-xl mb-4">Select a character to start</p>
              <button
                onClick={() => {
                  setEditingCharacter(null);
                  setShowForm(true);
                }}
                className="px-6 py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors font-medium"
              >
                Create a New Character
              </button>
            </div>
          )}
        </div>

        <RightPanel
          health={health}
          models={models}
          memories={memories}
          onClearMemories={handleClearMemories}
          onDeleteMemory={handleDeleteMemory}
        />
      </div>
    </div>
  );
}
