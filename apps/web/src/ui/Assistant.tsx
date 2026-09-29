import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { api, ApiRequestError, hasSessionToken } from '../api/client';
import { PREVIEW_MODE } from '../api/appConfig';
import type { DialogLink, DialogReply, DialogRequest, ReceiptView } from '../api/types';
import { ActionList } from './ActionList';
import { ErrorMessage } from './errors';

type Message = { id: number; role: 'user' | 'bot'; text: string; reply?: DialogReply };

/** Opens an https link through MAX Bridge when available, otherwise in a new tab. */
export function openExternal(url: string): boolean {
  let parsed: URL;
  try { parsed = new URL(url); } catch { return false; }
  if (parsed.protocol !== 'https:') return false;
  const bridge = window.WebApp?.openLink;
  if (typeof bridge === 'function') { bridge(parsed.href); return true; }
  return false;
}

export function safeLinks(links: DialogLink[]): DialogLink[] {
  return links.filter((link) => { try { return new URL(link.url).protocol === 'https:'; } catch { return false; } });
}

function LinkList({ links }: { links: DialogLink[] }) {
  const items = safeLinks(links);
  if (!items.length) return null;
  return <ul className="chat-links">{items.map((link) => <li key={link.url}>
    <a href={link.url} target="_blank" rel="noopener noreferrer"
      onClick={(event) => { if (openExternal(link.url)) event.preventDefault(); }}>{link.label}</a>
    <small> · {new URL(link.url).hostname}</small>
  </li>)}</ul>;
}

function Card({ card }: { card: NonNullable<DialogReply['card']> }) {
  const phoneDigits = card.management.phone?.replace(/\D/g, '') ?? '';
  return <div className="house-card-wrap">
    {card.intro && <p className="chat-text">{card.intro}</p>}
    <dl className="house-card">
    <div><dt>Дом</dt><dd>{card.address}</dd></div>
    {card.service.code !== 'management' && <div><dt>{card.service.name}</dt><dd>{card.provider
      ? <>{card.provider.name}{card.service.status === 'candidate' && <small> · по историческим открытым данным, сверьте с квитанцией</small>}</>
      : card.service.status === 'not_available' ? (card.service.note ?? 'Система в доме отсутствует') : 'Поставщик в открытых данных не найден'}</dd></div>}
    <div><dt>Управляющая организация</dt><dd>{card.management.name ?? 'не указана в источнике'}</dd></div>
    {card.management.phone && <div><dt>Телефон УК</dt><dd>{phoneDigits.length === 11 ? <a href={`tel:+${phoneDigits}`}>{card.management.phone}</a> : card.management.phone}</dd></div>}
    {card.management.email && <div><dt>Почта УК</dt><dd>{card.management.email}</dd></div>}
    <div><dt>Источник</dt><dd>HouseScore, данные от {card.management.fetched_at}{card.source.url ? ' · Dominfo' : ''}</dd></div>
  </dl>
    {card.warnings.length > 0 && <p className="review-warning">{card.warnings.join(' ')}</p>}
  </div>;
}

