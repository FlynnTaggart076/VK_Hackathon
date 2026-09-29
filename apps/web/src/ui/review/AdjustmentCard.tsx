import type { BillData, FieldEvidence, Issue } from '../../api/types';
import { formatMoney } from '../labels';
import { Evidence } from './Evidence';
import { Field, SelectField } from './Field';

type Adjustment = BillData['adjustments'][number];
type Service = BillData['services'][number];

export function AdjustmentCard({ item, index, lines, evidence, issues, onChange, onRemove }: {
  item: Adjustment; index: number; lines: Service[]; evidence: FieldEvidence[]; issues: Issue[];
  onChange: (patch: Partial<Adjustment>) => void; onRemove: () => void;
}) {
  const linked = item.service_line_id === null || lines.some((line) => line.line_id === item.service_line_id);
  return <fieldset>
    <legend>Перерасчёт {index + 1}{item.amount !== null ? ` · ${formatMoney(item.amount)}` : ''}</legend>
    <Field label="Название" value={item.label} maxLength={200} onChange={(value) => onChange({ label: value ?? '' })} />
    <Field label="Сумма, ₽ (может быть отрицательной)" value={item.amount} maxLength={20}
      onChange={(value) => onChange({ amount: value })} hint={<Evidence path={`/adjustments/${index}/amount`} evidence={evidence} issues={issues} />} />
    <SelectField label="Связь со строкой" value={item.service_line_id ?? ''} onChange={(value) => onChange({ service_line_id: value || null })}
      hint={!linked && <p className="review-warning">Связанная строка удалена. Выберите другую или снимите связь.</p>}>
      <option value="">Не связана с отдельной строкой</option>
      {!linked && <option value={item.service_line_id ?? ''}>Строка удалена</option>}
      {lines.map((line, lineIndex) => <option key={line.line_id} value={line.line_id}>{lineIndex + 1}. {line.raw_name || 'Без названия'}</option>)}
    </SelectField>
    <Field label="Период перерасчёта (ГГГГ-ММ)" value={item.related_period} maxLength={7} onChange={(value) => onChange({ related_period: value })} />
    <button type="button" className="danger" onClick={onRemove}>Удалить перерасчёт</button>
  </fieldset>;
}
