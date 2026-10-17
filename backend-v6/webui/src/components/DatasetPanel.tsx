import { useCallback, useEffect, useState } from "react";
import { api, Character, DatasetAnalysis, LoraDataset, LoraDatasetDetail, LoraDatasetItem } from "../api";
import {useI18n, TranslationKey} from "../i18n";

const REFERENCE_ROLES = [
  "close_face",
  "three_quarter_face",
  "profile",
  "upper_body",
  "front_full_body",
  "three_quarter_full_body",
  "side_full_body",
] as const;

const STEP_IDS = ["ds-step-1", "ds-step-2", "ds-step-3"] as const;
const STEP_LABELS: TranslationKey[] = ["lp.step1.title", "lp.step2.title", "lp.stepCurate.title"];

const STANDARD_POSES = [
  "walking_street",
  "sitting_cafe",
  "leaning_wall",
  "lying_bed_casual",
  "gym_workout",
  "kitchen_morning",
  "car_selfie",
  "beach_walk",
  "night_out_dress",
  "sofa_blanket",
  "lingerie_bed",
  "topless_mirror",
  "shower_tease",
  "bikini_poolside",
  "dress_off_shoulder",
  "bed_spread",
  "stockings_chair",
  "back_arch_bed",
  "oil_body",
  "bath_foam",
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

function RefGallery({ items, recommended, busy, onToggle, onView }: {
  items: LoraDatasetItem[];
  recommended: Set<string>;
  busy: boolean;
  onToggle: (item: LoraDatasetItem) => void;
  onView: (url: string, alt: string) => void;
}) {
  const { t } = useI18n();
  return <div className="ref-gallery">{items.map(item => <article className={`ref-card ${item.selected ? "selected" : ""}`} key={item.id}>
    <div className="dataset-thumb">
      <ItemThumb item={item} alt={item.caption || "reference"} onView={onView} />
      {(item.similarity ?? 0) > 0 && <span className={`badge sim-badge ${(item.similarity ?? 0) >= 70 ? "sim-ok" : (item.similarity ?? 0) >= 55 ? "sim-warn" : "sim-low"}`}>{Math.round(item.similarity ?? 0)}%</span>}
      {recommended.has(item.id) && <span className="badge rec-badge" title={t("lp.recommended")}>★</span>}
    </div>
    <label className="auto-label"><input type="checkbox" checked={item.selected} disabled={busy} onChange={() => onToggle(item)} /> {t("lp.itemSelect")}</label>
  </article>)}</div>;
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
  const [blueprint, setBlueprint] = useState<Awaited<ReturnType<typeof api.getDatasetBlueprint>> | null>(null);
  const [trigger, setTrigger] = useState("");
  const [datasetFamily, setDatasetFamily] = useState("real");
  const hasAvatar = !!character?.avatar_filename;
  const [characterPrompt, setCharacterPrompt] = useState("");
  const [deleteIds, setDeleteIds] = useState<string[]>([]);

  const loadDetail = useCallback(async (id: string) => {
    if (!id) { setDetail(null); setAnalysis(null); setBlueprint(null); return; }
    setDetail(await api.getDataset(id));
    setAnalysis(await api.getDatasetAnalysis(id));
    setBlueprint(await api.getDatasetBlueprint(id));
  }, []);

  useEffect(() => { void loadDetail(openId).catch(() => undefined); }, [openId, loadDetail]);

  useEffect(() => { setDeleteIds([]); }, [openId]);

  useEffect(() => {
    setCharacterPrompt(character?.avatar_prompt ?? "");
  }, [character?.id, character?.avatar_prompt]);

  const create = () => {
    if (!character) return;
    void perform(t("common.loading"), async () => {
      const created = await api.createDataset(character.id, { family: datasetFamily, trigger: trigger.trim() || undefined });
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

  const generateRole = (role: string) => {
    if (!detail) return;
    void perform(t("lp.generating"), async () => {
      await api.generateReferenceSet(detail.id, { role, count: 4 });
      await loadDetail(detail.id);
      await refresh();
    });
  };

  const generatePose = (pose: string) => {
    if (!detail) return;
    void perform(t("lp.generating"), async () => {
      await api.generatePoseVariations(detail.id, { pose, count: 4 });
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

  const saveCaption = (item: LoraDatasetItem, caption: string) => {
    if (caption === item.caption) return;
    void perform("", async () => {
      const updated = await api.patchDatasetItem(item.id, { caption });
      setDetail(prev => prev ? { ...prev, items: prev.items.map(entry => (entry.id === updated.id ? updated : entry)) } : prev);
    });
  };

  const toggleDeleteId = (id: string) => {
    setDeleteIds(prev => prev.includes(id) ? prev.filter(entry => entry !== id) : [...prev, id]);
  };

  const removeSelected = () => {
    if (!detail || !deleteIds.length) return;
    if (!window.confirm(t("bulk.confirmDelete", { count: deleteIds.length }))) return;
    void perform("", async () => {
      await api.deleteDatasetItems(deleteIds);
      setDeleteIds([]);
      await loadDetail(detail.id);
      await refresh();
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

  const items = detail?.items ?? [];
  const itemsByRole = (role: string) => items.filter(item => item.reference_role === role);
  const itemsByPose = (pose: string) => items.filter(item => (item.tags ?? []).includes(pose));
  const referenceRoles = new Set(items.filter(item => item.reference_role).map(item => item.reference_role));
  const poseCount = items.filter(item => (item.tags ?? []).some(tag => (STANDARD_POSES as readonly string[]).includes(tag))).length;
  const recommendedIds = (group: LoraDatasetItem[]) => {
    const scored = group.filter(item => (item.similarity ?? 0) > 0).sort((a, b) => (b.similarity ?? 0) - (a.similarity ?? 0)).slice(0, 2);
    return new Set(scored.map(item => item.id));
  };
  const stepDone = [referenceRoles.size > 0, poseCount > 0, (analysis?.selected ?? 0) > 0];
  const activeStep = stepDone.findIndex(done => !done);

  const stepHead = (index: number) => <header className="step-head">
    <span className="step-num">{index + 1}</span>
    <h3>{t(STEP_LABELS[index])}</h3>
    <span className={`step-state ${stepDone[index] ? "done" : index === activeStep ? "active" : ""}`}>{stepDone[index] ? t("lp.stepDone") : t("lp.stepTodo")}</span>
  </header>;

  return <section>
    <div className="section-title"><h2>{t("lp.datasets")}</h2><span>{datasets.length}</span></div>
    <details className="dataset-create" open={!datasets.length}>
      <summary>+ {t("lp.datasetCreate")}</summary>
      <div className="dataset-create-row">
        <label>{t("lp.datasetFamily")}<select value={datasetFamily} disabled={busy || !character} onChange={e => setDatasetFamily(e.target.value)}>
          <option value="real">real</option><option value="pony">pony</option><option value="anime">anime</option><option value="qwen-image">qwen-image</option>
        </select></label>
        <label>{t("lp.datasetTrigger")}<input value={trigger} disabled={busy || !character} onChange={e => setTrigger(e.target.value)} placeholder={t("lp.triggerHint")} maxLength={64} /></label>
        <button className="primary" disabled={busy || !character} onClick={create}>{t("lp.datasetCreate")}</button>
      </div>
    </details>
    {!datasets.length && <p className="muted">{t("lp.noDatasets")}</p>}
    <ul className="home-list">{datasets.map(dataset => <li key={dataset.id}>
      <button className="dataset-open" disabled={busy} onClick={() => setOpenId(openId === dataset.id ? "" : dataset.id)}>
        <span title={dataset.id}>{dataset.trigger}</span>
        <b>{t("lp.datasetCounts", { selected: dataset.selected_count, total: dataset.item_count })}</b>
      </button>
    </li>)}</ul>
    {detail && <div className="dataset-detail">
      <div className="section-title"><h2>{detail.trigger}</h2><div className="section-actions"><span>{t("lp.datasetCounts", { selected: detail.selected_count, total: detail.item_count })}</span><button className="text-button danger" disabled={busy} onClick={() => removeDataset(detail)}>{t("common.delete")}</button></div></div>
      {busy && <p className="memory-status" role="status"><span className="spinner" />{t("common.loading")} <button className="text-button danger" onClick={() => void api.interruptGeneration()}>{t("common.cancel")}</button></p>}

      <nav className="step-nav">{STEP_IDS.map((id, index) => <a key={id} href={`#${id}`} className={stepDone[index] ? "on" : ""}><span className="dot" />{t(STEP_LABELS[index])}</a>)}</nav>

      <div className="dataset-steps">
        <section className="step-card" id="ds-step-1">
          {stepHead(0)}
          <p className="muted">{t("lp.step1.hint")}</p>
          {!hasAvatar && <p className="warning" role="note">{t("lp.step1.needAvatar")}</p>}
          <details className="step-options">
            <summary>{t("lp.characterPrompt")}</summary>
            <p className="muted">{t("lp.characterPromptHint")}</p>
            <textarea rows={3} value={characterPrompt} disabled={busy || !character} onChange={e => setCharacterPrompt(e.target.value)} maxLength={4000} />
            <button type="button" className="text-button" disabled={busy || !character} onClick={saveCharacterPrompt}>{t("lp.characterPromptSave")}</button>
          </details>
          <p className="muted">{t("lp.step1.selectHint")}</p>
          {REFERENCE_ROLES.map(role => <div className="ref-row" key={role}>
            <div className="ref-row-head">
              <strong>{t(`lp.role.${role}` as TranslationKey)}</strong>
              <button className="primary" disabled={busy || !hasAvatar} onClick={() => generateRole(role)}>{t("lp.generate4")}</button>
            </div>
            {itemsByRole(role).length
              ? <RefGallery items={itemsByRole(role)} recommended={recommendedIds(itemsByRole(role))} busy={busy} onToggle={toggleItem} onView={onView} />
              : <p className="muted">{t("lp.refEmpty")}</p>}
          </div>)}
        </section>

        <section className="step-card" id="ds-step-2">
          {stepHead(1)}
          <p className="muted">{t("lp.step2.hint")}</p>
          {!referenceRoles.size && <p className="warning" role="note">{t("lp.step2.needRefs")}</p>}
          {STANDARD_POSES.map(pose => <div className="ref-row" key={pose}>
            <div className="ref-row-head">
              <strong>{t(`lp.pose.${pose}` as TranslationKey)}</strong>
              <button className="primary" disabled={busy || !referenceRoles.size} onClick={() => generatePose(pose)}>{t("lp.generate4")}</button>
            </div>
            {itemsByPose(pose).length
              ? <RefGallery items={itemsByPose(pose)} recommended={recommendedIds(itemsByPose(pose))} busy={busy} onToggle={toggleItem} onView={onView} />
              : <p className="muted">{t("lp.refEmpty")}</p>}
          </div>)}
        </section>

        <section className="step-card" id="ds-step-3">
          {stepHead(2)}
          <p className="muted">{t("lp.stepCurate.hint")}</p>
          {blueprint && <div className="dataset-blueprint">
            <small className="muted">{t("lp.blueprint.title")}</small>
            <ul>{blueprint.categories.map(category => <li key={category.key}>
              <span>{t(`lp.blueprint.${category.key}` as "lp.blueprint.close_face")}</span>
              <b className={category.count >= category.target ? "ok" : ""}>{category.count}/{category.target}</b>
            </li>)}</ul>
          </div>}
          {analysis && <div className="dataset-analysis">
            <div className="job-bar"><i style={{ width: `${Math.min(100, (analysis.selected / analysis.target) * 100)}%` }} /></div>
            <small>{t("lp.datasetProgress", { selected: analysis.selected, target: analysis.target })}</small>
            {!!analysis.warnings.length && <ul className="dataset-warnings">{analysis.warnings.map(warning => <li key={warning.code}>
              <b>{t(WARNING_LABELS[warning.code] || "lp.warnings")}</b> · {warning.detail}
            </li>)}</ul>}
          </div>}
          {!detail.items.length && <p className="muted">{t("lp.datasetEmpty")}</p>}
          {!!detail.items.length && <>
            <div className="bulk-bar">
              <label><input type="checkbox" disabled={busy} checked={deleteIds.length > 0 && deleteIds.length === detail.items.length} onChange={e => setDeleteIds(e.target.checked ? detail.items.map(entry => entry.id) : [])} /> {t("bulk.selectAll")}</label>
              <button className="danger" disabled={busy || !deleteIds.length} onClick={removeSelected}>{t("bulk.deleteSelected", { count: deleteIds.length })}</button>
            </div>
            <div className="dataset-grid" id="ds-grid">{detail.items.map(item => <article className={`dataset-card ${item.selected ? "selected" : ""}`} key={item.id}>
              <div className="dataset-thumb"><label className="select-check" title={t("bulk.select")}><input type="checkbox" checked={deleteIds.includes(item.id)} disabled={busy} onChange={() => toggleDeleteId(item.id)} /></label><ItemThumb item={item} alt={item.caption || detail.trigger} onView={onView} /></div>
              <div className="dataset-meta">
                {item.reference_role && <span className="reference-badge">{t(`lp.role.${item.reference_role}` as TranslationKey)}</span>}
                <input key={item.id} defaultValue={item.caption} disabled={busy} onBlur={e => saveCaption(item, e.target.value)} maxLength={2000} />
                <div className="lora-actions">
                  <button disabled={busy} onClick={() => toggleItem(item)}>{item.selected ? t("lp.itemSelected") : t("lp.itemSelect")}</button>
                  <button className="danger" disabled={busy} onClick={() => removeItem(item)}>{t("common.delete")}</button>
                </div>
              </div>
            </article>)}</div>
          </>}
        </section>
      </div>
    </div>}
  </section>;
}
