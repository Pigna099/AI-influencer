import { useEffect, useState } from "react";
import { api, CharacterProfile, Character, OllamaModel } from "../api";
import { useI18n, Lang, TranslationKey } from "../i18n";

const chatModels = (models: OllamaModel[]) => models.filter(m => m.chat_capable !== false && (m.kind ? m.kind === "chat" : !m.name.toLowerCase().includes("embed")) && !m.name.toLowerCase().includes("embed"));

const profileDefaults: Record<Lang, CharacterProfile> = {
  it: { description: "", appearance: "", background: "", personality_traits: "curiosa, giocosa, propositiva", tone_of_voice: "caldo, spontaneo, leggermente flirtante", speech_style: "Messaggi brevi e naturali, una domanda alla volta", vocabulary: "", likes: "", dislikes: "", boundaries: "Adulti, flirt consensuale e non esplicito; rispetto dei no", relationship_style: "Complice e indipendente, senza pressioni", language: "it", custom_instructions: "Prendi iniziativa e proponi argomenti in linea con gli interessi del fan." },
  en: { description: "", appearance: "", background: "", personality_traits: "curious, playful, proactive", tone_of_voice: "warm, spontaneous, lightly flirtatious", speech_style: "Short, natural messages, one question at a time", vocabulary: "", likes: "", dislikes: "", boundaries: "Adults, consensual and non-explicit flirting; respect boundaries", relationship_style: "Playful and independent, no pressure", language: "en", custom_instructions: "Take initiative and suggest topics that match the fan's interests." },
};

const fields: [keyof CharacterProfile, TranslationKey, number][] = [
  ["description", "form.field.description", 5000], ["appearance", "form.field.appearance", 2000], ["personality_traits", "form.field.personality_traits", 2000],
  ["tone_of_voice", "form.field.tone_of_voice", 1000], ["speech_style", "form.field.speech_style", 1000], ["background", "form.field.background", 5000],
  ["likes", "form.field.likes", 2000], ["dislikes", "form.field.dislikes", 2000], ["vocabulary", "form.field.vocabulary", 1000],
  ["relationship_style", "form.field.relationship_style", 1000], ["boundaries", "form.field.boundaries", 2000], ["custom_instructions", "form.field.custom_instructions", 5000],
];

export default function CharacterForm({ character, models, onSave, onCancel }: { character?: Character; models: OllamaModel[]; onSave: (data: {name: string; profile: CharacterProfile}) => Promise<void>; onCancel: () => void }) {
  const { t, lang } = useI18n();
  const [available, setAvailable] = useState<OllamaModel[]>(() => chatModels(models));
  const [name, setName] = useState(character?.name || "");
  const [profile, setProfile] = useState<CharacterProfile>({ ...profileDefaults[lang], ...character?.profile });
  const [model, setModel] = useState(available.find(m => m.name === "llama3.1:8b")?.name || available[0]?.name || "");
  useEffect(() => {
    if (models.length) { setAvailable(chatModels(models)); return; }
    let live = true;
    void api.getModels().then(data => { if (live) setAvailable(chatModels(data.models)); }).catch(() => undefined);
    return () => { live = false; };
  }, [models]);
  useEffect(() => {
    if (!model && available.length) setModel(available.find(m => m.name === "llama3.1:8b")?.name || available[0].name);
  }, [available, model]);
  const [direction, setDirection] = useState(t("form.enhance.directionDefault"));
  const [draft, setDraft] = useState<CharacterProfile | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const enhance = async () => {
    setBusy(t("form.enhance.busy")); setError("");
    try { const result = await api.request<{profile: CharacterProfile}>("/api/character-drafts/enhance", { method: "POST", body: JSON.stringify({ name, profile, model, direction }) }); setDraft(result.profile); }
    catch (e) { setError(e instanceof Error ? e.message : t("form.enhance.error")); } finally { setBusy(""); }
  };
  return <div className="character-editor"><header><div><span className="eyebrow">PERSONALITY</span><h2>{character ? t("form.title.edit", { name: character.name }) : t("form.title.new")}</h2></div><button onClick={onCancel} disabled={!!busy} aria-label={t("common.close")}>×</button></header>
    <form onSubmit={async e => { e.preventDefault(); setBusy(t("form.saving")); setError(""); try { await onSave({ name, profile }); } catch (err) { setError(String(err)); } finally { setBusy(""); } }}>
      <fieldset disabled={!!busy}><div className="editor-identity"><label>{t("form.name")}<input autoFocus value={name} onChange={e => setName(e.target.value)} required maxLength={120} /></label><label>{t("form.language")}<select value={profile.language} onChange={e => setProfile(p => ({ ...p, language: e.target.value }))}><option value="it">Italiano</option><option value="en">English</option><option value="fr">Français</option><option value="de">Deutsch</option><option value="es">Español</option></select></label></div>
        <div className="profile-fields">{fields.map(([key, labelKey, max]) => <label key={key}>{t(labelKey)}<textarea value={profile[key]} onChange={e => setProfile(p => ({ ...p, [key]: e.target.value }))} rows={key === "description" ? 3 : 2} maxLength={max} required={key === "description"} /></label>)}</div>
        <p className="muted">{t("form.appearanceNote")}</p>
        <div className="enhance-box"><h3>{t("form.enhance.title")}</h3><label>{t("form.enhance.model")}<select value={model} onChange={e => setModel(e.target.value)}>{!available.length && <option value="">{t("pg.chooseModel")}</option>}{available.map(m => <option key={m.name} value={m.name}>{m.name}</option>)}</select></label><label>{t("form.enhance.direction")}<textarea rows={2} value={direction} onChange={e => setDirection(e.target.value)} maxLength={2000} /></label><button type="button" disabled={!name.trim() || !profile.description.trim() || !model} onClick={() => void enhance()}>{t("form.enhance.generate")}</button><small>{t("form.enhance.note")}</small></div>
      </fieldset>
      {busy && <p className="memory-status" role="status"><span className="spinner" />{busy}</p>}{error && <p className="warning" role="alert">{error}</p>}
      {draft && <div className="draft-preview"><h3>{t("form.draft.title")}</h3>{fields.map(([key, labelKey]) => <div key={key}><strong>{t(labelKey)}</strong><p>{draft[key]}</p></div>)}<div className="modal-actions"><button type="button" disabled={!!busy} onClick={() => setDraft(null)}>{t("form.draft.discard")}</button><button className="primary" type="button" disabled={!!busy} onClick={() => { setProfile(draft); setDraft(null); }}>{t("form.draft.apply")}</button></div></div>}
      <div className="modal-actions sticky-actions"><button type="button" disabled={!!busy} onClick={onCancel}>{t("common.cancel")}</button><button className="primary" disabled={!!busy}>{t("form.save")}</button></div>
    </form>
  </div>;
}
