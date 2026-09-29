import type { Issue } from '../../api/types';

export interface IssueGroup { code: string; severity: Issue['severity']; message: string; places: number }

const order: Record<Issue['severity'], number> = { error: 0, warning: 1, info: 2 };

/**
 * The server asks for an acknowledgement per issue code, so equal codes share one line:
 * the first message is shown and the number of affected places is counted.
 */
export function groupIssues(issues: Issue[]): IssueGroup[] {
  const groups = new Map<string, IssueGroup & { paths: Set<string> }>();
  for (const issue of issues) {
    const key = `${issue.severity}:${issue.code}`;
    const group = groups.get(key) ?? { code: issue.code, severity: issue.severity, message: issue.message, places: 0, paths: new Set<string>() };
    group.paths.add(issue.path ?? `#${group.paths.size}`);
    group.places = group.paths.size;
    groups.set(key, group);
  }
  return [...groups.values()].sort((a, b) => order[a.severity] - order[b.severity])
    .map(({ code, severity, message, places }) => ({ code, severity, message, places }));
}
