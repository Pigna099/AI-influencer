import { useState } from "react";
import { api, CharacterProfile, Character, OllamaModel } from "../api";

const defaults: CharacterProfile = { description: "", appearance: "", background: "", personality_traits: "curiosa, giocosa, propositiva", tone_of_voice: "caldo, spontaneo, leggermente flirtante", speech_style: "Messaggi brevi e naturali, una domanda alla volta", vocabulary: "", likes: "", dislikes: "", boundaries: "Adulti, flirt consensuale e non esplicito; rispetto dei no", relationship_style: "Complice e indipendente, senza pressioni", language: "it", custom_instructions: "Prendi iniziativa e proponi argomenti in linea con gli interessi del fan." };
const fields: [keyof CharacterProfile, string, number][] = [
  ["description", "Descrizione e identità", 5000], ["appearance", "Aspetto fisico (età adulta, genere, capelli, corpo, stile)", 2000], ["personality_traits", "Tratti della personalità", 2000],
  ["tone_of_voice", "Tono di voce", 1000], ["speech_style", "Come scrive", 1000], ["background", "Storia personale", 5000],
  ["likes", "Interessi e passioni", 2000], ["dislikes", "Cosa non le/gli piace", 2000], ["vocabulary", "Espressioni e vocabolario", 1000],
  ["relationship_style", "Modo di relazionarsi", 1000], ["boundaries", "Limiti", 2000], ["custom_instructions", "Istruzioni aggiuntive", 5000],
];

export default function CharacterForm({ character, models, onSave, onCancel }: { character?: Character; models: OllamaModel[]; onSave: (data: {name: string; profile: CharacterProfile}) => Promise<void>; onCancel: () => void }) {
  const [name, setName] = useState(character?.name || "");
  const [profile, setProfile] = useState<CharacterProfile>({ ...defaults, ...character?.profile });
  const [model, setModel] = useState(models.find(m => m.name === "llama3.1:8b")?.name || models[0]?.name || "");
  const [direction, setDirection] = useState("Arricchisci la personalità: più distintiva, propositiva e capace di flirt leggero. Mantieni identità e limiti.");
  const [draft, setDraft] = useState<CharacterProfile | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const enhance = async () => {
    setBusy("Il modello sta ampliando la personalità…"); setError("");
    try { const result = await api.request<{profile: CharacterProfile}>("/api/character-drafts/enhance", { method: "POST", body: JSON.stringify({ name, profile, model, direction }) }); setDraft(result.profile); }
    catch (e) { setError(e instanceof Error ? e.message : "Non è stato possibile generare la proposta"); } finally { setBusy(""); }
  };
  return <div className="character-editor"><header><div><span className="eyebrow">PERSONALITÀ</span><h2>{character ? `Modifica ${character.name}` : "Crea un personaggio"}</h2></div><button onClick={onCancel} disabled={!!busy} aria-label="Chiudi editor">×</button></header>
    <form onSubmit={async e => { e.preventDefault(); setBusy("Salvataggio…"); setError(""); try { await onSave({ name, profile }); } catch (err) { setError(String(err)); } finally { setBusy(""); } }}>
      <fieldset disabled={!!busy}><div className="editor-identity"><label>Nome<input autoFocus value={name} onChange={e => setName(e.target.value)} required maxLength={120} /></label><label>Lingua<select value={profile.language} onChange={e => setProfile(p => ({ ...p, language: e.target.value }))}><option value="it">Italiano</option><option value="en">English</option><option value="fr">Français</option><option value="de">Deutsch</option><option value="es">Español</option></select></label></div>
        <div className="profile-fields">{fields.map(([key, label, max]) => <label key={key}>{label}<textarea value={profile[key]} onChange={e => setProfile(p => ({ ...p, [key]: e.target.value }))} rows={key === "description" ? 3 : 2} maxLength={max} required={key === "description"} /></label>)}</div>
        <p className="muted">L’aspetto fisico guida le immagini generate: descrivi età adulta, genere, capelli, corporatura e stile. Dalla colonna sinistra, <b>Foto profilo</b> genera e memorizza l’immagine di riferimento del personaggio.</p>
        <div className="enhance-box"><h3>Amplia con un modello installato</h3><label>Modello<select value={model} onChange={e => setModel(e.target.value)}>{models.map(m => <option key={m.name} value={m.name}>{m.name}</option>)}</select></label><label>Direzione creativa<textarea rows={2} value={direction} onChange={e => setDirection(e.target.value)} maxLength={2000} /></label><button type="button" disabled={!name.trim() || !profile.description.trim() || !model} onClick={() => void enhance()}>Genera proposta</button><small>La proposta viene mostrata prima di applicarla. I dati salvati restano invariati finché non premi Salva.</small></div>
      </fieldset>
      {busy && <p className="memory-status" role="status"><span className="spinner" />{busy}</p>}{error && <p className="warning" role="alert">{error}</p>}
      {draft && <div className="draft-preview"><h3>Proposta del modello</h3>{fields.map(([key, label]) => <div key={key}><strong>{label}</strong><p>{draft[key]}</p></div>)}<div className="modal-actions"><button type="button" disabled={!!busy} onClick={() => setDraft(null)}>Scarta proposta</button><button className="primary" type="button" disabled={!!busy} onClick={() => { setProfile(draft); setDraft(null); }}>Applica nell’editor</button></div></div>}
      <div className="modal-actions sticky-actions"><button type="button" disabled={!!busy} onClick={onCancel}>Annulla</button><button className="primary" disabled={!!busy}>Salva personaggio</button></div>
    </form>
  </div>;
}
