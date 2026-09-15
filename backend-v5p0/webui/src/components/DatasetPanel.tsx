import { useCallback, useEffect, useState } from "react";
import { api, Character, DatasetAnalysis, LoraDataset, LoraDatasetDetail, LoraDatasetItem } from "../api";
import { useI18n, TranslationKey } from "../i18n";

const WARNING_LABELS: Record<string, TranslationKey> = {
  select_more: "lp.warn.select_more",
  duplicates: "lp.warn.duplicates",
  few_full_body: "lp.warn.few_full_body",
  few_profile: "lp.warn.few_profile",
  too_frontal: "lp.warn.too_frontal",
  same_pose: "lp.warn.same_pose",
  same_scene: "lp.warn.same_scene",
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
  const [prompt, setPrompt] = useState("");
  const [variationPrompts, setVariationPrompts] = useState("");
  const [count, setCount] = useState(1);

  const loadDetail = useCallback(async (id: string) => {
    if (!id) { setDetail(null); setAnalysis(null); return; }
    setDetail(await api.getDataset(id));
    setAnalysis(await api.getDatasetAnalysis(id));
  }, []);

  useEffect(() => { void loadDetail(openId).catch(() => undefined); }, [openId, loadDetail]);

  const create = () => {
    if (!character) return;
    void perform(t("common.loading"), async () => {
      const created = await api.createDataset(character.id, { family: "real", trigger: trigger.trim() || undefined });
      await refresh();
      setOpenId(created.id);
      setTrigger("");
    });
  };

  const generate = () => {
    if (!detail || !prompt.trim()) return;
    void perform(t("lp.generating"), async () => {
      await api.generateDataset(detail.id, { prompt: prompt.trim(), pose_ids: [], count });
      await loadDetail(detail.id);
      await refresh();
    });
  };

  const generateVariations = () => {
    if (!detail) return;
    const prompts = variationPrompts.split("\n").map(line => line.trim()).filter(Boolean);
    if (!prompts.length) return;
    void perform(t("lp.variationsRunning"), async () => {
      await api.generateDatasetVariations(detail.id, { prompts });
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

  const removeItem = (item: LoraDatasetItem) => {
    if (!detail || !window.confirm(t("lp.deleteDatasetItemConfirm"))) return;
    void perform("", async () => {
      await api.deleteDatasetItem(item.id);
      await loadDetail(detail.id);
      await refresh();
    });
  };

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
      <div className="section-title"><h2>{detail.trigger}</h2><span>{t("lp.datasetCounts", { selected: detail.selected_count, total: detail.item_count })}</span></div>
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
        <label>{t("lp.variations")}<textarea rows={4} value={variationPrompts} disabled={busy} onChange={e => setVariationPrompts(e.target.value)} placeholder={t("lp.variationsPlaceholder")} /></label>
        <p className="muted">{t("lp.variationsHint")}</p>
        <button className="primary" disabled={busy || !variationPrompts.trim()} onClick={generateVariations}>{t("lp.variationsRun")}</button>
        <label>{t("lp.generatePrompt")}<textarea rows={3} value={prompt} disabled={busy} onChange={e => setPrompt(e.target.value)} maxLength={2000} /></label>
        <div className="grid">
          <label>{t("lp.countPerPose")}<select value={count} disabled={busy} onChange={e => setCount(Number(e.target.value))}>{[1, 2, 3, 4].map(value => <option key={value} value={value}>{value}</option>)}</select></label>
        </div>
        <button className="primary" disabled={busy || !prompt.trim()} onClick={generate}>{t("lp.generateCandidates")}</button>
        <p className="muted">{t("lp.candidatesHint")}</p>
      </div>
      {!detail.items.length && <p className="muted">{t("lp.datasetEmpty")}</p>}
      <div className="dataset-grid">{detail.items.map(item => <article className={`dataset-card ${item.selected ? "selected" : ""}`} key={item.id}>
        <div className="dataset-thumb"><ItemThumb item={item} alt={item.caption || detail.trigger} onView={onView} /></div>
        <div className="dataset-meta">
          <input key={item.id} defaultValue={item.caption} disabled={busy} onBlur={e => saveCaption(item, e.target.value)} maxLength={2000} />
          <div className="lora-actions">
            <button disabled={busy} onClick={() => toggleItem(item)}>{item.selected ? t("lp.itemSelected") : t("lp.itemSelect")}</button>
            <button className="danger" disabled={busy} onClick={() => removeItem(item)}>{t("common.delete")}</button>
          </div>
        </div>
      </article>)}</div>
    </div>}
  </section>;
}
