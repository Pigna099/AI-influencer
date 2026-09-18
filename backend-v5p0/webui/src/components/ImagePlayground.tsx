import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, Character, CharacterLora, CheckpointInfo, GenerationPreset, LibraryImage, PoseReference } from "../api";
import { useI18n, LanguageSwitch } from "../i18n";
import CharacterAvatar from "./CharacterAvatar";
import Lightbox from "./Lightbox";
import PoseLibrary from "./PoseLibrary";

type LoraSelection = { on: boolean; weight: number; clip?: number | null; category?: string };

const LORA_CATEGORIES = ["character", "style", "outfit", "composition", "other"] as const;
const SDXL_FAMILIES = ["real", "pony", "anime", "playground"];

function LibraryThumb({ item, onView, alt }: { item: LibraryImage; onView: (url: string, alt: string) => void; alt: string }) {
  const [url, setUrl] = useState("");
  useEffect(() => {
    let objectUrl = "";
    let alive = true;
    setUrl("");
    api.fetchBlob(`/api/library/${item.id}/file?v=${encodeURIComponent(item.filename)}`)
      .then(blob => {
        if (!alive) return;
        objectUrl = URL.createObjectURL(blob);
        setUrl(objectUrl);
      })
      .catch(() => setUrl(""));
    return () => {
      alive = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [item.id, item.filename]);
  if (!url) return <div className="library-loading"><span className="spinner" /></div>;
  return <img src={url} alt={alt} loading="lazy" onClick={() => onView(url, alt)} />;
}

export default function ImagePlayground({ onLogout }: { onLogout: () => void }) {
  const { t } = useI18n();
  const [characters, setCharacters] = useState<Character[]>([]);
  const [characterId, setCharacterId] = useState("");
  const [library, setLibrary] = useState<LibraryImage[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [checkpoints, setCheckpoints] = useState<CheckpointInfo[]>([]);
  const [loras, setLoras] = useState<string[]>([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [styleFilter, setStyleFilter] = useState("");
  const [prompt, setPrompt] = useState("");
  const [direction, setDirection] = useState("");
  const [negative, setNegative] = useState("");
  const [style, setStyle] = useState<"real" | "anime">("real");
  const [checkpoint, setCheckpoint] = useState("");
  const [loraSel, setLoraSel] = useState<Record<string, LoraSelection>>({});
  const [loraFamilies, setLoraFamilies] = useState<Record<string, string>>({});
  const [presets, setPresets] = useState<GenerationPreset[]>([]);
  const [presetId, setPresetId] = useState("");
  const [poses, setPoses] = useState<PoseReference[]>([]);
  const [characterLoras, setCharacterLoras] = useState<CharacterLora[]>([]);
  const autoApplied = useRef<Set<string>>(new Set());
  const [poseIds, setPoseIds] = useState<string[]>([]);
  const [poseStrength, setPoseStrength] = useState("0.8");
  const [count, setCount] = useState(2);
  const [seed, setSeed] = useState("");
  const [classify, setClassify] = useState(false);
  const [busy, setBusy] = useState("");
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState("");
  const [viewer, setViewer] = useState<{ url: string; alt: string } | null>(null);
  const [panelWidth, setPanelWidth] = useState(() => {
    const stored = Number(localStorage.getItem("ip_panel_width"));
    return Number.isFinite(stored) && stored >= 280 && stored <= 700 ? stored : 380;
  });
  const generation = useRef(0);
  const character = characters.find(item => item.id === characterId);

  const startResize = (event: React.MouseEvent) => {
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = panelWidth;
    const onMove = (move: MouseEvent) => {
      const next = Math.min(700, Math.max(280, startWidth + (startX - move.clientX)));
      setPanelWidth(next);
      localStorage.setItem("ip_panel_width", String(next));
    };
    const onUp = () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  };

  useEffect(() => {
    let live = true;
    Promise.all([api.getCharacters(), api.getCheckpoints(), api.getLoras(), api.getPoses(), api.getPresets()])
      .then(([chars, checkpointData, loraData, poseData, presetData]) => {
        if (!live) return;
        setCharacters(chars);
        setCheckpoints(checkpointData.checkpoints);
        setLoras(loraData.loras);
        setLoraFamilies(loraData.families ?? {});
        setPoses(poseData);
        setPresets(presetData);
        setLoraSel(Object.fromEntries(loraData.loras.map(name => [name, { on: false, weight: 0.8, clip: null, category: "other" }])));
        const first = chars[0];
        if (first) {
          setCharacterId(first.id);
          setStyle(first.image_style || "real");
          setCheckpoint(first.image_checkpoint || "");
        }
      })
      .catch(e => { if (live) setError(e instanceof Error ? e.message : t("common.failed")); });
    return () => { live = false; };
  }, []);

  const refreshPoses = useCallback(async () => {
    setPoses(await api.getPoses());
  }, []);

  useEffect(() => {
    if (!characterId) { setCharacterLoras([]); return; }
    let live = true;
    api.getCharacterLoras(characterId)
      .then(items => { if (live) setCharacterLoras(items); })
      .catch(() => undefined);
    return () => { live = false; };
  }, [characterId]);

  const checkpointFamily = checkpoints.find(item => item.name === checkpoint)?.family ?? (style === "anime" ? "anime" : "real");
  const activeCharacterLora = characterLoras.find(item => item.is_active && item.filename && (SDXL_FAMILIES.includes(checkpointFamily) ? SDXL_FAMILIES.includes(item.family) : item.family === checkpointFamily));
  const compatibleLoras = loras.filter(name => {
    const family = loraFamilies[name] ?? "sdxl";
    if (SDXL_FAMILIES.includes(checkpointFamily)) return family === "sdxl" || SDXL_FAMILIES.includes(family);
    return family === checkpointFamily;
  });
  const hiddenLoras = loras.length - compatibleLoras.length;

  useEffect(() => {
    if (!characterId || !activeCharacterLora?.filename) return;
    const key = `${characterId}:${checkpointFamily}:${checkpoint || "default"}`;
    if (autoApplied.current.has(key)) return;
    autoApplied.current.add(key);
    const name = activeCharacterLora.filename;
    setLoraSel(prev => ({ ...prev, [name]: { on: true, weight: prev[name]?.weight ?? 0.85, clip: prev[name]?.clip ?? null, category: "character" } }));
  }, [characterId, checkpointFamily, checkpoint, activeCharacterLora]);

  const refresh = useCallback(async (id: string) => {
    if (!id) { setLibrary([]); return; }
    setSelectedIds([]);
    const epoch = generation.current;
    const items = await api.getLibrary(id, { status: statusFilter, style: styleFilter });
    if (epoch === generation.current) setLibrary(items);
  }, [statusFilter, styleFilter]);

  useEffect(() => {
    void refresh(characterId).catch(() => undefined);
  }, [characterId, refresh]);

  useEffect(() => {
    if (!busy) { setElapsed(0); return; }
    const start = Date.now();
    const timer = window.setInterval(() => setElapsed((Date.now() - start) / 1000), 200);
    return () => window.clearInterval(timer);
  }, [busy]);

  const selectCharacter = (item: Character) => {
    generation.current += 1;
    setCharacterId(item.id);
    setStyle(item.image_style || "real");
    setCheckpoint(item.image_checkpoint || "");
  };

  const updateItem = (updated: LibraryImage) => {
    setLibrary(prev => prev.map(item => (item.id === updated.id ? updated : item)));
  };

  const perform = async (label: string, work: () => Promise<void>) => {
    if (busy) return;
    setBusy(label); setError("");
    try { await work(); } catch (e) { setError(e instanceof Error ? e.message : t("common.failed")); } finally { setBusy(""); }
  };

  const augment = () => {
    if (!character || !prompt.trim()) return;
    void perform(t("ip.augmenting"), async () => {
      const result = await api.augmentPrompt(character.id, { prompt: prompt.trim(), style, direction: direction.trim() });
      setPrompt(result.prompt);
    });
  };

  const generate = () => {
    if (!character || !prompt.trim()) return;
    void perform(t("ip.generating"), async () => {
      const selectedLoras = Object.entries(loraSel)
        .filter(([, value]) => value.on)
        .map(([name, value]) => ({ name, weight: value.weight, clip_weight: value.clip ?? undefined, category: value.category }));
      const items = await api.generateLibraryImages(character.id, {
        prompt: prompt.trim(),
        negative: negative.trim() || undefined,
        style,
        checkpoint: checkpoint || undefined,
        loras: selectedLoras,
        pose_ids: poseIds,
        pose_strength: Number(poseStrength),
        count,
        seed: seed.trim() ? Number(seed) : undefined,
        classify,
      });
      setLibrary(prev => [...items, ...prev]);
    });
  };

  const applyPreset = () => {
    const preset = presets.find(item => item.id === presetId);
    if (!preset) return;
    const payload = preset.payload as {
      prompt?: string; negative?: string; style?: "real" | "anime"; checkpoint?: string;
      loras?: { name: string; weight: number; clip_weight?: number; category?: string }[];
      pose_ids?: string[]; pose_strength?: number; count?: number;
    };
    if (payload.prompt !== undefined) setPrompt(payload.prompt);
    if (payload.negative !== undefined) setNegative(payload.negative);
    if (payload.style) setStyle(payload.style);
    if (payload.checkpoint !== undefined) setCheckpoint(payload.checkpoint);
    if (payload.count) setCount(payload.count);
    if (payload.pose_ids) setPoseIds(payload.pose_ids);
    if (payload.pose_strength !== undefined) setPoseStrength(String(payload.pose_strength));
    if (payload.loras) {
      const next: Record<string, LoraSelection> = {};
      for (const [name, value] of Object.entries(loraSel)) next[name] = { ...value, on: false };
      for (const lora of payload.loras) {
        next[lora.name] = { on: true, weight: lora.weight, clip: lora.clip_weight ?? null, category: lora.category ?? "other" };
      }
      setLoraSel(next);
    }
  };

  const savePreset = () => {
    const name = window.prompt(t("ip.presetName"), "");
    if (!name || !name.trim()) return;
    const selectedLoras = Object.entries(loraSel)
      .filter(([, value]) => value.on)
      .map(([loraName, value]) => ({ name: loraName, weight: value.weight, clip_weight: value.clip ?? undefined, category: value.category }));
    void perform(t("common.save"), async () => {
      const created = await api.createPreset({
        name: name.trim(),
        payload: { prompt, negative, style, checkpoint, loras: selectedLoras, pose_ids: poseIds, pose_strength: Number(poseStrength), count },
      });
      setPresets(prev => [...prev, created]);
      setPresetId(created.id);
    });
  };

  const deletePreset = () => {
    if (!presetId || !window.confirm(t("ip.presetDeleteConfirm"))) return;
    void perform("", async () => {
      await api.deletePreset(presetId);
      setPresets(prev => prev.filter(item => item.id !== presetId));
      setPresetId("");
    });
  };

  const setStatus = (item: LibraryImage, status: "approved" | "rejected" | "draft") =>
    void perform("", async () => updateItem(await api.patchLibraryItem(item.id, { status })));
  const setRating = (item: LibraryImage, rating: number) =>
    void perform("", async () => updateItem(await api.patchLibraryItem(item.id, { rating })));
  const classifyItem = (item: LibraryImage) =>
    void perform(t("ip.classifying"), async () => updateItem(await api.classifyLibraryItem(item.id)));
  const toggleSelectedId = (id: string) => {
    setSelectedIds(prev => prev.includes(id) ? prev.filter(entry => entry !== id) : [...prev, id]);
  };

  const removeSelected = () => {
    if (!selectedIds.length) return;
    if (!window.confirm(t("bulk.confirmDelete", { count: selectedIds.length }))) return;
    void perform("", async () => {
      await api.deleteLibraryItems(selectedIds);
      setLibrary(prev => prev.filter(entry => !selectedIds.includes(entry.id)));
      setSelectedIds([]);
    });
  };

  const removeItem = (item: LibraryImage) => {
    if (!window.confirm(t("ip.deleteConfirm"))) return;
    void perform("", async () => {
      await api.deleteLibraryItem(item.id);
      setLibrary(prev => prev.filter(entry => entry.id !== item.id));
    });
  };

  const statusLabel = (item: LibraryImage) => item.status === "approved" ? t("ip.approved") : item.status === "rejected" ? t("ip.rejected") : t("ip.draft");

  return <div className="playground theme-images">
    <header className="topbar"><div className="brand"><span className="brand-mark">ai</span><h1>AI influencer playground <b>v5</b></h1></div>
      <div className="top-actions">
        <nav className="top-nav"><Link to="/">{t("pg.nav.home")}</Link><Link to="/chat">{t("pg.nav.chat")}</Link><Link className="selected" to="/images">{t("pg.nav.images")}</Link><Link to="/dataset">{t("pg.nav.dataset")}</Link><Link to="/loras">{t("pg.nav.loras")}</Link></nav>
        <LanguageSwitch /><button onClick={onLogout} disabled={!!busy}>{t("pg.logout")}</button>
      </div></header>
    {error && <div className="error-banner" role="alert">{error}<button onClick={() => setError("")} aria-label={t("pg.error.closeAria")}>×</button></div>}
    <div className="workspace image-workspace" style={{ gridTemplateColumns: `225px minmax(320px, 1fr) 6px ${panelWidth}px` }}>
      <aside className="character-rail">
        <div className="section-title"><h2>{t("ip.characters")}</h2><span>{characters.length}</span></div>
        <div className="character-list">{characters.map((item, index) => <button key={item.id} disabled={!!busy} onClick={() => selectCharacter(item)} className={`character-row ${characterId === item.id ? "selected" : ""}`}>
          <CharacterAvatar character={item} index={index} onView={(url, alt) => setViewer({ url, alt })} altTemplate={t("pg.avatarAlt")} /><span><strong>{item.name}</strong><small>{item.image_style === "anime" ? t("pg.style.anime") : t("pg.style.real")}</small></span></button>)}
          {!characters.length && <p className="muted">{t("pg.noCharacters")}</p>}</div>
        <div className="rail-divider" />
        <div className="section-title"><h2>{t("ip.filters")}</h2></div>
        <label className="image-checkpoint">{t("pg.checkpoint")}
          <select value={statusFilter} disabled={!!busy} onChange={e => setStatusFilter(e.target.value)}>
            <option value="">{t("ip.statusAll")}</option><option value="draft">{t("ip.statusDraft")}</option><option value="approved">{t("ip.statusApproved")}</option><option value="rejected">{t("ip.statusRejected")}</option>
          </select>
        </label>
        <label className="image-checkpoint">{t("ip.style")}
          <select value={styleFilter} disabled={!!busy} onChange={e => setStyleFilter(e.target.value)}>
            <option value="">{t("ip.styleAll")}</option><option value="real">{t("pg.style.real")}</option><option value="anime">{t("pg.style.anime")}</option>
          </select>
        </label>
      </aside>
      <main className="main-panel">
        <div className="chat-heading"><div><span className="eyebrow">{character ? t("pg.personalityVersion", { version: character.version }) : t("ip.title")}</span><h2>{character?.name || t("ip.selectCharacter")}</h2><p>{t("ip.subtitle")}</p></div>
          <span className="library-count">{t("ip.imagesCount", { count: library.length })}</span>
        </div>
        <div className="library-scroll">
          <div className="bulk-bar">
            <label><input type="checkbox" disabled={!!busy || !library.length} checked={selectedIds.length > 0 && selectedIds.length === library.length} onChange={e => setSelectedIds(e.target.checked ? library.map(entry => entry.id) : [])} /> {t("bulk.selectAll")}</label>
            <button className="danger" disabled={!!busy || !selectedIds.length} onClick={removeSelected}>{t("bulk.deleteSelected", { count: selectedIds.length })}</button>
          </div>
          {!library.length && <div className="empty-memory"><span>◎</span><p>{t("ip.empty")}</p></div>}
          <div className="library-grid">{library.map(item => <article className={`library-card status-${item.status}`} key={item.id}>
            <div className="library-thumb">
              <LibraryThumb item={item} onView={(url, alt) => setViewer({ url, alt })} alt={item.caption || item.prompt} />
              <span className={`badge ${item.status}`}>{statusLabel(item)}</span>
              <label className="select-check" title={t("bulk.select")}><input type="checkbox" checked={selectedIds.includes(item.id)} disabled={!!busy} onChange={() => toggleSelectedId(item.id)} /></label>
            </div>
            <div className="library-meta">
              <div className="library-stars" role="group" aria-label={t("ip.rating")}>{[1, 2, 3, 4, 5].map(value => <button key={value} className={item.rating >= value ? "on" : ""} disabled={!!busy} onClick={() => setRating(item, value)} aria-label={`${value}/5`}>★</button>)}</div>
              <p>{item.caption || item.prompt}</p>
              {!!item.tags.length && <div className="library-tags">{item.tags.slice(0, 8).map(tag => <span key={tag}>{tag}</span>)}</div>}
              <small>{item.style} · {(item.checkpoint || "").replace(".safetensors", "")} · {t("ip.used")} {item.used_count} · {item.source === "chat" ? t("ip.sourceChat") : t("ip.sourcePlayground")}</small>
              <div className="library-actions">
                <button disabled={!!busy} onClick={() => setStatus(item, item.status === "approved" ? "draft" : "approved")}>{t("ip.approve")}</button>
                <button disabled={!!busy} onClick={() => setStatus(item, item.status === "rejected" ? "draft" : "rejected")}>{t("ip.reject")}</button>
                <button disabled={!!busy} onClick={() => classifyItem(item)}>{t("ip.classifyNow")}</button>
                <button className="danger" disabled={!!busy} onClick={() => removeItem(item)}>{t("common.delete")}</button>
              </div>
            </div>
          </article>)}</div>
        </div>
      </main>
      <div className="panel-resizer" role="separator" aria-orientation="vertical" title={t("ip.resizePanel")} onMouseDown={startResize} />
      <aside className="inspector image-inspector">
        <div className="section-title"><h2>{t("ip.generatePanel")}</h2>{character?.avatar_filename && <span title={t("ip.referenceOn")}>◉</span>}</div>
        <div className="ip-form">
          <label>{t("ip.preset")}<select value={presetId} disabled={!!busy} onChange={e => setPresetId(e.target.value)}>
            <option value="">{t("ip.presetNone")}</option>
            {presets.map(preset => <option key={preset.id} value={preset.id}>{preset.name}</option>)}
          </select></label>
          <div className="preset-actions">
            <button type="button" disabled={!!busy || !presetId} onClick={applyPreset}>{t("ip.presetApply")}</button>
            <button type="button" disabled={!!busy} onClick={savePreset}>{t("ip.presetSave")}</button>
            {presetId && <button type="button" className="danger" disabled={!!busy} onClick={deletePreset}>{t("common.delete")}</button>}
          </div>
          <label>{t("ip.prompt")}<textarea rows={4} value={prompt} disabled={!!busy} onChange={e => setPrompt(e.target.value)} placeholder={t("ip.promptPlaceholder")} maxLength={2000} /></label>
          <label>{t("ip.direction")}<input value={direction} disabled={!!busy} onChange={e => setDirection(e.target.value)} placeholder={t("ip.directionPlaceholder")} maxLength={1000} /></label>
          <button type="button" disabled={!!busy || !prompt.trim()} onClick={augment}>{t("ip.augment")}</button>
          <details><summary>{t("ip.details")}</summary>
            <label>{t("ip.negative")}<textarea rows={2} value={negative} disabled={!!busy} onChange={e => setNegative(e.target.value)} placeholder={t("ip.negativeHint")} maxLength={4000} /></label>
            <label>{t("ip.style")}<select value={style} disabled={!!busy} onChange={e => setStyle(e.target.value as "real" | "anime")}><option value="real">{t("pg.style.real")}</option><option value="anime">{t("pg.style.anime")}</option></select></label>
            <label>{t("ip.checkpoint")}<select value={checkpoint} disabled={!!busy} onChange={e => setCheckpoint(e.target.value)}><option value="">{t("ip.default")}</option>{checkpoints.filter(c => c.usable).map(checkpoint => <option key={checkpoint.name} value={checkpoint.name}>{checkpoint.name} · {checkpoint.family}</option>)}</select></label>
          </details>
          <div className="lora-picker"><span>{t("ip.loras")}</span>
            {!loras.length && <small className="muted">{t("ip.noLoras")}</small>}
            {compatibleLoras.map(name => <div className="lora-row" key={name}>
              <input type="checkbox" checked={loraSel[name]?.on || false} disabled={!!busy} onChange={e => setLoraSel(prev => ({ ...prev, [name]: { ...prev[name], on: e.target.checked, weight: prev[name]?.weight ?? 0.8 } }))} />
              <span className="lora-name" title={name}>{name}</span>
              <input type="number" min="0" max="2" step="0.05" value={loraSel[name]?.weight ?? 0.8} disabled={!!busy} onChange={e => setLoraSel(prev => ({ ...prev, [name]: { ...prev[name], on: prev[name]?.on ?? false, weight: Number(e.target.value) } }))} />
              {loraSel[name]?.on && <div className="lora-extra">
                <select value={loraSel[name]?.category ?? "other"} disabled={!!busy} onChange={e => setLoraSel(prev => ({ ...prev, [name]: { ...prev[name], on: prev[name]?.on ?? false, weight: prev[name]?.weight ?? 0.8, category: e.target.value } }))}>
                  {LORA_CATEGORIES.map(category => <option key={category} value={category}>{t(`ip.loraCat.${category}`)}</option>)}
                </select>
                <label>CLIP<input type="number" min="0" max="2" step="0.05" value={loraSel[name]?.clip ?? ""} placeholder="auto" disabled={!!busy} onChange={e => setLoraSel(prev => ({ ...prev, [name]: { ...prev[name], on: prev[name]?.on ?? false, weight: prev[name]?.weight ?? 0.8, clip: e.target.value === "" ? null : Number(e.target.value) } }))} /></label>
              </div>}
            </div>)}
            {hiddenLoras > 0 && <small className="muted">{t("ip.lorasHidden", { count: hiddenLoras })}</small>}
          </div>
          {activeCharacterLora?.filename && loraSel[activeCharacterLora.filename]?.on && <p className="muted">{t("ip.characterLoraOn", { name: activeCharacterLora.filename })}</p>}
          <div className="pose-picker"><span>{t("lp.poseSelect")}</span>
            {!poses.length && <small className="muted">{t("lp.noPoses")}</small>}
            {poses.filter(pose => pose.active).map(pose => <label className="pose-choice" key={pose.id}>
              <input type="checkbox" checked={poseIds.includes(pose.id)} disabled={!!busy} onChange={e => setPoseIds(prev => e.target.checked ? [...prev, pose.id] : prev.filter(id => id !== pose.id))} />
              {pose.name}
            </label>)}
          </div>
          {!!poseIds.length && <label className="auto-label">{t("lp.poseStrength")} <input type="number" min={0} max={2} step={0.05} value={poseStrength} disabled={!!busy} onChange={e => setPoseStrength(e.target.value)} /></label>}
          <div className="benchmark-options">
            <label>{t("ip.count")}<select value={count} disabled={!!busy} onChange={e => setCount(Number(e.target.value))}>{[1, 2, 3, 4].map(value => <option key={value}>{value}</option>)}</select></label>
            <label>{t("ip.seed")}<input type="number" min="0" value={seed} disabled={!!busy} onChange={e => setSeed(e.target.value)} placeholder="—" /></label>
          </div>
          <label className="auto-label">{t("ip.classify")} <input type="checkbox" checked={classify} disabled={!!busy} onChange={e => setClassify(e.target.checked)} /></label>
          {busy && <p className="memory-status" role="status"><span className="spinner" />{busy} <b>{elapsed.toFixed(0)} s</b> <button className="text-button danger" onClick={() => void api.interruptGeneration()}>{t("common.cancel")}</button></p>}
          <button className="primary" disabled={!!busy || !character || !prompt.trim()} onClick={generate}>{t("ip.generate")}</button>
          <details className="pose-library-panel">
            <summary>{t("lp.poses")}</summary>
            <PoseLibrary poses={poses} busy={!!busy} perform={perform} onView={(url, alt) => setViewer({ url, alt })} onChange={refreshPoses} />
          </details>
        </div>
      </aside>
    </div>
    {viewer && <Lightbox src={viewer.url} alt={viewer.alt} onClose={() => setViewer(null)} />}
  </div>;
}
