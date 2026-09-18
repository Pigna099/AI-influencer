import { useCallback, useEffect, useState } from "react";
import { api, Character, CheckpointInfo, DatasetAnalysis, LoraDataset, LoraDatasetDetail, LoraDatasetItem, PoseReference } from "../api";
import { useI18n, TranslationKey } from "../i18n";

const SDXL_FAMILIES = ["real", "pony", "anime"];
const REFERENCE_ROLES = [
  "close_face",
  "three_quarter_face",
  "profile",
  "upper_body",
  "front_full_body",
  "three_quarter_full_body",
  "side_full_body",
] as const;

const WARNING_LABELS: Record<string, TranslationKey> = {
  select_more: "lp.warn.select_more",
  duplicates: "lp.warn.duplicates",
  few_full_body: "lp.warn.few_full_body",
  few_profile: "lp.warn.few_profile",
  too_frontal: "lp.warn.too_frontal",
  same_pose: "lp.warn.same_pose",
  same_scene: "lp.warn.same_scene",
  few_references: "lp.warn.few_references",
};

function ItemThumb({ item, alt, onView }: { item: LoraDatasetItem; alt: string; onView: (url: string, alt: string) => void }) {
  const [url, setUrl] = useState("");
  useEffect(() => {
    let objectUrl = "";
    let alive = true;
    setUrl("");
    if (!item.image_id || !item.filename) return;
    api.fetchBlob(`/api/library/${item.image_id}/file?v=${encodeURIComponent(item.filename)}`)
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
  }, [item.image_id, item.filename]);
  if (!item.image_id) return <div className="library-loading"><span className="spinner" /></div>;
  if (!url) return <div className="library-loading"><span className="spinner" /></div>;
  return <img src={url} alt={alt} loading="lazy" onClick={() => onView(url, alt)} />;
}

interface Props {
  character: Character | undefined;
  datasets: LoraDataset[];
  busy: boolean;
  perform: (label: string, work: () => Promise<void>) => Promise<void>;
  refresh: () => Promise<void>;
  onView: (url: string, alt: string) => void;
}

