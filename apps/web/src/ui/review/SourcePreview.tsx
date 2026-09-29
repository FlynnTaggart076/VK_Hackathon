import { useEffect, useState } from 'react';
import { api } from '../../api/client';
import type { ReceiptView } from '../../api/types';
import { ErrorMessage } from '../errors';

/** Original document: a compact page view that can be collapsed, opened large or downloaded. */
export function SourcePreview({ receipt }: { receipt: ReceiptView }) {
  const [page, setPage] = useState(1);
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [reloadPage, setReloadPage] = useState(0);
  useEffect(() => {
    setUrl(null); setError(null);
    if (!receipt.document.available) return;
    const controller = new AbortController();
    let objectUrl: string | null = null;
    api.page(receipt.id, page, controller.signal).then((blob) => {
      if (!controller.signal.aborted) { objectUrl = URL.createObjectURL(blob); setUrl(objectUrl); }
    }).catch((cause) => { if (!(cause instanceof DOMException && cause.name === 'AbortError')) setError(cause); });
    return () => { controller.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [receipt.id, receipt.document.available, page, reloadPage]);
  async function download() {
    setBusy(true); setError(null);
    try {
      const blob = await api.source(receipt.id);
      const objectUrl = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = objectUrl;
      anchor.download = `platezhka.${receipt.document.mime_type === 'application/pdf' ? 'pdf' : receipt.document.mime_type === 'image/jpeg' ? 'jpg' : 'png'}`;
      anchor.click(); setTimeout(() => URL.revokeObjectURL(objectUrl), 10000);
    } catch (cause) { setError(cause); }
    finally { setBusy(false); }
  }
  const pages = receipt.document.page_count ?? 1;
  return <details className="notice-box" open aria-label="Исходный документ"><summary><strong>Оригинал документа</strong></summary>
    {!receipt.document.available ? <p>Срок хранения исходника истёк или файл недоступен. Сохранённые цифры можно проверить, но страницу показать нельзя.</p> : <>
      {url ? <><img className="receipt-page" src={url} alt={`Страница ${page} исходной платёжки`} /><p><a href={url} target="_blank" rel="noopener noreferrer">Открыть страницу крупно</a></p></> : !error && <p role="status">Загружаем защищённый просмотр страницы…</p>}
      <ErrorMessage error={error} />
      {error && <button type="button" onClick={() => setReloadPage((value) => value + 1)}>Повторить просмотр страницы</button>}
      {pages > 1 && <div className="actions">
        <button type="button" className="secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>Предыдущая</button>
        <span>Страница {page} из {pages}</span>
        <button type="button" className="secondary" disabled={page >= pages} onClick={() => setPage(page + 1)}>Следующая</button>
      </div>}
      <button type="button" className="secondary" disabled={busy} onClick={() => void download()}>{busy ? 'Скачиваем…' : 'Скачать исходник'}</button>
    </>}
  </details>;
}
