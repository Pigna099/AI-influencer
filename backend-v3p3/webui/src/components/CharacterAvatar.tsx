import { useEffect, useState } from "react";
import { api, Character } from "../api";

export default function CharacterAvatar({ character, index, onView, altTemplate }: { character: Character; index: number; onView: (url: string, alt: string) => void; altTemplate: string }) {
  const [url, setUrl] = useState("");
  const alt = altTemplate.replace("{name}", character.name);
  useEffect(() => {
    let objectUrl = "";
    let alive = true;
    setUrl("");
    if (!character.avatar_filename) return;
    api.fetchBlob(`/api/characters/${character.id}/avatar/file?v=${encodeURIComponent(character.avatar_filename)}`)
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
  }, [character.id, character.avatar_filename]);
  if (!url) return <span className={`avatar color-${index % 4}`}>{character.name.slice(0, 2).toUpperCase()}</span>;
  return <img className="avatar avatar-photo" src={url} alt={alt} onClick={event => { event.stopPropagation(); onView(url, alt); }} />;
}