export default function DatasetPanel({ character, datasets, busy, perform, refresh, onView }: Props) {
  const { t } = useI18n();
  const [openId, setOpenId] = useState("");
  const [detail, setDetail] = useState<LoraDatasetDetail | null>(null);
  const [analysis, setAnalysis] = useState<DatasetAnalysis | null>(null);
  const [trigger, setTrigger] = useState("");
  const [checkpoints, setCheckpoints] = useState<CheckpointInfo[]>([]);
  const [poses, setPoses] = useState<PoseReference[]>([]);
  const [identityPrompt, setIdentityPrompt] = useState(() => t("lp.identityDefaultPrompt"));
  const [characterPrompt, setCharacterPrompt] = useState("");
  const [identityModel, setIdentityModel] = useState("");
  const [identityCount, setIdentityCount] = useState(4);
  const [variationPrompts, setVariationPrompts] = useState(() => t("lp.variationsDefaultScenes"));
  const [variationModel, setVariationModel] = useState("");
  const [variationCount, setVariationCount] = useState(1);
  const [candidatePrompt, setCandidatePrompt] = useState("");
  const [candidateCheckpoint, setCandidateCheckpoint] = useState("");
  const [candidateCount, setCandidateCount] = useState(1);
  const [candidatePoseIds, setCandidatePoseIds] = useState<string[]>([]);
  const [candidateStrength, setCandidateStrength] = useState("0.8");

  const loadDetail = useCallback(async (id: string) => {
    if (!id) { setDetail(null); setAnalysis(null); return; }
    setDetail(await api.getDataset(id));
    setAnalysis(await api.getDatasetAnalysis(id));
  }, []);

  useEffect(() => { void loadDetail(openId).catch(() => undefined); }, [openId, loadDetail]);

  useEffect(() => {
    setCharacterPrompt(character?.avatar_prompt ?? "");
  }, [character?.id, character?.avatar_prompt]);

  useEffect(() => {
    Promise.all([api.getCheckpoints(), api.getPoses()])
      .then(([checkpointData, poseData]) => {
        const usable = (checkpointData.checkpoints ?? []).filter(item => item.usable);
        setCheckpoints(usable);
        setPoses(poseData);
        const preferred = usable.find(item => item.name.toLowerCase().includes("2512"))
          || usable.find(item => item.family === "qwen-image");
        if (preferred) setIdentityModel(preferred.name);
      })
      .catch(() => undefined);
  }, []);

  const create = () => {
    if (!character) return;
    void perform(t("common.loading"), async () => {
      const created = await api.createDataset(character.id, { family: "real", trigger: trigger.trim() || undefined });
      await refresh();
      setOpenId(created.id);
      setTrigger("");
    });
  };

  const saveCharacterPrompt = () => {
    if (!character) return;
    void perform(t("lp.characterPromptSave"), async () => {
      const updated = await api.setAvatarPrompt(character.id, characterPrompt.trim() || null);
      setCharacterPrompt(updated.avatar_prompt ?? "");
    });
  };

  const generateIdentity = () => {
    if (!detail || !identityPrompt.trim()) return;
    void perform(t("lp.generating"), async () => {
      await api.generateDataset(detail.id, {
        prompt: identityPrompt.trim(),
        checkpoint: identityModel || undefined,
        pose_ids: [],
        count: identityCount,
      });
      await loadDetail(detail.id);
      await refresh();
    });
  };

  const generateCandidates = () => {
    if (!detail || !candidatePrompt.trim()) return;
    void perform(t("lp.generating"), async () => {
      await api.generateDataset(detail.id, {
        prompt: candidatePrompt.trim(),
        checkpoint: candidateCheckpoint || undefined,
        pose_ids: candidatePoseIds,
        pose_strength: Number(candidateStrength),
        count: candidateCount,
      });
      await loadDetail(detail.id);
      await refresh();
    });
  };

  const generateVariations = () => {
    if (!detail) return;
    const prompts = variationPrompts.split("\n").map(line => line.trim()).filter(Boolean);
    if (!prompts.length) return;
    void perform(t("lp.variationsRunning"), async () => {
      await api.generateDatasetVariations(detail.id, { prompts, count: variationCount, model: variationModel || undefined });
      await loadDetail(detail.id);
      await refresh();
    });
  };

  const toggleItem = (item: LoraDatasetItem) => void perform("", async () => {
    const updated = await api.patchDatasetItem(item.id, { selected: !item.selected });
    setDetail(prev => prev ? {
      ...prev,
      items: prev.items.map(entry => (entry.id === updated.id ? updated : entry)),
      selected_count: prev.items.filter(entry => (entry.id === updated.id ? updated.selected : entry.selected)).length,
    } : prev);
    await refresh();
  });

  const setRole = (item: LoraDatasetItem, role: string) => void perform("", async () => {
    const updated = await api.patchDatasetItem(item.id, { reference_role: role });
    setDetail(prev => prev ? { ...prev, items: prev.items.map(entry => (entry.id === updated.id ? updated : entry)) } : prev);
    if (detail) setAnalysis(await api.getDatasetAnalysis(detail.id));
  });

  const saveCaption = (item: LoraDatasetItem, caption: string) => {
    if (caption === item.caption) return;
    void perform("", async () => {
      const updated = await api.patchDatasetItem(item.id, { caption });
      setDetail(prev => prev ? { ...prev, items: prev.items.map(entry => (entry.id === updated.id ? updated : entry)) } : prev);
    });
  };

  const removeItem = (item: LoraDatasetItem) => {
    if (!detail || !window.confirm(t("lp.deleteDatasetItemConfirm"))) return;
    void perform("", async () => {
      await api.deleteDatasetItem(item.id);
      await loadDetail(detail.id);
      await refresh();
    });
  };

  const removeDataset = (dataset: LoraDatasetDetail) => {
    if (!window.confirm(t("lp.deleteDatasetConfirm"))) return;
    void perform("", async () => {
      await api.deleteDataset(dataset.id);
      setOpenId("");
      setDetail(null);
      setAnalysis(null);
      await refresh();
    });
  };

  const referenceRoles = new Set((detail?.items ?? []).filter(item => item.reference_role).map(item => item.reference_role));
  const identityModels = [...checkpoints].sort((left, right) => (left.family === "qwen-image" ? -1 : 0) - (right.family === "qwen-image" ? -1 : 0));

  return <section>
    <div className="section-title"><h2>{t("lp.datasets")}</h2><span>{datasets.length}</span></div>
    <div className="dataset-create">
      <label>{t("lp.datasetTrigger")}<input value={trigger} disabled={busy || !character} onChange={e => setTrigger(e.target.value)} placeholder={t("lp.triggerHint")} maxLength={64} /></label>
      <button className="primary" disabled={busy || !character} onClick={create}>{t("lp.datasetCreate")}</button>
    </div>
    {!datasets.length && <p className="muted">{t("lp.noDatasets")}</p>}
    <ul className="home-list">{datasets.map(dataset => <li key={dataset.id}>
      <button className="dataset-open" disabled={busy} onClick={() => setOpenId(openId === dataset.id ? "" : dataset.id)}>
        <span title={dataset.id}>{dataset.trigger}</span>
        <b>{t("lp.datasetCounts", { selected: dataset.selected_count, total: dataset.item_count })}</b>
      </button>
    </li>)}</ul>
    {detail && <div className="dataset-detail">
      <div className="section-title"><h2>{detail.trigger}</h2><div className="section-actions"><span>{t("lp.datasetCounts", { selected: detail.selected_count, total: detail.item_count })}</span><button className="danger" disabled={busy} onClick={() => removeDataset(detail)}>{t("common.delete")}</button></div></div>
      {busy && <p className="memory-status" role="status"><span className="spinner" />{t("common.loading")} <button className="text-button danger" onClick={() => void api.interruptGeneration()}>{t("common.cancel")}</button></p>}
      {analysis && <div className="dataset-analysis">
        <div className="job-bar"><i style={{ width: `${Math.min(100, (analysis.selected / analysis.target) * 100)}%` }} /></div>
        <small>{t("lp.datasetProgress", { selected: analysis.selected, target: analysis.target })}</small>
        {!!analysis.warnings.length && <ul className="dataset-warnings">{analysis.warnings.map(warning => <li key={warning.code}>
          <b>{t(WARNING_LABELS[warning.code] || "lp.warnings")}</b> · {warning.detail}
        </li>)}</ul>}
      </div>}
      <p className="muted">{t("lp.datasetHint")}</p>

      <div className="dataset-generate">
        <h3>{t("lp.stepA.title")}</h3>
        <p className="muted">{t("lp.stepA.hint")}</p>
        <details className="character-prompt" key={character?.id} open={Boolean(character?.avatar_prompt)}>
          <summary>{t("lp.characterPrompt")}</summary>
          <p className="muted">{t("lp.characterPromptHint")}</p>
          <label><textarea rows={3} value={characterPrompt} disabled={busy || !character} onChange={e => setCharacterPrompt(e.target.value)} maxLength={4000} /></label>
          <button type="button" disabled={busy || !character} onClick={saveCharacterPrompt}>{t("lp.characterPromptSave")}</button>
        </details>
        <label>{t("lp.generatePrompt")} <button type="button" className="text-button" disabled={busy} onClick={() => setIdentityPrompt(t("lp.identityDefaultPrompt"))}>{t("lp.restoreDefaults")}</button><textarea rows={3} value={identityPrompt} disabled={busy} onChange={e => setIdentityPrompt(e.target.value)} maxLength={2000} /></label>
        <div className="grid">
          <label>{t("lp.identityModel")}<select value={identityModel} disabled={busy} onChange={e => setIdentityModel(e.target.value)}>
            <option value="">{t("lp.baseCheckpointAuto")}</option>
            {identityModels.map(item => <option key={item.name} value={item.name}>{item.name} · {item.family}</option>)}
          </select></label>
          <label>{t("lp.countPerPose")}<select value={identityCount} disabled={busy} onChange={e => setIdentityCount(Number(e.target.value))}>{[1, 2, 3, 4].map(value => <option key={value} value={value}>{value}</option>)}</select></label>
        </div>
        <button className="primary" disabled={busy || !identityPrompt.trim()} onClick={generateIdentity}>{t("lp.generateIdentity")}</button>
        <hr className="dataset-divider" />

        <h3>{t("lp.stepB.title")}</h3>
        <p className="muted">{t("lp.stepB.hint")}</p>
        <div className="reference-summary">
          <b>{t("lp.referenceCount", { count: referenceRoles.size })}</b>
          {REFERENCE_ROLES.map(role => <span className={`role-chip ${referenceRoles.has(role) ? "on" : ""}`} key={role}>{t(`lp.role.${role}`)}</span>)}
        </div>
        <hr className="dataset-divider" />

        <h3>{t("lp.stepC.title")}</h3>
        <p className="muted">{t("lp.stepC.hint")}</p>
        <label>{t("lp.variations")} <button type="button" className="text-button" disabled={busy} onClick={() => setVariationPrompts(t("lp.variationsDefaultScenes"))}>{t("lp.restoreDefaults")}</button><textarea rows={6} value={variationPrompts} disabled={busy} onChange={e => setVariationPrompts(e.target.value)} placeholder={t("lp.variationsPlaceholder")} /></label>
        <div className="grid">
          <label>{t("lp.variationsModel")}<select value={variationModel} disabled={busy} onChange={e => setVariationModel(e.target.value)}>
            <option value="">{t("lp.baseCheckpointAuto")}</option>
            {checkpoints.filter(item => item.family === "qwen-image").map(item => <option key={item.name} value={item.name}>{item.name}</option>)}
          </select></label>
          <label>{t("lp.countPerPose")}<select value={variationCount} disabled={busy} onChange={e => setVariationCount(Number(e.target.value))}>{[1, 2, 3, 4].map(value => <option key={value} value={value}>{value}</option>)}</select></label>
        </div>
        <p className="muted">{t("lp.variationsHint")}</p>
        <button className="primary" disabled={busy || !variationPrompts.trim()} onClick={generateVariations}>{t("lp.variationsRun")}</button>

        <label>{t("lp.candidatesPrompt")}<textarea rows={2} value={candidatePrompt} disabled={busy} onChange={e => setCandidatePrompt(e.target.value)} maxLength={2000} /></label>
        <div className="grid">
          <label>{t("lp.candidatesModel")}<select value={candidateCheckpoint} disabled={busy} onChange={e => setCandidateCheckpoint(e.target.value)}>
            <option value="">{t("lp.baseCheckpointAuto")}</option>
            {checkpoints.filter(item => SDXL_FAMILIES.includes(item.family)).map(item => <option key={item.name} value={item.name}>{item.name}</option>)}
          </select></label>
          <label>{t("lp.countPerPose")}<select value={candidateCount} disabled={busy} onChange={e => setCandidateCount(Number(e.target.value))}>{[1, 2, 3, 4].map(value => <option key={value} value={value}>{value}</option>)}</select></label>
          <label>{t("lp.poseStrength")}<input type="number" min={0} max={2} step={0.05} value={candidateStrength} disabled={busy} onChange={e => setCandidateStrength(e.target.value)} /></label>
        </div>
        <div className="pose-picker"><span>{t("lp.poseSelect")}</span>
          {!poses.length && <small className="muted">{t("lp.noPoses")}</small>}
          {poses.filter(pose => pose.active).map(pose => <label className="pose-choice" key={pose.id}>
            <input type="checkbox" checked={candidatePoseIds.includes(pose.id)} disabled={busy} onChange={e => setCandidatePoseIds(prev => e.target.checked ? [...prev, pose.id] : prev.filter(id => id !== pose.id))} />
            {pose.name}
          </label>)}
        </div>
        <p className="muted">{t("lp.candidatesHint")}</p>
        <button className="primary" disabled={busy || !candidatePrompt.trim()} onClick={generateCandidates}>{t("lp.generateCandidates")}</button>
      </div>

      {!detail.items.length && <p className="muted">{t("lp.datasetEmpty")}</p>}
      <div className="dataset-grid">{detail.items.map(item => <article className={`dataset-card ${item.selected ? "selected" : ""}`} key={item.id}>
        <div className="dataset-thumb"><ItemThumb item={item} alt={item.caption || detail.trigger} onView={onView} /></div>
        <div className="dataset-meta">
          {item.reference_role && <span className="reference-badge">{t(`lp.role.${item.reference_role}` as TranslationKey)}</span>}
          <input key={item.id} defaultValue={item.caption} disabled={busy} onBlur={e => saveCaption(item, e.target.value)} maxLength={2000} />
          <select className="dataset-role" value={item.reference_role ?? ""} disabled={busy} onChange={e => setRole(item, e.target.value)}>
            <option value="">{t("lp.role.none")}</option>
            {REFERENCE_ROLES.map(role => <option key={role} value={role}>{t(`lp.role.${role}`)}</option>)}
          </select>
          <div className="lora-actions">
            <button disabled={busy} onClick={() => toggleItem(item)}>{item.selected ? t("lp.itemSelected") : t("lp.itemSelect")}</button>
            <button className="danger" disabled={busy} onClick={() => removeItem(item)}>{t("common.delete")}</button>
          </div>
        </div>
      </article>)}</div>
    </div>}
  </section>;
}
