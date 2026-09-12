import { Character } from "../api";

interface CharacterCardProps {
  character: Character;
  onClick: () => void;
  onDelete?: () => void;
}

export default function CharacterCard({ character, onClick, onDelete }: CharacterCardProps) {
  return (
    <div
      onClick={onClick}
      className="group p-4 bg-gray-800 hover:bg-gray-700 rounded-xl border border-gray-700 hover:border-blue-600 transition-all cursor-pointer shadow-lg"
    >
      <div className="flex items-start justify-between mb-2">
        <h3 className="text-lg font-semibold text-white group-hover:text-blue-400 transition-colors">
          {character.name}
        </h3>
        <span className="text-xs text-gray-500 bg-gray-900 px-2 py-1 rounded">
          v{character.version}
        </span>
      </div>
      
      <p className="text-gray-400 text-sm line-clamp-2 mb-3">
        {character.profile.description || "No description provided"}
      </p>
      
      <div className="flex flex-wrap gap-2 mt-3">
        {character.profile.personality_traits && (
          <span className="text-xs text-gray-500 bg-gray-900/50 px-2 py-1 rounded-full">
            {character.profile.personality_traits.split(",")[0].trim()}
          </span>
        )}
        <span className="text-xs text-gray-600 px-2 py-1 rounded-full">
          {new Date(character.created_at).toLocaleDateString()}
        </span>
        {onDelete && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              onDelete();
            }}
            className="text-gray-500 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity text-lg p-1"
            title="Delete character"
          >
            ×
          </button>
        )}
      </div>
    </div>
  );
}
