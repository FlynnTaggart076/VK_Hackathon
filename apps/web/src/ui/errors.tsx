import { ApiRequestError } from '../api/client';

export function ErrorMessage({ error }: { error: unknown }) {
  if (error === null || error === undefined) return null;
  let message = error instanceof Error ? error.message : 'Не удалось выполнить запрос.';
  if (error instanceof ApiRequestError) {
    if (error.status === 401) message = import.meta.env.DEV
      ? 'Сессия истекла. Войдите снова, чтобы продолжить.'
      : 'Вход MAX недействителен или сессия истекла. Переоткройте мини-приложение в MAX.';
    else if (error.code === 'PREVIEW_NOT_READY') message = 'Предпросмотр ещё готовится. Повторите загрузку страницы чуть позже.';
    else if (error.status === 409) message = `Конфликт данных: ${error.message}`;
    else if (error.status === 410) message = 'Срок хранения исходного файла истёк. Извлечённые данные остаются в истории.';
    else if (error.status === 413) message = `Файл не принят: ${error.message}`;
    else if (error.status === 422) message = `Проверьте данные: ${error.message}`;
  } else if (error instanceof TypeError) message = 'Нет соединения с сервером. Проверьте сеть и повторите попытку.';
  return <p role="alert" className="error">{message}{error instanceof ApiRequestError && <small>Код: {error.code}; запрос: {error.requestId}</small>}</p>;
}
