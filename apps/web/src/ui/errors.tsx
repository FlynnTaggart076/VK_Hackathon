import { ApiRequestError } from '../api/client';

/** A server message is shown only when it is Russian; anything else gets a neutral sentence. */
function russian(text: string | undefined, fallback: string): string {
  return text && /[а-яё]/i.test(text) ? text : fallback;
}

export function errorText(error: unknown): string {
  if (error instanceof ApiRequestError) {
    if (error.status === 401) return import.meta.env.DEV
      ? 'Сессия истекла. Войдите снова, чтобы продолжить.'
      : 'Вход в MAX недействителен или сессия истекла. Переоткройте мини-приложение в MAX.';
    if (error.code === 'PREVIEW_NOT_READY') return 'Просмотр страницы ещё готовится. Повторите загрузку чуть позже.';
    if (error.status === 409) return `Данные изменились: ${russian(error.message, 'обновите страницу и повторите действие')}`;
    if (error.status === 410) return 'Срок хранения исходного файла истёк. Извлечённые данные остаются в истории.';
    if (error.status === 413) return `Файл не принят: ${russian(error.message, 'он слишком большой')}`;
    if (error.status === 422) return `Проверьте данные: ${russian(error.message, 'некоторые поля заполнены неверно')}`;
    if (error.status === 429) return 'Слишком много запросов. Подождите минуту и повторите.';
    if (error.status >= 500) return russian(error.message, 'Сервис временно недоступен. Повторите чуть позже.');
    return russian(error.message, 'Не удалось выполнить запрос.');
  }
  if (error instanceof TypeError) return 'Нет соединения с сервером. Проверьте сеть и повторите попытку.';
  if (error instanceof Error) return russian(error.message, 'Не удалось выполнить запрос.');
  return 'Не удалось выполнить запрос.';
}

export function ErrorMessage({ error }: { error: unknown }) {
  if (error === null || error === undefined) return null;
  const fields = error instanceof ApiRequestError ? error.body.error.fields : [];
  return <div role="alert" className="error">
    <p>{errorText(error)}</p>
    {fields.length > 0 && <ul>{fields.map((field, index) => <li key={index}>{russian(field.message, 'Проверьте это поле.')}</li>)}</ul>}
    {error instanceof ApiRequestError && <details><summary>Подробности для поддержки</summary>
      <small>Номер запроса: {error.requestId}. Код ошибки: {error.code}.</small></details>}
  </div>;
}
