import { useState } from "react";
import { useNavigate } from "react-router-dom";

interface LoginProps {
  onLogin: (key: string) => void;
}

export default function Login({ onLogin }: LoginProps) {
  const [key, setKey] = useState("");
  const [error, setError] = useState("");
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (!key.trim()) {
      setError("Inserisci la chiave di accesso");
      return;
    }

    try {
      const response = await fetch("/api/characters?limit=1", { headers: {"X-API-Key": key.trim()} });
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { detail?: unknown } | null;
        throw new Error(typeof payload?.detail === "string" ? payload.detail : `Errore HTTP ${response.status}`);
      }
      onLogin(key.trim());
      navigate("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Autenticazione non riuscita. Controlla la chiave API.");
      console.error(err);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-950 p-4">
      <div className="max-w-md w-full">
        <div className="bg-gray-900 rounded-xl p-8 shadow-2xl border border-gray-800">
          <div className="text-center mb-8">
            <h1 className="text-3xl font-bold text-blue-400 mb-2">AI influencer playground v3.2</h1>
            <p className="text-gray-400">Chat, personalità e memoria. Il tuo laboratorio privato.</p>
          </div>
          
          <form onSubmit={handleSubmit} className="space-y-6">
            <div>
              <label htmlFor="api-key" className="block text-sm font-medium text-gray-300 mb-2">
                API Key
              </label>
              <input
                id="api-key"
                type="password"
                value={key}
                onChange={(e) => setKey(e.target.value)}
                className="w-full px-4 py-3 bg-gray-950 border border-gray-700 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none transition-all text-white"
                placeholder="Inserisci la chiave API"
                required
              />
            </div>

            {error && (
              <div className="bg-red-900/30 border border-red-700 rounded-lg p-4 text-red-200 text-sm">
                {error}
              </div>
            )}

            <button
              type="submit"
              className="w-full px-4 py-3 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-lg transition-colors duration-200 focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 focus:ring-offset-gray-900"
            >
              Entra nel playground
            </button>
          </form>

          <div className="mt-6 text-center text-sm text-gray-500">
            <p>La chiave resta nella sessione di questo browser fino al logout.</p>
          </div>
        </div>
      </div>
    </div>
  );
}
