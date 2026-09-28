import { useEffect, useRef, useState } from 'react';
import { Link, Navigate, Route, Routes, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { api, ApiRequestError, hasSessionToken, setSessionToken } from '../api/client';
import { PREVIEW_MODE } from '../api/appConfig';
import { previewAuth } from '../api/previewAuth';
import { maxAuth, maxInitData } from '../api/maxAuth';
import type { AnswerContext, AnswerView, Catalog, MetaResponse, Profile, ReceiptView } from '../api/types';
import { Onboarding, canUpload } from './Onboarding';
import { Processing, Upload } from './Upload';
import { ReceiptReview } from './ReceiptReview';
import { ReceiptExplanation } from './ReceiptExplanation';
import { History } from './History';
import { Comparison } from './Comparison';
import { Draft } from './Draft';
import { ActionList } from './ActionList';
import { ErrorMessage } from './errors';

const mockEnabled = import.meta.env.DEV && !PREVIEW_MODE && import.meta.env.VITE_ENABLE_MOCK === 'true';
const screens = [
  { path: '/', title: 'Главная', text: 'Вопросы, платёжки, история и учебные примеры.', states: 'пустая история, demo-пометка' },
] as const;

function Entry({ meta, sessionExpired, onAuth }: { meta: MetaResponse | null; sessionExpired: boolean; onAuth: (profile: Profile) => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [accessCode, setAccessCode] = useState('');
  const [identity, setIdentity] = useState<'reviewer_a' | 'reviewer_b' | ''>('');
  const [bridgeVersion, setBridgeVersion] = useState(0);
  const initData = !import.meta.env.DEV && !PREVIEW_MODE && !sessionExpired ? maxInitData() : null;
  useEffect(() => {
    const ready = () => setBridgeVersion((value) => value + 1);
    window.addEventListener('zhkh:max-bridge-ready', ready);
    return () => window.removeEventListener('zhkh:max-bridge-ready', ready);
  }, []);
  async function enterMax() {
    if (!initData) return;
    setBusy(true); setError(null);
    try {
      const result = await maxAuth(initData);
      setSessionToken(result.access_token);
      onAuth(result.profile);
    } catch (cause) { setError(cause); }
    finally { setBusy(false); }
  }
  useEffect(() => { if (initData) void enterMax(); }, [bridgeVersion]);
  async function enterPreview() {
    setBusy(true); setError(null);
    try {
      const result = await previewAuth();
      setSessionToken(result.access_token);
      onAuth(result.profile);
    } catch (cause) { setError(cause); }
    finally { setBusy(false); }
  }
  useEffect(() => { if (PREVIEW_MODE) void enterPreview(); }, []);
  async function enterDemo(event?: React.FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    setBusy(true); setError(null);
    try {
      const { demoAuth } = await import('../api/devAuth');
      const result = await demoAuth(mockEnabled ? 'mock-only' : accessCode, identity || 'reviewer_a');
      setSessionToken(result.access_token);
      setAccessCode('');
      onAuth(result.profile);
    } catch (cause) { setError(cause); }
    finally { setBusy(false); }
  }
  return <section className="panel">
    <h2>Вход</h2>
    {PREVIEW_MODE ? <>
      <p>Создаём отдельного виртуального гостя для этой вкладки. Код и вход MAX не нужны.</p>
      {sessionExpired && <p role="status">Прежняя учебная сессия истекла. Создаём нового гостя; его история начнётся заново.</p>}
      {error && <button type="button" disabled={busy} onClick={() => void enterPreview()}>Повторить учебный вход</button>}
      {busy && <p role="status">Открываем учебный стенд…</p>}
    </> : <p>В рабочей версии вход происходит в MAX после проверки стартовых данных сервером.</p>}
    {meta && <p>API {meta.api_version} · База знаний {meta.knowledge_version ?? 'ещё не подключена'}</p>}
    {PREVIEW_MODE ? null : mockEnabled ? <button type="button" onClick={() => void enterDemo()} disabled={busy}>{busy ? 'Входим…' : 'Войти в учебный mock'}</button> :
      import.meta.env.DEV && meta?.features.demo_auth ? <form onSubmit={(event) => void enterDemo(event)}>
        <p className="badge">Локальный dev вход. Код задаётся при запуске backend и не сохраняется в браузере.</p>
        <label htmlFor="demo-identity">Учётная запись</label>
        <select id="demo-identity" value={identity} onChange={(event) => setIdentity(event.target.value as 'reviewer_a' | 'reviewer_b')}>
          <option value="">Выберите запись</option>
          <option value="reviewer_a">Проверяющий A</option><option value="reviewer_b">Проверяющий B</option>
        </select>
        <label htmlFor="demo-code">Локальный код</label>
        <input id="demo-code" type="password" autoComplete="off" value={accessCode} onChange={(event) => setAccessCode(event.target.value)} />
        <button type="submit" disabled={busy || !accessCode || !identity}>{busy ? 'Входим…' : 'Войти в dev'}</button>
      </form> : sessionExpired ? <p role="status">Сессия истекла. Закройте и переоткройте мини-приложение в MAX для свежих стартовых данных.</p> :
        initData ? <><p role="status">{busy ? 'Проверяем вход MAX на сервере…' : 'Вход MAX не завершён.'}</p>
          {error && !(error instanceof ApiRequestError && error.status === 401) &&
            <button type="button" disabled={busy} onClick={() => void enterMax()}>Повторить вход MAX</button>}</> :
        <p>Откройте приложение внутри MAX. Стартовые данные MAX здесь недоступны.</p>}
    <ErrorMessage error={error} />
  </section>;
}

function Assistant({ profile, catalog }: { profile: Profile; catalog: Catalog }) {
  const [params] = useSearchParams();
  const receiptId = params.get('receipt');
  const [question, setQuestion] = useState('Почему выросла сумма за воду?');
  const [topicId, setTopicId] = useState(params.get('topic') ?? '');
  const [clarified, setClarified] = useState<Partial<AnswerContext>>({});
  const [receipt, setReceipt] = useState<ReceiptView | null>(null);
  const [serviceCode, setServiceCode] = useState('');
  const [answer, setAnswer] = useState<AnswerView | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const pending = useRef<AbortController | null>(null);
  useEffect(() => {
    return () => pending.current?.abort();
  }, []);
  useEffect(() => { setTopicId(params.get('topic') ?? ''); }, [params]);
  useEffect(() => {
    let active = true; setReceipt(null); setServiceCode('');
    if (receiptId) api.receipt(receiptId).then((value) => { if (active) setReceipt(value); })
      .catch((cause) => { if (active) setError(cause); });
    return () => { active = false; };
  }, [receiptId]);
  async function ask(event?: React.FormEvent<HTMLFormElement>, extra: Partial<AnswerContext> = {}) {
    event?.preventDefault();
    if (!question.trim()) return;
    const context: AnswerContext = {
      territory_id: profile.territory_id, role: profile.role, topic_id: topicId || null,
      organization_id: null, service_code: serviceCode || null, document_kind: null,
      receipt_id: receipt?.status === 'confirmed' ? receipt.id : null,
      receipt_revision: receipt?.status === 'confirmed' ? receipt.revision : null, ...clarified, ...extra,
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
      {receiptId && <div className="notice-box"><p>Документ: {receipt ? `${receipt.bill_data.period ?? 'без периода'} · ревизия ${receipt.revision}` : 'загружаем…'}</p>{receipt && receipt.status !== 'confirmed' && <p className="review-warning">Для вопроса по документу сначала подтвердите его данные.</p>}{receipt?.dataset_kind === 'synthetic' && <p className="badge">Синтетический пример</p>}{receipt?.status === 'confirmed' && <><label htmlFor="answer-service">Услуга</label><select id="answer-service" value={serviceCode} onChange={(event) => setServiceCode(event.target.value)}><option value="">Без выбора услуги</option>{receipt.bill_data.services.map((line) => <option key={line.line_id} value={line.service_code}>{line.raw_name}</option>)}</select></>}</div>}
      <label htmlFor="answer-topic">Тема</label><select id="answer-topic" value={topicId} onChange={(event) => { setTopicId(event.target.value); setClarified({}); }}><option value="">Определить по вопросу</option>{catalog?.topics.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select>
      <label htmlFor="question">Ваш вопрос</label>
      <textarea id="question" value={question} onChange={(event) => setQuestion(event.target.value)} maxLength={2000} rows={3} />
      <button disabled={busy || !hasSessionToken() || (!!receiptId && receipt?.status !== 'confirmed')}>{busy ? 'Ищем ответ…' : 'Спросить'}</button>
    </form>
    {!hasSessionToken() && <p>Войдите на главной, чтобы задать общий вопрос.</p>}
    <ErrorMessage error={error} />
    {answer && <article aria-live="polite" className="answer">
      <p className="badge">{answer.dataset_kind === 'synthetic' ? 'Синтетический пример' : answer.dataset_kind}</p>
      <h3>{answer.status === 'unsupported' ? 'Пока нет проверенного ответа' : answer.status === 'needs_clarification' ? 'Нужно уточнение' : 'Ответ'}</h3>
      <p>{answer.text}</p>
      {answer.clarification && <div className="notice-box"><p>{answer.clarification.prompt}</p>{answer.clarification.options.map((option) => <button key={option.value} type="button" onClick={() => { const extra = { [answer.clarification!.field]: option.value }; setClarified((value) => ({ ...value, ...extra })); void ask(undefined, extra); }}>{option.label}</button>)}</div>}
      {answer.stale && <p className="review-warning">Ответ устарел: проверьте сведения перед действием.</p>}
      <p>Территория: {catalog.territories.find((item) => item.id === profile.territory_id)?.label ?? 'не выбрана'} · версия знаний {answer.knowledge_version}</p>
      {answer.sources.map((source) => <p key={source.id}>Источник: {source.title} · {source.territory_id ? catalog.territories.find((item) => item.id === source.territory_id)?.label ?? source.territory_id : 'общий'} · проверен {source.verified_at} · пересмотреть после {source.review_after}{source.is_synthetic && ' · учебный'}{source.url && <a href={source.url} target="_blank" rel="noopener noreferrer"> Открыть</a>}</p>)}
      <ActionList actions={answer.actions} />
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
    </> : <><p>{screen.text}</p><p className="notice">Этот экран ожидает реализацию следующего этапа.</p><p>Состояния для реализации: {screen.states}.</p></>}
  </section>;
}

export function App() {
  const [meta, setMeta] = useState<MetaResponse | null>(null);
  const [metaError, setMetaError] = useState<unknown>(null);
  const [authenticated, setAuthenticated] = useState(hasSessionToken());
  const [profile, setProfile] = useState<Profile | null>(null);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [sessionError, setSessionError] = useState<unknown>(null);
  const [sessionExpired, setSessionExpired] = useState(false);
  const [guestRenewed, setGuestRenewed] = useState(false);
  const [loadingSession, setLoadingSession] = useState(false);
  const [reloadMeta, setReloadMeta] = useState(0);
  const [reloadSession, setReloadSession] = useState(0);
  const location = useLocation();
  const navigate = useNavigate();
  useEffect(() => {
    const controller = new AbortController();
    setMetaError(null);
    api.meta(controller.signal).then(setMeta).catch((cause) => {
      if (!(cause instanceof DOMException && cause.name === 'AbortError')) setMetaError(cause);
    });
    return () => controller.abort();
  }, [reloadMeta]);
  useEffect(() => {
    const expired = () => { setAuthenticated(false); setProfile(null); setCatalog(null); setSessionExpired(true);
      setSessionError(new Error(PREVIEW_MODE ? 'Учебная сессия истекла. Открываем нового гостя.' : import.meta.env.DEV ? 'Сессия истекла. Войдите снова.' : 'Сессия истекла. Переоткройте мини-приложение в MAX.')); };
    window.addEventListener('zhkh:session-expired', expired);
    return () => window.removeEventListener('zhkh:session-expired', expired);
  }, []);
  useEffect(() => {
    if (!authenticated) return;
    const controller = new AbortController();
    setLoadingSession(true); setSessionError(null);
    Promise.all([api.me(controller.signal), api.catalog(controller.signal)])
      .then(([me, choices]) => { setProfile(me.profile); setCatalog(choices); })
      .catch((cause) => { if (!(cause instanceof DOMException && cause.name === 'AbortError')) setSessionError(cause); })
      .finally(() => setLoadingSession(false));
    return () => controller.abort();
  }, [authenticated, reloadSession]);
  const needsLogin = <section className="panel"><h2>Нужен вход</h2><p>{PREVIEW_MODE ? 'Подождите создания виртуального гостя.' : sessionExpired && !import.meta.env.DEV ? 'Переоткройте мини-приложение в MAX. После входа можно продолжить на этом экране.' : 'После входа можно продолжить на этом экране.'}</p></section>;
  const waiting = <section className="panel"><h2>Профиль</h2>{sessionError ? <>
    <p>Не удалось получить профиль и каталог.</p><button type="button" onClick={() => setReloadSession((value) => value + 1)}>Повторить</button>
  </> : <p role="status">Получаем данные первого запуска…</p>}</section>;
  return <div className="app">
    <a className="skip" href="#content">К содержимому</a>
    <header><h1>Помощник ЖКХ</h1><p>Первые вопросы о платёжке и следующий шаг</p></header>
    {PREVIEW_MODE && <aside className="preview-banner" role="note"><strong>Публичный учебный стенд · синтетические данные</strong><span>Не загружайте личные квитанции и персональные данные. Обращения отсюда никому не отправляются.</span></aside>}
    <nav aria-label="Основная навигация"><Link to="/">Главная</Link><Link to="/onboarding">Первый запуск</Link><Link to="/assistant">Помощник</Link><Link to="/upload">Платёжка</Link><Link to="/history">История</Link></nav>
    <main id="content" tabIndex={-1}>
      {metaError !== null && <><ErrorMessage error={metaError} /><button type="button" onClick={() => setReloadMeta((value) => value + 1)}>Повторить загрузку API</button></>}
      {sessionError !== null && <ErrorMessage error={sessionError} />}
      {guestRenewed && <p className="notice" role="status">Создан новый виртуальный гость: прежняя учебная история в этой вкладке недоступна.</p>}
      {!authenticated && <Entry meta={meta} sessionExpired={sessionExpired} onAuth={(value) => { setProfile(value); if (PREVIEW_MODE && sessionExpired) setGuestRenewed(true); setSessionExpired(false); setAuthenticated(true); }} />}
      {location.pathname === '/' && authenticated && meta && !canUpload(profile, meta) && <p className="notice">Перед загрузкой платёжки завершите <Link to="/onboarding">первый запуск</Link>.</p>}
      {loadingSession && waiting}
      <Routes>
        {screens.map(({ path }) => <Route key={path} path={path} element={<Page path={path} />} />)}
        <Route path="/onboarding" element={!authenticated ? needsLogin : meta && catalog && profile ? <Onboarding meta={meta} catalog={catalog} profile={profile} onSaved={setProfile} /> : waiting} />
        <Route path="/upload" element={!authenticated ? needsLogin : meta ? <Upload meta={meta} profile={profile} catalog={catalog} onQueued={(value) => navigate(`/processing?job=${encodeURIComponent(value.job_id)}`)} /> : waiting} />
        <Route path="/processing" element={!authenticated ? needsLogin : <Processing stub={!!meta?.features.engine_stub} />} />
        <Route path="/review" element={!authenticated ? needsLogin : <ReceiptReview />} />
        <Route path="/explanation" element={!authenticated ? needsLogin : <ReceiptExplanation />} />
        <Route path="/history" element={!authenticated ? needsLogin : <History />} />
        <Route path="/comparison" element={!authenticated ? needsLogin : <Comparison />} />
        <Route path="/draft" element={!authenticated ? needsLogin : <Draft catalog={catalog} />} />
        <Route path="/assistant" element={!authenticated ? needsLogin : profile && catalog ? <Assistant profile={profile} catalog={catalog} /> : waiting} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </main>
    <footer>{PREVIEW_MODE ? 'Учебная версия. Используйте только синтетические примеры.' : 'Интерфейс разработки. Распознавание и ответы проверяйте по доступным возможностям API.'}</footer>
  </div>;
}
