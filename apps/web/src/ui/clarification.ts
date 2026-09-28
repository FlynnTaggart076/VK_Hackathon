import type { AnswerView, Catalog } from '../api/types';

export type Clarification = NonNullable<AnswerView['clarification']>;
export type ClarificationField = Clarification['field'];
export type Suggestion = { value: string; label: string };

export const clarificationLabels: Record<ClarificationField, string> = {
  topic_id: 'Тема вопроса',
  territory_id: 'Территория',
  role: 'Ваша роль',
  organization_id: 'Организация',
  service_code: 'Услуга',
  document_kind: 'Вид документа',
};

export function suggestionsFor(field: ClarificationField, catalog: Catalog, options: Suggestion[]): Suggestion[] {
  const catalogOptions: Suggestion[] = field === 'topic_id' ? catalog.topics.map(({ id, label }) => ({ value: id, label }))
    : field === 'territory_id' ? catalog.territories.map(({ id, label }) => ({ value: id, label }))
      : field === 'organization_id' ? catalog.organizations.map(({ id, label }) => ({ value: id, label }))
        : field === 'document_kind' ? catalog.document_kinds.map(({ id, label }) => ({ value: id, label }))
          : field === 'service_code' ? catalog.service_codes.map((value) => ({ value, label: value }))
            : field === 'role' ? [
              { value: 'owner', label: 'Собственник' },
              { value: 'tenant', label: 'Арендатор' },
              { value: 'other', label: 'Другое' },
            ] : [];
  const unique = new Map<string, Suggestion>();
  for (const suggestion of [...options, ...catalogOptions]) unique.set(suggestion.value, suggestion);
  return [...unique.values()];
}

export function selectedValue(input: string, suggestions: Suggestion[]): string {
  const value = input.trim();
  const match = suggestions.find((item) => item.value.toLocaleLowerCase('ru') === value.toLocaleLowerCase('ru') ||
    item.label.toLocaleLowerCase('ru') === value.toLocaleLowerCase('ru'));
  return match?.value ?? value;
}

const serviceAliases: Record<string, string> = {
  'холодная вода': 'cold_water', 'хвс': 'cold_water',
  'горячая вода': 'hot_water', 'гвс': 'hot_water',
  'водоотведение': 'drainage', 'канализация': 'drainage',
  'электричество': 'electricity', 'электроэнергия': 'electricity',
  'отопление': 'heating', 'содержание жилья': 'maintenance',
  'капремонт': 'capital_repair', 'капитальный ремонт': 'capital_repair',
  'вывоз мусора': 'waste', 'тко': 'waste',
};
const serviceCodes = new Set(['cold_water', 'hot_water', 'drainage', 'electricity', 'heating', 'maintenance', 'capital_repair', 'waste', 'other']);

export function serviceContext(input: string | undefined): { code: string | null; freeText: string | null } {
  const typed = input?.trim() ?? '';
  if (!typed) return { code: null, freeText: null };
  const lower = typed.toLocaleLowerCase('ru');
  const code = serviceCodes.has(lower) ? lower : serviceAliases[lower];
  return code ? { code, freeText: null } : { code: 'other', freeText: typed };
}
