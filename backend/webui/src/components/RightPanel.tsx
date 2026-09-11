import { HealthStatus, OllamaModel, Memory } from "../api";

interface RightPanelProps {
  health: HealthStatus | null;
  models: OllamaModel[];
  memories: Memory[];
  onClearMemories: () => void;
  onDeleteMemory: (id: string) => void;
}

export default function RightPanel({ health, models, memories, onClearMemories, onDeleteMemory }: RightPanelProps) {
  return (
    <div className="w-1/3 border-l border-gray-800 bg-gray-900 flex flex-col">
      {/* Health Status */}
      <div className="p-4 border-b border-gray-800">
        <h3 className="text-sm font-semibold text-gray-400 uppercase mb-3">System Status</h3>
        {health ? (
          <div className="space-y-2">
            <div className="flex justify-between items-center">
              <span className="text-gray-300">Status</span>
              <span className={`flex items-center space-x-1 ${health.status === "ok" ? "text-green-400" : "text-red-400"}`}>
                <span className="w-2 h-2 rounded-full bg-current"></span>
                <span>{health.status}</span>
              </span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-gray-300">Text Provider</span>
              <span className="text-white font-mono">{health.text_provider}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-gray-300">Image Provider</span>
              <span className="text-white font-mono">{health.image_provider}</span>
            </div>
            {health.text_provider === "ollama" && (
              <div className="mt-2 pt-2 border-t border-gray-800">
                <p className="text-xs text-gray-400 mb-2">Ollama Models ({models.length} available):</p>
                {models.slice(0, 5).map(model => (
                  <div key={model.name} className="text-xs text-gray-500 mb-1 truncate">
                    <span className="font-mono">{model.name.replace(/:latest$/, "")}</span>
                    <span className="ml-2 text-gray-600">({model.parameter_size}, {model.family})</span>
                  </div>
                ))}
                {models.length > 5 && (
                  <p className="text-xs text-gray-500">+{models.length - 5} more models</p>
                )}
              </div>
            )}
          </div>
        ) : (
          <div className="text-gray-500 text-sm">Loading status...</div>
        )}
      </div>

      {/* Memories */}
      <div className="flex-1 overflow-y-auto p-4">
        <div className="flex justify-between items-center mb-3">
          <h3 className="text-sm font-semibold text-gray-400 uppercase">Character Memories</h3>
          {memories.length > 0 && (
            <button
              onClick={() => {
                if (window.confirm("Clear all memories?")) {
                  onClearMemories();
                }
              }}
              className="text-xs text-red-400 hover:text-red-300 transition-colors"
            >
              Clear All
            </button>
          )}
        </div>

        {memories.length === 0 ? (
          <div className="text-center text-gray-500 py-8">
            <div className="w-12 h-12 border-2 border-gray-700 rounded-full flex items-center justify-center mx-auto mb-3">
              <span className="text-xl">🧠</span>
            </div>
            <p className="text-sm">No memories extracted yet</p>
            <p className="text-xs text-gray-600 mt-2">Memories appear after conversations</p>
          </div>
        ) : (
          <div className="space-y-3">
            {memories.map((memory) => (
              <div
                key={memory.id}
                className="relative p-3 bg-gray-800 rounded-lg border border-gray-700 hover:border-gray-600 transition-all group"
              >
                <div className="flex justify-between items-start mb-2">
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] uppercase font-bold text-gray-400 bg-gray-900 px-1.5 py-0.5 rounded">
                      {memory.category}
                    </span>
                    <span className="text-xs text-gray-500">Importance: {memory.importance}/5</span>
                  </div>
                  <button
                    onClick={() => {
                      onDeleteMemory(memory.id);
                    }}
                    className="text-gray-500 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity"
                    title="Delete memory"
                  >
                    ×
                  </button>
                </div>
                <p className="text-sm text-gray-200 leading-relaxed">{escapeHtml(memory.content)}</p>
                {memory.source_message_id && (
                  <div className="mt-2 pt-2 border-t border-gray-700 text-xs text-gray-500">
                    Extracted from conversation
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function escapeHtml(text: string): string {
  const map: { [key: string]: string } = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  };
  return text.replace(/[&<>"']/g, (m) => map[m]);
}
