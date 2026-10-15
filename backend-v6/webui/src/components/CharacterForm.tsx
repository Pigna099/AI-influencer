import { useEffect, useState } from "react";
import { api, CharacterProfile, Character, OllamaModel } from "../api";
import { useI18n, TranslationKey } from "../i18n";

const chatModels = (models: OllamaModel[]) => models.filter(m => m.chat_capable !== false && (m.kind ? m.kind === "chat" : !m.name.toLowerCase().includes("embed")) && !m.name.toLowerCase().includes("embed"));

const profileDefaults: CharacterProfile = { description: "", appearance: "", background: "", personality_traits: "curious, playful, proactive", tone_of_voice: "warm, spontaneous, lightly flirtatious", speech_style: "Short, natural messages, one question at a time", vocabulary: "", likes: "", dislikes: "", boundaries: "Adults, consensual and non-explicit flirting; respect boundaries", relationship_style: "Playful and independent, no pressure", language: "en", custom_instructions: "Take initiative and suggest topics that match the fan's interests." };

const fields: [keyof CharacterProfile, TranslationKey, number][] = [
  ["description", "form.field.description", 5000], ["appearance", "form.field.appearance", 2000], ["personality_traits", "form.field.personality_traits", 2000],
  ["tone_of_voice", "form.field.tone_of_voice", 1000], ["speech_style", "form.field.speech_style", 1000], ["background", "form.field.background", 5000],
  ["likes", "form.field.likes", 2000], ["dislikes", "form.field.dislikes", 2000], ["vocabulary", "form.field.vocabulary", 1000],
  ["relationship_style", "form.field.relationship_style", 1000], ["boundaries", "form.field.boundaries", 2000], ["custom_instructions", "form.field.custom_instructions", 5000],
];