export function Assistant() {
  const [params] = useSearchParams();
  const receiptId = params.get('receipt');
  const topic = params.get('topic');
  const [receipt, setReceipt] = useState<ReceiptView | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [question, setQuestion] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [lastRequest, setLastRequest] = useState<DialogRequest | null>(null);
  const pending = useRef<AbortController | null>(null);
  const counter = useRef(0);
  const bottom = useRef<HTMLDivElement | null>(null);

  const confirmed = receipt?.status === 'confirmed' ? receipt : null;

  async function send(body: DialogRequest, shown: string | null) {
    pending.current?.abort();
    const controller = new AbortController();
    pending.current = controller;
    setBusy(true); setError(null); setLastRequest(body);
    if (shown) setMessages((current) => [...current, { id: ++counter.current, role: 'user', text: shown }]);
    try {
      const request: DialogRequest = confirmed ? { ...body, receipt_id: confirmed.id, receipt_revision: confirmed.revision } : body;
      const reply = await api.dialog(request, controller.signal);
      if (pending.current !== controller) return; // A newer message already replaced this one.
      setMessages((current) => [...current, { id: ++counter.current, role: 'bot', text: reply.text, reply }]);
      setLastRequest(null);
    } catch (cause) {
      if (!(cause instanceof DOMException && cause.name === 'AbortError')) setError(cause);
    } finally {
      if (pending.current === controller) { pending.current = null; setBusy(false); }
    }
  }

  useEffect(() => () => pending.current?.abort(), []);
  useEffect(() => {
    let active = true; setReceipt(null);
    if (receiptId) api.receipt(receiptId).then((value) => { if (active) setReceipt(value); })
      .catch((cause) => { if (active) setError(cause); });
    return () => { active = false; };
  }, [receiptId]);
  useEffect(() => {
    if (!hasSessionToken() || (receiptId && !receipt)) return;
    setMessages([]);
    void send(topic ? { choice: `topic:${topic}` } : { message: null }, null);
  }, [topic, receiptId, receipt?.id, receipt?.revision]);
  useEffect(() => { bottom.current?.scrollIntoView?.({ block: 'end', behavior: 'smooth' }); }, [messages.length]);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = question.trim();
    if (!text || busy) return;
    setQuestion('');
    void send({ message: text.slice(0, 2000) }, text);
  }

  const latest = [...messages].reverse().find((item) => item.role === 'bot')?.id;
  return <section className="panel assistant">
    <h2>Помощник</h2>
    <p className="notice">Найду управляющую компанию и поставщиков по адресу дома, подскажу, куда передать показания, и объясню квитанцию. Ничего никуда не отправляю.</p>
    {receiptId && <div className="notice-box">
      <p>Документ: {receipt ? `${receipt.bill_data.period ?? 'без периода'} · версия ${receipt.revision}` : 'загружаем…'}</p>
      {receipt && receipt.status !== 'confirmed' && <p className="review-warning">Вопросы по документу доступны после подтверждения его данных. <Link to={`/review?id=${encodeURIComponent(receipt.id)}`}>Проверить данные</Link></p>}
      {receipt?.dataset_kind === 'synthetic' && <p className="badge">Синтетический пример</p>}
      {PREVIEW_MODE && confirmed?.dataset_kind === 'synthetic' && <p><Link to={`/city-comparison?receipt=${encodeURIComponent(confirmed.id)}`}>Сравнить с учебной выборкой</Link> — отдельное числовое сравнение, без данных реальных жителей.</p>}
    </div>}
    <div className="chat" aria-live="polite">
      {messages.map((message) => message.role === 'user'
        ? <p key={message.id} className="bubble user"><span className="sr-only">Вы: </span>{message.text}</p>
        : <article key={message.id} className={`bubble bot${message.reply?.status === 'unsupported' ? ' limited' : ''}`}>
          <span className="sr-only">Помощник: </span>
          {message.reply?.card ? <Card card={message.reply.card} /> : <p className="chat-text">{message.text}</p>}
          {message.reply && <LinkList links={message.reply.links} />}
          {message.reply && message.id === latest && <ActionList actions={message.reply.actions} />}
          {message.reply?.dataset_kind === 'synthetic' && <p className="badge">Учебные данные</p>}
          {message.reply && message.id === latest && message.reply.options.length > 0 && <div className="suggestion-buttons" role="group" aria-label="Варианты ответа">
            {message.reply.options.map((option) => <button key={option.value} type="button" disabled={busy}
              onClick={() => void send({ choice: option.value }, option.label)}>{option.label}</button>)}
          </div>}
        </article>)}
      {PREVIEW_MODE && confirmed?.dataset_kind === 'synthetic' && messages.some((item) => item.role === 'user') &&
        <p><Link to={`/city-comparison?receipt=${encodeURIComponent(confirmed.id)}`}>Проверить по учебной выборке</Link> · числовое сравнение с фиксированными синтетическими значениями.</p>}
      {busy && <p className="notice" role="status">Помощник отвечает…</p>}
      <div ref={bottom} />
    </div>
    <ErrorMessage error={error} />
    {error !== null && lastRequest && <button type="button" disabled={busy} onClick={() => void send(lastRequest, null)}>
      {error instanceof ApiRequestError && error.status === 409 ? 'Обновить диалог' : 'Повторить'}</button>}
    {!hasSessionToken() && <p>Войдите на главной, чтобы задать вопрос.</p>}
    <form className="chat-form" onSubmit={submit}>
      <label htmlFor="question">Ваш вопрос</label>
      <textarea id="question" value={question} rows={2} maxLength={2000} placeholder="Например: контакты УК, куда передать показания воды"
        onChange={(event) => setQuestion(event.target.value)}
        onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); } }} />
      <div className="actions">
        <button type="submit" disabled={busy || !question.trim() || !hasSessionToken()}>Спросить</button>
        <button type="button" className="secondary" disabled={busy || !hasSessionToken()} onClick={() => { setMessages([]); void send({ reset: true }, null); }}>Новый вопрос</button>
      </div>
    </form>
  </section>;
}
