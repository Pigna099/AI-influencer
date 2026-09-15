import { useEffect, useRef, useState } from "react";
import { api, Character, CharacterProfile, OllamaModel } from "../api";
import { useI18n, TranslationKey } from "../i18n";

type Sample = {
  id: string;
  batch_id: string;
  model: string;
  prompt: string;
  response: string;
  metrics: {
    request_seconds: number;
    load_duration?: number;
    eval_count?: number;
    eval_duration?: number;
    profile_label?: string;
    profile_custom?: boolean;
  };
  error: string | null;
};
type Variant = { id: string; label: string; profile: CharacterProfile; open: boolean };
type Group = { key: string; label: string; model: string; count: number; errors: number; mean: number | null; load: number | null };

const scenarioKeys: [TranslationKey, TranslationKey][] = [
  ["bench.scenario.natural", "bench.prompt.natural"],
  ["bench.scenario.flirt", "bench.prompt.flirt"],
  ["bench.scenario.memory", "bench.prompt.memory"],
  ["bench.scenario.limits", "bench.prompt.limits"],
];
const variantFields: [keyof CharacterProfile, TranslationKey, number][] = [
  ["description", "bench.field.description", 5000],
  ["personality_traits", "bench.field.personality_traits", 2000],
  ["tone_of_voice", "bench.field.tone_of_voice", 1000],
  ["speech_style", "bench.field.speech_style", 1000],
  ["custom_instructions", "bench.field.custom_instructions", 5000],
];
const newId = () => globalThis.crypto?.randomUUID?.() || `variant-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;

export default function BenchmarkPanel({ character, fanId, models, onBusy }: { character?: Character; fanId: string; models: OllamaModel[]; onBusy: (value: string) => void }) {
  const { t } = useI18n();
  const [selected, setSelected] = useState<string[]>([]);
  const [prompt, setPrompt] = useState(t("bench.prompt.natural"));
  const [repeats, setRepeats] = useState(2);
  const [temperature, setTemperature] = useState(0.7);
  const [variants, setVariants] = useState<Variant[]>([]);
  const [results, setResults] = useState<Sample[]>([]);
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState("");
  const [seconds, setSeconds] = useState(0);
  const [error, setError] = useState("");
  const [batch, setBatch] = useState("");
  const stop = useRef(false);
  const savedLabel = t("bench.saved", { version: character?.version ?? 1 });
  useEffect(() => {
    if (!running) return;
    const start = Date.now(); const timer = window.setInterval(() => setSeconds((Date.now() - start) / 1000), 200);
    return () => window.clearInterval(timer);
  }, [running]);
  useEffect(() => { setVariants([]); setResults([]); setBatch(""); setError(""); }, [character?.id]);
  const addVariant = () => {
    if (!character) return;
    const letter = String.fromCharCode(65 + variants.length);
    setVariants(prev => [...prev, { id: newId(), label: t("bench.variantLabel", { letter }), profile: { ...character.profile }, open: true }]);
  };
  const patchVariant = (id: string, patch: Partial<Variant> & { field?: keyof CharacterProfile; value?: string }) => {
    setVariants(prev => prev.map(variant => {
      if (variant.id !== id) return variant;
      const { field, value, ...rest } = patch;
      return { ...variant, ...rest, profile: field !== undefined ? { ...variant.profile, [field]: value ?? "" } : variant.profile };
    }));
  };
  const run = async () => {
    if (!character || !fanId || !selected.length) return;
    const batchId = newId(); setBatch(batchId); setResults([]); setError(""); setRunning(true); stop.current = false;
    onBusy(t("pg.tab.benchmark"));
    const plan = [{ id: "saved", label: savedLabel, profile: null }, ...variants];
    const total = plan.length * selected.length * repeats;
    try {
      let index = 0;
      for (const variant of plan) for (const model of selected) for (let i = 0; i < repeats; i++) {
        if (stop.current) return;
        setProgress(t("bench.progress", { index: ++index, total, variant: variant.label, model, run: i + 1 }));
        try {
          const sample = await api.request<Sample>("/api/benchmarks", { method: "POST", body: JSON.stringify({ batch_id: batchId, character_id: character.id, fan_id: fanId, model, prompt, temperature, label: variant.label, ...(variant.profile ? { profile: variant.profile } : {}) }) });
          setResults(prev => [...prev, sample]);
        } catch (e) { setError(e instanceof Error ? e.message : t("bench.failed")); }
      }
    } finally { setRunning(false); setProgress(""); onBusy(""); }
  };
  const groupKey = (sample: Sample) => `${sample.metrics.profile_label || savedLabel}\u0000${sample.model}`;
  const groups: Group[] = Array.from(new Set(results.map(groupKey))).map(key => {
    const [label, model] = key.split("\u0000");
    const samples = results.filter(r => groupKey(r) === key), valid = samples.filter(r => !r.error);
    return { key, label, model, count: valid.length, errors: samples.length - valid.length,
      mean: valid.length ? valid.reduce((sum, r) => sum + r.metrics.request_seconds, 0) / valid.length : null,
      load: valid.length ? valid.reduce((sum, r) => sum + (r.metrics.load_duration || 0) / 1e9, 0) / valid.length : null };
  });
  const comparePersonalities = variants.length > 0;
  return <section className="benchmark-panel"><div className="benchmark-intro"><h3>{t("bench.title")}</h3><p>{t("bench.intro")}</p></div>
    <fieldset disabled={running}><legend>{t("bench.models")}</legend><div className="model-checks">{models.map(m => <label key={m.name}><input type="checkbox" checked={selected.includes(m.name)} onChange={e => setSelected(prev => e.target.checked ? [...prev, m.name] : prev.filter(x => x !== m.name))} /><span>{m.name}<small>{m.parameter_size} · {(m.size / 1e9).toFixed(1)} GB</small></span></label>)}</div></fieldset>
    <fieldset disabled={running}><legend>{t("bench.variants")}</legend>
      <p className="muted">{t("bench.variants.note")}</p>
      <div className="variant-list">
        <article className="variant-saved"><strong>{savedLabel}</strong><small>{t("bench.readonly")}</small></article>
        {variants.map(variant => <article className="variant-card" key={variant.id}>
          <header><input aria-label={t("bench.variantName", { label: variant.label })} value={variant.label} maxLength={120} onChange={e => patchVariant(variant.id, { label: e.target.value })} /><button type="button" onClick={() => patchVariant(variant.id, { open: !variant.open })} disabled={running}>{variant.open ? t("common.close") : t("common.edit")}</button><button type="button" className="danger" aria-label={t("bench.removeVariant", { label: variant.label })} onClick={() => setVariants(prev => prev.filter(item => item.id !== variant.id))} disabled={running}>×</button></header>
          {variant.open && <div className="variant-fields">{variantFields.map(([field, labelKey, max]) => <label key={field}>{t(labelKey)}<textarea rows={2} value={variant.profile[field]} maxLength={max} onChange={e => patchVariant(variant.id, { field, value: e.target.value })} /></label>)}</div>}
        </article>)}
      </div>
      <button type="button" disabled={!character || running} onClick={addVariant}>{t("bench.addVariant")}</button>
    </fieldset>
    <fieldset disabled={running}>
      <label className="block-label">{t("bench.scenario")}<select aria-label={t("bench.scenario")} onChange={e => setPrompt(e.target.value)} defaultValue={t("bench.prompt.natural")}>{scenarioKeys.map(([nameKey, promptKey]) => <option key={nameKey} value={t(promptKey)}>{t(nameKey)}</option>)}</select></label>
      <label className="block-label">{t("bench.message")}<textarea rows={3} value={prompt} onChange={e => setPrompt(e.target.value)} maxLength={4000} /></label>
      <div className="benchmark-options"><label>{t("bench.repeats")}<select value={repeats} onChange={e => setRepeats(Number(e.target.value))}>{[1,2,3,5].map(n => <option key={n}>{n}</option>)}</select></label><label>{t("bench.temperature")}<input type="number" min="0" max="2" step="0.1" value={temperature} onChange={e => setTemperature(Number(e.target.value))} /></label><button className="primary" disabled={!character || !fanId || !selected.length || !prompt.trim()} onClick={() => void run()}>{t("bench.run")}</button></div>
    </fieldset>
    {comparePersonalities && <p className="muted">{t("bench.matrix", { personalities: variants.length + 1, models: selected.length || 0, repeats })}</p>}
    {running && <div className="benchmark-progress" role="status"><span className="spinner" /><span>{progress} · {t("bench.elapsed", { seconds: seconds.toFixed(0) })}</span><button onClick={() => { stop.current = true; setProgress(t("bench.stopping")); }}>{t("bench.stop")}</button></div>}
    {error && <p className="warning" role="alert">{error}</p>}
    <p className="muted">{t("bench.note")}</p>
    {groups.length > 0 && <div className="comparison-table"><table><thead><tr>{comparePersonalities && <th>{t("bench.personality")}</th>}<th>{t("bench.model")}</th><th>{t("bench.mean")}</th><th>{t("bench.load")}</th><th>{t("bench.results")}</th></tr></thead><tbody>{groups.map(g => <tr key={g.key}>{comparePersonalities && <td>{g.label}</td>}<td>{g.model}</td><td>{g.mean == null ? "—" : `${g.mean.toFixed(2)} s`}</td><td>{g.load == null ? "—" : `${g.load.toFixed(2)} s`}</td><td>{g.count} / {g.errors}</td></tr>)}</tbody></table></div>}
    <div className="sample-results">{results.map((r, i) => <article key={r.id}><header><strong>{r.metrics.profile_label || savedLabel} · {r.model}</strong><span>{i + 1} · {r.metrics.request_seconds.toFixed(2)} s</span></header><p>{r.error || r.response}</p>{r.error && <span className="warning">{t("bench.failedRun")}</span>}</article>)}</div>
    <div className="benchmark-footer"><button disabled={running} onClick={async () => { try { const saved = await api.request<Sample[]>("/api/benchmarks"); if (!saved.length) { setError(t("bench.noSaved")); return; } const latest = saved[0].batch_id; setBatch(latest); setResults(saved.filter(s => s.batch_id === latest)); } catch (e) { setError(String(e)); } }}>{t("bench.loadLast")}</button>{results.length > 0 && <button onClick={() => { const file = new Blob([JSON.stringify({ batch, results }, null, 2)], { type: "application/json" }); const url = URL.createObjectURL(file); const a = document.createElement("a"); a.href = url; a.download = "model-comparison.json"; a.click(); URL.revokeObjectURL(url); }}>{t("bench.export")}</button>}</div>
  </section>;
}
