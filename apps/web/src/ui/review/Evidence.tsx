import type { FieldEvidence, Issue } from '../../api/types';
import { evidenceSourceLabel } from '../labels';

/** A short note under a field: what to re-check, or that the value was typed by hand. Nothing is shown for calm fields. */
export function Evidence({ path, evidence, issues }: { path: string; evidence: FieldEvidence[]; issues: Issue[] }) {
  const notes = evidence.filter((item) => item.path === path);
  const warnings = issues.filter((item) => item.path === path && item.severity !== 'info');
  const check = notes.find((item) => item.needs_review);
  const manual = !check && notes.some((item) => item.source === 'manual');
  if (!check && !manual && !warnings.length) return null;
  return <div className="field-note">
    {check && <p className="review-warning">
      Проверьте по квитанции · {evidenceSourceLabel(check.source)}
      {check.page_number ? ` · стр. ${check.page_number}` : ''}{check.source_text ? ` · «${check.source_text}»` : ''}
    </p>}
    {manual && <p>Введено вами</p>}
    {warnings.map((item, index) => <p key={index} className="review-warning">{item.message}</p>)}
  </div>;
}

/** True when the line or any of its fields carries something the user should look at. */
export function lineNeedsAttention(index: number, evidence: FieldEvidence[], issues: Issue[]): boolean {
  const prefix = `/services/${index}`;
  const under = (path: string | null) => path === prefix || (path?.startsWith(`${prefix}/`) ?? false);
  return evidence.some((item) => item.needs_review && under(item.path)) || issues.some((item) => item.severity !== 'info' && under(item.path));
}
