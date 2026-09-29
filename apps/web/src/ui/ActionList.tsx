import { Link } from 'react-router-dom';
import type { NextAction } from '../api/types';

const routeByTarget: Record<NonNullable<NextAction['target']>, string> = {
  receipt_upload: '/upload', receipt_history: '/history', receipt_detail: '/history', comparison: '/comparison',
};

function targetFor(action: NextAction): string | null {
  if (action.type === 'prepare_draft') {
    const query = new URLSearchParams();
    if (action.receipt_ref) query.set('receipt', action.receipt_ref.id);
    if (action.topic_id) query.set('topic', action.topic_id);
    return `/draft${query.size ? `?${query}` : ''}`;
  }
  if (action.type === 'select_topic' && action.topic_id) return `/assistant?topic=${encodeURIComponent(action.topic_id)}${action.receipt_ref ? `&receipt=${encodeURIComponent(action.receipt_ref.id)}` : ''}`;
  if (action.type === 'navigate' && action.target) {
    if (action.target === 'receipt_detail') return action.receipt_ref ? `/review?id=${encodeURIComponent(action.receipt_ref.id)}` : null;
    return routeByTarget[action.target];
  }
  return null;
}

export function ActionList({ actions }: { actions: NextAction[] }) {
  if (!actions.length) return null;
  return <div className="notice-box"><h4>Следующие шаги</h4><ul>{actions.map((action) => {
    const route = targetFor(action);
    let external: string | null = null;
    if (action.type === 'open_link' && action.url) {
      try { const parsed = new URL(action.url); if (parsed.protocol === 'https:') external = parsed.href; } catch { /* Bad URL stays plain text. */ }
    }
    return <li key={action.id}>{route ? <Link to={route}>{action.label}</Link> : external ? <a href={external} target="_blank" rel="noopener noreferrer">{action.label}</a> : action.label}
      {!!action.requires.length && <span> · требуется: {action.requires.join(', ')}</span>}
    </li>;
  })}</ul></div>;
}
