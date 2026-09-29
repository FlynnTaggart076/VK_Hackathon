import type { BillData, FieldEvidence, Issue } from '../../api/types';
import { Evidence } from './Evidence';
import { Field } from './Field';

/** Document totals; the settlement details are collapsed because most people never need them. */
export function TotalsSection({ draft, evidence, issues, onChange, onSettlementChange }: {
  draft: BillData; evidence: FieldEvidence[]; issues: Issue[];
  onChange: <K extends keyof BillData>(key: K, value: BillData[K]) => void;
  onSettlementChange: <K extends keyof BillData['settlement']>(key: K, value: BillData['settlement'][K]) => void;
}) {
  const note = (path: string) => <Evidence path={path} evidence={evidence} issues={issues} />;
  const settlement = draft.settlement;
  const inSettlement = (path: string | null) => !!path && path.startsWith('/settlement');
  const attention = evidence.some((item) => item.needs_review && inSettlement(item.path)) ||
    issues.some((item) => item.severity !== 'info' && inSettlement(item.path));
  return <>
    <h3>Итоги документа</h3>
    <Field label="Начислено за текущий период, ₽" value={draft.document_current_charges} inputMode="decimal" maxLength={20}
      onChange={(value) => onChange('document_current_charges', value)} hint={note('/document_current_charges')} />
    <Field label="К оплате по документу, ₽" value={draft.document_total_due} inputMode="decimal" maxLength={20}
      onChange={(value) => onChange('document_total_due', value)} hint={note('/document_total_due')} />
    <details className="notice-box" open={attention || undefined}>
      <summary><strong>Расчёты по лицевому счёту</strong></summary>
      <p className="field-hint" style={{ margin: '8px 0' }}>
        Формула остатка: {settlement.formula_kind === 'signed_balance_v1' ? 'остаток с учётом оплат' : 'не определена'}. Её выбирает сервер по макету документа.
      </p>
      <Field label="Остаток на начало, ₽" value={settlement.opening_balance} maxLength={20} onChange={(value) => onSettlementChange('opening_balance', value)} />
      <Field label="Учтённые оплаты, ₽" value={settlement.payments_credited} inputMode="decimal" maxLength={20} onChange={(value) => onSettlementChange('payments_credited', value)} />
      <Field label="Пени, ₽" value={settlement.penalties} maxLength={20} onChange={(value) => onSettlementChange('penalties', value)} />
      <Field label="Другие изменения счёта, ₽" value={settlement.other_account_changes} maxLength={20} onChange={(value) => onSettlementChange('other_account_changes', value)} />
      <Field label="Остаток по документу, ₽" value={settlement.document_closing_balance} maxLength={20} onChange={(value) => onSettlementChange('document_closing_balance', value)} />
    </details>
  </>;
}