export default function CharacterForm({ character, models, onSave, onCancel }: { character?: Character; models: OllamaModel[]; onSave: (data: {name: string; profile: CharacterProfile; age?: number | null; synthetic_declared?: boolean; provenance?: string; source_category?: string; rights_notes?: string; permitted_uses?: string; lifecycle_state?: string; platform_policy?: {platforms: Record<string, {ai_disclosure: boolean; terms_reviewed: boolean; content_rules_ok: boolean}>}}) => Promise<void>; onCancel: () => void }) {
  const { t } = useI18n();
  const [available, setAvailable] = useState<OllamaModel[]>(() => chatModels(models));
  const [name, setName] = useState(character?.name || "");
  const [age, setAge] = useState(character?.age != null ? String(character.age) : "");
  const [synthetic, setSynthetic] = useState(character?.synthetic_declared ?? true);
  const [provenance, setProvenance] = useState(character?.provenance || "synthetic");
  const [sourceCategory, setSourceCategory] = useState(character?.source_category || "generated");
  const [rightsNotes, setRightsNotes] = useState(character?.rights_notes || "");
  const [permittedUses, setPermittedUses] = useState(character?.permitted_uses || "");
  const [lifecycle, setLifecycle] = useState(character?.lifecycle_state || "active");
  const [platformPolicy, setPlatformPolicy] = useState<Record<string, { ai_disclosure: boolean; terms_reviewed: boolean; content_rules_ok: boolean }>>(
    () => (character?.platform_policy?.platforms as Record<string, { ai_disclosure: boolean; terms_reviewed: boolean; content_rules_ok: boolean }>) || {},
  );
  const setPlatformCheck = (platform: string, key: "ai_disclosure" | "terms_reviewed" | "content_rules_ok", value: boolean) => {
    setPlatformPolicy(current => {
      const next = { ...current };
      if (key === "ai_disclosure" && !value && !next[platform]?.terms_reviewed && !next[platform]?.content_rules_ok) {
        delete next[platform];
        return next;
      }
      next[platform] = {
        ai_disclosure: next[platform]?.ai_disclosure ?? false,
        terms_reviewed: next[platform]?.terms_reviewed ?? false,
        content_rules_ok: next[platform]?.content_rules_ok ?? false,
        [key]: value,
      };
      return next;
    });
  };
  const [profile, setProfile] = useState<CharacterProfile>({ ...profileDefaults, ...character?.profile });
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
    <form onSubmit={async e => { e.preventDefault(); setBusy(t("form.saving")); setError(""); try { await onSave({ name, profile, age: age.trim() ? Number(age) : null, synthetic_declared: synthetic, provenance, source_category: sourceCategory, rights_notes: rightsNotes, permitted_uses: permittedUses, lifecycle_state: lifecycle, platform_policy: { platforms: platformPolicy } }); } catch (err) { setError(String(err)); } finally { setBusy(""); } }}>
      <fieldset disabled={!!busy}><div className="editor-identity"><label>{t("form.name")}<input autoFocus value={name} onChange={e => setName(e.target.value)} required maxLength={120} /></label><label>{t("form.language")}<select value={profile.language} onChange={e => setProfile(p => ({ ...p, language: e.target.value }))}><option value="it">Italiano</option><option value="en">English</option><option value="fr">Français</option><option value="de">Deutsch</option><option value="es">Español</option></select></label></div>
        <div className="editor-identity">
          <label>{t("form.age")}<input type="number" min={21} max={99} value={age} onChange={e => setAge(e.target.value)} placeholder="21+" /></label>
          <label>{t("form.provenance")}<select value={provenance} onChange={e => setProvenance(e.target.value)}>
            <option value="synthetic">{t("form.provenance.synthetic")}</option>
            <option value="original">{t("form.provenance.original")}</option>
            <option value="consented">{t("form.provenance.consented")}</option>
          </select></label>
        </div>
        <label className="auto-label policy-declaration"><input type="checkbox" checked={synthetic} onChange={e => setSynthetic(e.target.checked)} /> {t("form.syntheticDeclaration")}</label>
        <div className="editor-identity">
          <label>{t("form.sourceCategory")}<select value={sourceCategory} onChange={e => setSourceCategory(e.target.value)}>
            <option value="generated">{t("form.source.generated")}</option>
            <option value="owned">{t("form.source.owned")}</option>
            <option value="consented">{t("form.source.consented")}</option>
            <option value="reference_only">{t("form.source.referenceOnly")}</option>
          </select></label>
          <label>{t("form.lifecycle")}<select value={lifecycle} onChange={e => setLifecycle(e.target.value)}>
            <option value="draft">{t("form.lifecycle.draft")}</option>
            <option value="active">{t("form.lifecycle.active")}</option>
            <option value="retired">{t("form.lifecycle.retired")}</option>
          </select></label>
        </div>
        {sourceCategory === "reference_only" && <p className="warning" role="note">{t("form.referenceOnlyWarning")}</p>}
        <div className="editor-identity">
          <label>{t("form.rightsNotes")}<textarea rows={2} value={rightsNotes} onChange={e => setRightsNotes(e.target.value)} maxLength={4000} /></label>
          <label>{t("form.permittedUses")}<input value={permittedUses} onChange={e => setPermittedUses(e.target.value)} maxLength={300} /></label>
        </div>
        <fieldset className="platform-policy">
          <legend>{t("form.platformPolicy")}</legend>
          <p className="muted">{t("form.platformPolicyHint")}</p>
          {["instagram", "fanvue", "x", "reddit", "tiktok"].map(platform => <div className="platform-row" key={platform}>
            <strong>{platform}</strong>
            <label className="auto-label"><input type="checkbox" checked={platform in platformPolicy} onChange={e => setPlatformCheck(platform, "ai_disclosure", e.target.checked)} /> {t("form.platform.inUse")}</label>
            <label className="auto-label"><input type="checkbox" disabled={!(platform in platformPolicy)} checked={platformPolicy[platform]?.ai_disclosure || false} onChange={e => setPlatformCheck(platform, "ai_disclosure", e.target.checked)} /> {t("form.platform.aiDisclosure")}</label>
            <label className="auto-label"><input type="checkbox" disabled={!(platform in platformPolicy)} checked={platformPolicy[platform]?.terms_reviewed || false} onChange={e => setPlatformCheck(platform, "terms_reviewed", e.target.checked)} /> {t("form.platform.terms")}</label>
            <label className="auto-label"><input type="checkbox" disabled={!(platform in platformPolicy)} checked={platformPolicy[platform]?.content_rules_ok || false} onChange={e => setPlatformCheck(platform, "content_rules_ok", e.target.checked)} /> {t("form.platform.rules")}</label>
          </div>)}
          {Object.entries(platformPolicy).some(([, checks]) => !checks.ai_disclosure) && <p className="warning" role="note">{t("form.platform.warning")}</p>}
        </fieldset>
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
