import { useEffect, useState } from "react";
import { api, PoseReference } from "../api";
import { useI18n } from "../i18n";

function PoseThumb({ pose, onView }: { pose: PoseReference; onView: (url: string, alt: string) => void }) {
  const [url, setUrl] = useState("");
  useEffect(() => {
    let objectUrl = "";
    let alive = true;
    setUrl("");
    api.fetchBlob(`/api/poses/${pose.id}/skeleton`)
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
  }, [pose.id]);
  if (!url) return <div className="library-loading"><span className="spinner" /></div>;
  return <img src={url} alt={pose.name} loading="lazy" onClick={() => onView(url, pose.name)} />;
}

interface Props {
  poses: PoseReference[];
  busy: boolean;
  perform: (label: string, work: () => Promise<void>) => Promise<void>;
  onView: (url: string, alt: string) => void;
  onChange: () => Promise<void>;
}

export default function PoseLibrary({ poses, busy, perform, onView, onChange }: Props) {
  const { t } = useI18n();

  const renamePose = (pose: PoseReference) => {
    const name = window.prompt(t("lp.poseRename"), pose.name);
    if (!name || !name.trim()) return;
    void perform("", async () => {
      await api.patchPose(pose.id, { name: name.trim() });
      await onChange();
    });
  };

  const togglePose = (pose: PoseReference) => void perform("", async () => {
    await api.patchPose(pose.id, { active: !pose.active });
    await onChange();
  });

  const removePose = (pose: PoseReference) => {
    if (!window.confirm(`${t("common.delete")} "${pose.name}"?`)) return;
    void perform("", async () => {
      await api.deletePose(pose.id);
      await onChange();
    });
  };

  return <div>
    {!poses.length && <p className="muted">{t("lp.noPoses")}</p>}
    <div className="pose-grid">{poses.map(pose => <article className={`pose-card ${pose.active ? "" : "inactive"}`} key={pose.id}>
      <div className="pose-thumb"><PoseThumb pose={pose} onView={onView} /></div>
      <div className="pose-meta">
        <strong>{pose.name}</strong>
        <small>{pose.tags.join(" · ") || "—"}</small>
        <div className="lora-actions">
          <button disabled={busy} onClick={() => renamePose(pose)}>{t("common.edit")}</button>
          <button disabled={busy} onClick={() => togglePose(pose)}>{pose.active ? t("lp.poseActive") : t("lp.poseInactive")}</button>
          <button className="danger" disabled={busy} onClick={() => removePose(pose)}>{t("common.delete")}</button>
        </div>
      </div>
    </article>)}</div>
  </div>;
}
