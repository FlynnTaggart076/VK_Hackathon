import type { FieldEvidence, Issue } from '../../api/types';
import { formatDecimal, formatMoney, formatTariff, scopeLabels, serviceLabel, unitLabels, unitText } from '../labels';
import { availableServiceCodes, serviceSpec, unitChoices, type Service } from '../serviceCatalog';
import type { ServiceCode } from '../labels';
import { Evidence, lineNeedsAttention } from './Evidence';
import { Field, SelectField } from './Field';

interface Props {
  line: Service; index: number; lines: Service[]; evidence: FieldEvidence[]; issues: Issue[]; notes: string[]; open: boolean;
  onToggle: (open: boolean) => void; onChange: (patch: Partial<Service>) => void;
  onServiceChange: (code: ServiceCode) => void; onRemove: () => void;
}

function volumeText(line: Service): string {
  const unit = unitText(line.unit, line.unit_label);
  const quantity = line.quantity === null ? null : `${formatDecimal(line.quantity)}${unit ? ` ${unit}` : ''}`;
  const tariff = line.tariff === null ? null : formatTariff(line.tariff);
  if (quantity && tariff) return `${quantity} × ${tariff}`;
  return quantity ?? (tariff ? `Тариф ${tariff}` : 'Объём и тариф не указаны');
}

export function LineCard({ line, index, lines, evidence, issues, notes, open, onToggle, onChange, onServiceChange, onRemove }: Props) {
  const spec = serviceSpec(line.service_code);
  const at = (field: string) => `/services/${index}/${field}`;
  const note = (field: string) => <Evidence path={at(field)} evidence={evidence} issues={issues} />;
  const choices = availableServiceCodes(lines, line.line_id);
  const scopes = spec.scopes.includes(line.scope) ? spec.scopes : [...spec.scopes, line.scope];
  const segmentKnown = line.segment_key === null || spec.segments.some((item) => item.key === line.segment_key);
  return <details className="service-row" open={open} onToggle={(event) => onToggle(event.currentTarget.open)}>
    <summary>
      <div className="line-summary">
        <span className="line-title">{index + 1}. {line.raw_name || 'Без названия'}</span>
        <span className="line-amount">{line.charge_amount === null ? 'нет суммы' : formatMoney(line.charge_amount)}</span>
        <span className="line-meta">
          <span className="chip chip--info">{serviceLabel(line.service_code)}</span>
          {lineNeedsAttention(index, evidence, issues) && <span className="chip chip--warn">Проверьте</span>}
          <span>{volumeText(line)}</span>
        </span>
      </div>
    </summary>
    <div className="line-body">
      <Field label="Название в квитанции" value={line.raw_name} maxLength={200} onChange={(value) => onChange({ raw_name: value ?? '' })} hint={note('raw_name')} />
      <SelectField label="Вид услуги" value={line.service_code} onChange={(value) => onServiceChange(value as ServiceCode)}
        hint={<>{note('service_code')}<p className="field-hint">Каждый вид услуги можно выбрать только в одной строке; «Прочее» — в любом числе строк.</p></>}>
        {choices.map((choice) => <option key={choice.code} value={choice.code} disabled={choice.takenBy !== null && choice.code !== line.service_code}>
          {choice.label}{choice.takenBy !== null && choice.code !== line.service_code ? ` — уже выбрано в строке ${choice.takenBy}` : ''}</option>)}
      </SelectField>
      {notes.map((text) => <p key={text} className="review-warning" role="status">{text}</p>)}
      <div className="grid-2">
        <Field label="Объём" value={line.quantity} inputMode="decimal" maxLength={24} onChange={(value) => onChange({ quantity: value })} hint={note('quantity')} />
        <SelectField label="Единица" value={line.unit ?? ''}
          onChange={(value) => onChange({ unit: (value || null) as Service['unit'], unit_label: value === 'other' ? line.unit_label : null })}
          hint={note('unit')}>
          <option value="">Не указана</option>
          {unitChoices(line.service_code, line.unit).map((unit) => <option key={unit} value={unit}>{unitLabels[unit]}</option>)}
        </SelectField>
        <Field label="Тариф" value={line.tariff} inputMode="decimal" maxLength={24} onChange={(value) => onChange({ tariff: value })} hint={note('tariff')} />
        <Field label="Сумма, ₽" value={line.charge_amount} inputMode="decimal" maxLength={20} onChange={(value) => onChange({ charge_amount: value })} hint={note('charge_amount')} />
      </div>
      <details>
        <summary>Дополнительно</summary>
        <SelectField label="Область начисления" value={line.scope} onChange={(value) => onChange({ scope: value as Service['scope'] })} hint={note('scope')}>
          {scopes.map((scope) => <option key={scope} value={scope}>{scopeLabels[scope]}</option>)}
        </SelectField>
        {(spec.segments.length > 0 || !segmentKnown) && <SelectField label="Сегмент" value={line.segment_key ?? ''} onChange={(value) => onChange({ segment_key: value || null })}>
          <option value="">Не указан</option>
          {spec.segments.map((item) => <option key={item.key} value={item.key}>{item.label}</option>)}
          {!segmentKnown && <option value={line.segment_key ?? ''}>Другой (из документа)</option>}
        </SelectField>}
        {line.unit === 'other' && <Field label="Пояснение к единице" value={line.unit_label} maxLength={200} onChange={(value) => onChange({ unit_label: value })} />}
      </details>
      <button type="button" className="danger" onClick={onRemove}>Удалить строку</button>
    </div>
  </details>;
}
