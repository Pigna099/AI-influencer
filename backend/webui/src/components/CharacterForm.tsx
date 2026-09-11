import { CharacterProfile, Character } from "../api";
import { useState } from "react";

interface CharacterFormProps {
  character?: Character;
  onSave: (data: {name: string; profile: CharacterProfile}) => void;
  onCancel: () => void;
}

export default function CharacterForm({ character, onSave, onCancel }: CharacterFormProps) {
  const [formData, setFormData] = useState({
    name: character?.name || "",
    profile: character?.profile || {
      description: "",
      background: "",
      personality_traits: "",
      tone_of_voice: "",
      speech_style: "",
      vocabulary: "",
      likes: "",
      dislikes: "",
      boundaries: "",
      relationship_style: "",
      language: "en",
      custom_instructions: "",
    },
  });

  const handleChange = (field: keyof typeof formData, value: string) => {
    setFormData(prev => ({...prev, [field]: value}));
  };

  const handleProfileChange = (field: keyof CharacterProfile, value: string) => {
    setFormData(prev => ({
      ...prev,
      profile: {...prev.profile, [field]: value},
    }));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.name.trim() || !formData.profile.description.trim()) {
      return;
    }
    onSave({
      name: formData.name,
      profile: formData.profile,
    });
  };

  return (
    <div className="p-4 overflow-y-auto max-h-[calc(100vh-140px)]">
      <h3 className="text-xl font-semibold mb-4 text-white">
        {character ? "Edit Character" : "Create New Character"}
      </h3>
      
      <form onSubmit={handleSubmit} className="space-y-6">
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">Name</label>
          <input
            type="text"
            value={formData.name}
            onChange={(e) => handleChange("name", e.target.value)}
            className="w-full px-4 py-2 bg-gray-950 border border-gray-700 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-white"
            placeholder="e.g., Nikita"
            required
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Description <span className="text-red-400">*</span>
          </label>
          <textarea
            value={formData.profile.description}
            onChange={(e) => handleProfileChange("description", e.target.value)}
            rows={3}
            className="w-full px-4 py-2 bg-gray-950 border border-gray-700 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-white"
            placeholder="Brief overview of the character"
            required
          />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">Personality</label>
            <input
              type="text"
              value={formData.profile.personality_traits}
              onChange={(e) => handleProfileChange("personality_traits", e.target.value)}
              className="w-full px-4 py-2 bg-gray-950 border border-gray-700 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-white"
              placeholder="e.g., cheerful, helpful"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">Voice</label>
            <input
              type="text"
              value={formData.profile.tone_of_voice}
              onChange={(e) => handleProfileChange("tone_of_voice", e.target.value)}
              className="w-full px-4 py-2 bg-gray-950 border border-gray-700 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-white"
              placeholder="e.g., warm, professional"
            />
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">Background</label>
          <textarea
            value={formData.profile.background}
            onChange={(e) => handleProfileChange("background", e.target.value)}
            rows={2}
            className="w-full px-4 py-2 bg-gray-950 border border-gray-700 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-white"
            placeholder="Backstory and origins"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">Likes</label>
          <textarea
            value={formData.profile.likes}
            onChange={(e) => handleProfileChange("likes", e.target.value)}
            rows={2}
            className="w-full px-4 py-2 bg-gray-950 border border-gray-700 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-white"
            placeholder="Interests and preferences"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">Dislikes</label>
          <textarea
            value={formData.profile.dislikes}
            onChange={(e) => handleProfileChange("dislikes", e.target.value)}
            rows={2}
            className="w-full px-4 py-2 bg-gray-950 border border-gray-700 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-white"
            placeholder="Things to avoid"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">Boundaries</label>
          <textarea
            value={formData.profile.boundaries}
            onChange={(e) => handleProfileChange("boundaries", e.target.value)}
            rows={2}
            className="w-full px-4 py-2 bg-gray-950 border border-gray-700 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-white"
            placeholder="Content restrictions and limits"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">Custom Instructions</label>
          <textarea
            value={formData.profile.custom_instructions}
            onChange={(e) => handleProfileChange("custom_instructions", e.target.value)}
            rows={3}
            className="w-full px-4 py-2 bg-gray-950 border border-gray-700 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent text-white"
            placeholder="Additional guidance for behavior"
          />
        </div>

        <div className="flex space-x-3 pt-4">
          <button
            type="submit"
            className="flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors"
          >
            {character ? "Save Changes" : "Create Character"}
          </button>
          <button
            type="button"
            onClick={onCancel}
            className="flex-1 px-4 py-2 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-lg transition-colors"
          >
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}
