import { useId, type ReactNode } from 'react';

export function Field({ label, value, onChange, hint, inputMode, placeholder, maxLength }: {
  label: string; value: string | null; onChange: (value: string | null) => void;
  hint?: ReactNode; inputMode?: 'decimal' | 'text'; placeholder?: string; maxLength?: number;
}) {
  const id = useId();
  return <div className="field"><label htmlFor={id}>{label}</label>
    <input id={id} value={value ?? ''} inputMode={inputMode} placeholder={placeholder} maxLength={maxLength}
      onChange={(event) => onChange(event.target.value || null)} />{hint}</div>;
}

export function SelectField({ label, value, onChange, children, hint }: {
  label: string; value: string; onChange: (value: string) => void; children: ReactNode; hint?: ReactNode;
}) {
  const id = useId();
  return <div className="field"><label htmlFor={id}>{label}</label>
    <select id={id} value={value} onChange={(event) => onChange(event.target.value)}>{children}</select>{hint}</div>;
}
