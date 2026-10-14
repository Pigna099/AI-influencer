interface Props {
  tone?: "error" | "info";
  children: React.ReactNode;
  onClose?: () => void;
  closeAria: string;
}

export default function Banner({ tone = "error", children, onClose, closeAria }: Props) {
  return (
    <div className={`${tone}-banner`} role={tone === "error" ? "alert" : "status"}>
      {children}
      {onClose && <button onClick={onClose} aria-label={closeAria}>×</button>}
    </div>
  );
}
