import { useEffect } from "react";

export default function Lightbox({ src, alt, onClose }: { src: string; alt: string; onClose: () => void }) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return <div className="lightbox" role="dialog" aria-modal="true" aria-label={alt} onClick={onClose}>
    <button className="lightbox-close" onClick={onClose} aria-label="Chiudi">×</button>
    <img src={src} alt={alt} onClick={event => event.stopPropagation()} />
    <span className="lightbox-hint">Clic o Esc per chiudere</span>
  </div>;
}
