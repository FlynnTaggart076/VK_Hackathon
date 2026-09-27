import { useEffect, useRef, useState } from 'react';
import { Link, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { api, ApiRequestError, hasSessionToken, setSessionToken } from '../api/client';
import type { AnswerContext, AnswerView, MetaResponse } from '../api/types';

const mockEnabled = import.meta.env.DEV && import.meta.env.VITE_ENABLE_MOCK === 'true';
const screens = [
  { path: '/', title: 'Главная', text: 'Вопросы, платёжки, история и учебные примеры.', states: 'пустая история, demo-пометка' },
  { path: '/onboarding', title: 'Первый запуск', text: 'Роль, территория и уведомление об обработке документов.', states: 'незаполнено, сохранение, ошибка' },
  { path: '/upload', title: 'Загрузка', text: 'Выбор документа, ограничения и учебный пример.', states: 'upload, rejected, retry' },
  { path: '/processing', title: 'Обработка', text: 'Этап обработки и возврат к истории.', states: 'queued, processing, failed, completed' },
  { path: '/review', title: 'Проверка', text: 'Исходник, реквизиты и исправляемые строки.', states: 'missing, warning, invalid, saving, revision conflict' },
  { path: '/explanation', title: 'Объяснение', text: 'Начисления и итог к оплате показываются отдельно.', states: 'complete, partial, source expired' },
  { path: '/comparison', title: 'Сравнение', text: 'Выбор двух документов и объяснение различий.', states: 'incompatible, identity confirmation, ambiguous, partial' },
  { path: '/draft', title: 'Черновик', text: 'Проверка, редактирование и копирование текста.', states: 'copied, clipboard unavailable, stale' },
  { path: '/history', title: 'История и настройки', text: 'Документы, удаление и профиль.', states: 'empty, pagination, deleting, error' },
] as const;

function ErrorMessage({ error }: { error: unknown }) {
  if (!error) return null;
  const message = error instanceof Error ? error.message : 'Не удалось выполнить запрос.';
  return <p role="alert" className="error">{message}{error instanceof ApiRequestError && <small> Код: {error.code}; запрос: {error.requestId}</small>}</p>;
}

function Entry({ meta, onAuth }: { meta: MetaResponse | null; onAuth: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  async function enterDemo() {
    setBusy(true); setError(null);
    try {
      const result = await api.demoAuth('mock-only');
      setSessionToken(result.access_token);
      onAuth();
    } catch (cause) { setError(cause); }
    finally { setBusy(false); }
  }
  return <section className="panel">
    <h2>Вход</h2>
    <p>В рабочей версии вход происходит в MAX после проверки стартовых данных сервером.</p>
    {meta && <p>API {meta.api_version} · База знаний {meta.knowledge_version}</p>}
    {mockEnabled ? <button type="button" onClick={() => void enterDemo()} disabled={busy}>{busy ? 'Входим…' : 'Войти в учебный mock'}</button> : <p>Откройте приложение внутри MAX. Подключение MAX Bridge запланировано на следующий этап.</p>}
    <ErrorMessage error={error} />
  </section>;
}

function Assistant() {
  const [question, setQuestion] = useState('Почему выросла сумма за воду?');
  const [answer, setAnswer] = useState<AnswerView | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const pending = useRef<AbortController | null>(null);
  useEffect(() => {
    return () => pending.current?.abort();
  }, []);
  async function ask(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!question.trim()) return;
    const context: AnswerContext = {
      territory_id: 'demo-territory', role: 'tenant', topic_id: null,
      organization_id: null, service_code: null, document_kind: null,
      receipt_id: null, receipt_revision: null,
    };
    setBusy(true); setError(null); setAnswer(null);
    pending.current?.abort();
    const controller = new AbortController();
    pending.current = controller;
    try { setAnswer(await api.answer(question.trim(), context, controller.signal)); }
    catch (cause) { if (!(cause instanceof DOMException && cause.name === 'AbortError')) setError(cause); }
    finally { if (pending.current === controller) { pending.current = null; setBusy(false); } }
  }
  return <section className="panel">
    <h2>Помощник</h2>
    <form onSubmit={(event) => void ask(event)}>
      <label htmlFor="question">Ваш вопрос</label>
      <textarea id="question" value={question} onChange={(event) => setQuestion(event.target.value)} maxLength={2000} rows={3} />
      <button disabled={busy || !hasSessionToken()}>{busy ? 'Ищем ответ…' : 'Спросить'}</button>
    </form>
    {!hasSessionToken() && <p>Для примера войдите через учебный mock на главной.</p>}
    <ErrorMessage error={error} />
    {answer && <article aria-live="polite" className="answer">
      <p className="badge">{answer.dataset_kind === 'synthetic' ? 'Синтетический пример' : answer.dataset_kind}</p>
      <h3>{answer.status === 'unsupported' ? 'Пока нет проверенного ответа' : answer.status === 'needs_clarification' ? 'Нужно уточнение' : 'Ответ'}</h3>
      <p>{answer.text}</p>
      {answer.clarification && <p>{answer.clarification.prompt}</p>}
      {answer.sources.map((source) => <p key={source.id}>Источник: {source.title}{source.url && <a href={source.url} target="_blank" rel="noopener noreferrer"> {source.url}</a>}</p>)}
      {answer.limitations.map((item) => <p key={item}>{item}</p>)}
    </article>}
  </section>;
}

function Page({ path }: { path: typeof screens[number]['path'] }) {
  const screen = screens.find((item) => item.path === path)!;
  return <section className="panel">
    <h2>{screen.title}</h2>
    {path === '/' ? <>
      <p>Задайте вопрос, разберите платёжку или вернитесь к истории.</p>
      {mockEnabled && <p className="badge">Учебный mock · синтетические данные</p>}
      <div className="actions"><Link to="/assistant">Задать вопрос</Link><Link to="/upload">Разобрать платёжку</Link></div>
    </> : <><p>{screen.text}</p><p className="notice">Экран E0: пользовательский путь будет реализован на следующих этапах.</p><p>Состояния для реализации: {screen.states}.</p></>}
  </section>;
}

export function App() {
  const [meta, setMeta] = useState<MetaResponse | null>(null);
  const [metaError, setMetaError] = useState<unknown>(null);
  const [authenticated, setAuthenticated] = useState(hasSessionToken());
  const location = useLocation();
  useEffect(() => {
    const controller = new AbortController();
    api.meta(controller.signal).then(setMeta).catch((cause) => {
      if (!(cause instanceof DOMException && cause.name === 'AbortError')) setMetaError(cause);
    });
    return () => controller.abort();
  }, []);
  return <div className="app">
    <a className="skip" href="#content">К содержимому</a>
    <header><h1>Помощник ЖКХ</h1><p>Первые вопросы о платёжке и следующий шаг</p></header>
    <nav aria-label="Основная навигация"><Link to="/">Главная</Link><Link to="/assistant">Помощник</Link><Link to="/upload">Платёжка</Link><Link to="/history">История</Link></nav>
    <main id="content" tabIndex={-1}>
      {metaError !== null && <ErrorMessage error={metaError} />}
      {location.pathname === '/' && (!authenticated || mockEnabled) && <Entry meta={meta} onAuth={() => setAuthenticated(true)} />}
      <Routes>
        {screens.map(({ path }) => <Route key={path} path={path} element={<Page path={path} />} />)}
        <Route path="/assistant" element={<Assistant />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </main>
    <footer>Учебный интерфейс E0. Данные и ответы требуют проверки.</footer>
  </div>;
}
