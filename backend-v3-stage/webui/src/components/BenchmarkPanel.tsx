import { useEffect, useRef, useState } from "react";
import { api, Character, OllamaModel } from "../api";

type Sample = { id: string; batch_id: string; model: string; prompt: string; response: string; metrics: { request_seconds: number; load_duration?: number; eval_count?: number; eval_duration?: number }; error: string | null };
const scenarios = [
  ["Conversazione naturale", "Ciao, oggi è stata una giornata lunghissima. Ho voglia di staccare un po’, tu cosa mi racconti?"],
  ["Flirt leggero", "Mi piace il tuo modo di stuzzicarmi. Vediamo se riesci a farmi sorridere anche stasera 😉"],
  ["Richiamo della memoria", "Ti ricordi qualcosa dei miei gusti? Proponimi qualcosa che mi potrebbe piacere, senza inventare."],
  ["Rispetto dei limiti", "Mi piace parlare con te, ma oggi non voglio comprare nulla. Possiamo semplicemente chiacchierare?"],
];

export default function BenchmarkPanel({ character, fanId, models, onBusy }: { character?: Character; fanId: string; models: OllamaModel[]; onBusy: (value: string) => void }) {
  const [selected, setSelected] = useState<string[]>([]);
  const [prompt, setPrompt] = useState(scenarios[0][1]);
  const [repeats, setRepeats] = useState(2);
  const [temperature, setTemperature] = useState(0.7);
  const [results, setResults] = useState<Sample[]>([]);
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState("");
  const [seconds, setSeconds] = useState(0);
  const [error, setError] = useState("");
  const [batch, setBatch] = useState("");
  const stop = useRef(false);
  useEffect(() => {
    if (!running) return;
    const start = Date.now(); const timer = window.setInterval(() => setSeconds((Date.now() - start) / 1000), 200);
    return () => window.clearInterval(timer);
  }, [running]);
  const run = async () => {
    if (!character || !fanId || !selected.length) return;
    const batchId = globalThis.crypto?.randomUUID?.() || `run-${Date.now()}-${Math.random().toString(36).slice(2,10)}`; setBatch(batchId); setResults([]); setError(""); setRunning(true); stop.current = false;
    onBusy("Confronto modelli in corso");
    const total = selected.length * repeats;
    try {
      let index = 0;
      for (const model of selected) for (let i = 0; i < repeats; i++) {
        if (stop.current) return;
        setProgress(`${++index}/${total} · ${model} · prova ${i + 1}`);
        try {
          const sample = await api.request<Sample>("/api/benchmarks", { method: "POST", body: JSON.stringify({ batch_id: batchId, character_id: character.id, fan_id: fanId, model, prompt, temperature }) });
          setResults(prev => [...prev, sample]);
        } catch (e) { setError(e instanceof Error ? e.message : "Confronto non riuscito"); }
      }
    } finally { setRunning(false); setProgress(""); onBusy(""); }
  };
  const groups = Array.from(new Set(results.map(r => r.model))).map(model => {
    const samples = results.filter(r => r.model === model), valid = samples.filter(r => !r.error);
    return { model, count: valid.length, errors: samples.length - valid.length,
      mean: valid.length ? valid.reduce((sum, r) => sum + r.metrics.request_seconds, 0) / valid.length : null,
      load: valid.length ? valid.reduce((sum, r) => sum + (r.metrics.load_duration || 0) / 1e9, 0) / valid.length : null };
  });
  return <section className="benchmark-panel"><div className="benchmark-intro"><h3>Stesso messaggio. Modelli diversi.</h3><p>Ogni prova parte senza cronologia, con la stessa personalità e i ricordi del fan selezionato. Le risposte restano separate dalle chat.</p></div>
    <fieldset disabled={running}><legend>Modelli da confrontare</legend><div className="model-checks">{models.map(m => <label key={m.name}><input type="checkbox" checked={selected.includes(m.name)} onChange={e => setSelected(prev => e.target.checked ? [...prev, m.name] : prev.filter(x => x !== m.name))} /><span>{m.name}<small>{m.parameter_size} · {(m.size / 1e9).toFixed(1)} GB</small></span></label>)}</div>
      <label className="block-label">Scenario<select aria-label="Scenario confronto" onChange={e => setPrompt(e.target.value)} defaultValue={scenarios[0][1]}>{scenarios.map(([name, text]) => <option key={name} value={text}>{name}</option>)}</select></label>
      <label className="block-label">Messaggio uguale per tutti<textarea rows={3} value={prompt} onChange={e => setPrompt(e.target.value)} maxLength={4000} /></label>
      <div className="benchmark-options"><label>Prove per modello<select value={repeats} onChange={e => setRepeats(Number(e.target.value))}>{[1,2,3,5].map(n => <option key={n}>{n}</option>)}</select></label><label>Temperatura<input type="number" min="0" max="2" step="0.1" value={temperature} onChange={e => setTemperature(Number(e.target.value))} /></label><button className="primary" disabled={!character || !fanId || !selected.length || !prompt.trim()} onClick={() => void run()}>Avvia confronto</button></div>
    </fieldset>
    {running && <div className="benchmark-progress" role="status"><span className="spinner" /><span>{progress} · {seconds.toFixed(0)} s trascorsi</span><button onClick={() => { stop.current = true; setProgress("Interruzione dopo la prova in corso"); }}>Ferma dopo questa prova</button></div>}
    {error && <p className="warning" role="alert">{error}</p>}
    <p className="muted">Prove in sequenza: 512 token, oppure 2048 per modelli che richiedono ragionamento; contesto di 8192 token. La media include il caricamento: una prima prova a freddo può essere più lenta. La qualità si valuta leggendo le risposte, non dal tempo.</p>
    {groups.length > 0 && <div className="comparison-table"><table><thead><tr><th>Modello</th><th>Media totale</th><th>Carico medio</th><th>Riuscite / errori</th></tr></thead><tbody>{groups.map(g => <tr key={g.model}><td>{g.model}</td><td>{g.mean == null ? "—" : `${g.mean.toFixed(2)} s`}</td><td>{g.load == null ? "—" : `${g.load.toFixed(2)} s`}</td><td>{g.count} / {g.errors}</td></tr>)}</tbody></table></div>}
    <div className="sample-results">{results.map((r, i) => <article key={r.id}><header><strong>{r.model}</strong><span>Prova {i + 1} · {r.metrics.request_seconds.toFixed(2)} s</span></header><p>{r.error || r.response}</p>{r.error && <span className="warning">Prova fallita, esclusa dalla media</span>}</article>)}</div>
    <div className="benchmark-footer"><button disabled={running} onClick={async () => { try { const saved = await api.request<Sample[]>("/api/benchmarks"); if (!saved.length) { setError("Non ci sono confronti salvati."); return; } const latest = saved[0].batch_id; setBatch(latest); setResults(saved.filter(s => s.batch_id === latest)); } catch (e) { setError(String(e)); } }}>Carica ultimo confronto</button>{results.length > 0 && <button onClick={() => { const file = new Blob([JSON.stringify({ batch, results }, null, 2)], { type: "application/json" }); const url = URL.createObjectURL(file); const a = document.createElement("a"); a.href = url; a.download = "confronto-modelli.json"; a.click(); URL.revokeObjectURL(url); }}>Esporta risultati</button>}</div>
  </section>;
}
