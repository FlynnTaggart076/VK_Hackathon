import type { Issue } from '../../api/types';
import { plural } from '../labels';
import { groupIssues } from './issues';

/**
 * Everything the server wants the user to know before confirming, grouped by issue code.
 * Warnings need one acknowledgement per code; errors block; information is only shown.
 */
export function IssuesPanel({ issues, acknowledged, onAcknowledge, canAcknowledge }: {
  issues: Issue[]; acknowledged: string[]; onAcknowledge: (code: string, checked: boolean) => void; canAcknowledge: boolean;
}) {
  const groups = groupIssues(issues);
  if (!groups.length) return null;
  const places = (count: number) => count > 1 ? ` (${count} ${plural(count, ['место', 'места', 'мест'])})` : '';
  const errors = groups.filter((item) => item.severity === 'error');
  const warnings = groups.filter((item) => item.severity === 'warning');
  const infos = groups.filter((item) => item.severity === 'info');
  return <section className="notice-box" aria-label="Замечания к данным">
    <h3>Проверьте перед подтверждением</h3>
    {errors.length > 0 && <div className="error" role="alert"><strong>Нужно исправить:</strong>
      <ul>{errors.map((item) => <li key={item.code}>{item.message}{places(item.places)}</li>)}</ul></div>}
    {warnings.map((item) => canAcknowledge
      ? <label className="check" key={item.code}>
        <input type="checkbox" checked={acknowledged.includes(item.code)} onChange={(event) => onAcknowledge(item.code, event.target.checked)} />
        Принимаю предупреждение: {item.message}{places(item.places)}
      </label>
      : <p className="review-warning" key={item.code}>{item.message}{places(item.places)}</p>)}
    {infos.map((item) => <p className="notice" key={item.code}>{item.message}</p>)}
  </section>;
}
