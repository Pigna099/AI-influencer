interface Option {
  id: string;
  name: string;
  hint?: string;
}

interface Props {
  options: Option[];
  value: string;
  onChange: (id: string) => void;
  label: string;
  disabled?: boolean;
}

export default function ContextSelector({ options, value, onChange, label, disabled }: Props) {
  return (
    <label className="context-selector">
      <span className="sr-only">{label}</span>
      <select value={value} disabled={disabled || !options.length} onChange={event => onChange(event.target.value)} aria-label={label}>
        <option value="" disabled>{label}</option>
        {options.map(option => (
          <option key={option.id} value={option.id}>{option.name}{option.hint ? ` · ${option.hint}` : ""}</option>
        ))}
      </select>
    </label>
  );
}
