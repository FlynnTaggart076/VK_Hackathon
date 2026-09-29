import { useEffect, useState } from 'react';
import { Link, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import type { ReactNode } from 'react';
import { api, ApiRequestError, hasSessionToken, setSessionToken } from '../api/client';
import { PREVIEW_MODE } from '../api/appConfig';
import { previewAuth } from '../api/previewAuth';
import { maxAuth, maxInitData } from '../api/maxAuth';
import type { Catalog, MetaResponse, Profile } from '../api/types';
import { Onboarding, canUpload } from './Onboarding';
import { Processing, Upload } from './Upload';
import { ReceiptReview } from './ReceiptReview';
import { ReceiptExplanation } from './ReceiptExplanation';
import { History } from './History';
import { Comparison } from './Comparison';
import { CityComparison } from './CityComparison';
import { Draft } from './Draft';
import { Assistant } from './Assistant';
import { ErrorMessage } from './errors';

const mockEnabled = import.meta.env.DEV && !PREVIEW_MODE && import.meta.env.VITE_ENABLE_MOCK === 'true';

const icons: Record<string, ReactNode> = {
  home: <path d="M3 11.5 12 4l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z" />,
  chat: <path d="M4 5h16v11H9l-5 4z" />,
  receipt: <><path d="M6 3h12v18l-3-2-3 2-3-2-3 2z" /><path d="M9 8h6M9 12h6" /></>,
  history: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
};
const tabs = [
  { to: '/', label: 'Главная', icon: 'home', paths: ['/'] },
  { to: '/assistant', label: 'Помощник', icon: 'chat', paths: ['/assistant', '/draft'] },
  { to: '/upload', label: 'Платёжка', icon: 'receipt', paths: ['/upload', '/processing', '/review', '/explanation'] },
  { to: '/history', label: 'История', icon: 'history', paths: ['/history', '/comparison', '/city-comparison'] },
];

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
    {import.meta.env.DEV && meta && <p className="notice">Версия интерфейса обмена {meta.api_version} · база знаний {meta.knowledge_version ?? 'ещё не подключена'}</p>}
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

function Home() {
  return <section className="panel">
    <h2>Главная</h2>
    <p>Разберите платёжку по шагам или задайте вопрос о ЖКХ. Ничего никуда не отправляется.</p>
    {mockEnabled && <p className="badge">Учебный режим · синтетические данные</p>}
    <div className="actions"><Link className="btn" to="/upload">Разобрать платёжку</Link><Link to="/assistant">Задать вопрос</Link></div>
    <h3>Частые вопросы</h3>
    <div className="actions">
      <Link to="/assistant?topic=supplier_contacts">Контакты поставщика</Link>
      <Link to="/assistant?topic=management_contacts">Контакты УК</Link>
      <Link to="/assistant?topic=meter_readings">Передать показания</Link>
      <Link to="/assistant?topic=service_issue">Проблема с услугой</Link>
    </div>
  </section>;
}

function TabBar() {
  const { pathname } = useLocation();
  return <nav className="tabbar" aria-label="Основная навигация"><div className="tabbar-inner">
    {tabs.map((tab) => {
      const active = tab.paths.includes(pathname);
      return <Link key={tab.to} to={tab.to} aria-current={active ? 'page' : undefined}>
        <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">{icons[tab.icon]}</svg>{tab.label}
      </Link>;
    })}
  </div></nav>;
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
  const navigate = useNavigate();
  const location = useLocation();
  useEffect(() => { window.WebApp?.ready?.(); }, []);
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
    <header className="app-header"><h1>Помощник ЖКХ</h1><p>Разберём платёжку по шагам</p></header>
    {PREVIEW_MODE && <aside className="preview-banner" role="note"><strong>Публичный учебный стенд · синтетические данные</strong><span>Не загружайте личные квитанции и персональные данные. Обращения отсюда никому не отправляются.</span></aside>}
    <main id="content" tabIndex={-1}>
      {metaError !== null && <><ErrorMessage error={metaError} /><button type="button" onClick={() => setReloadMeta((value) => value + 1)}>Повторить загрузку данных</button></>}
      {sessionError !== null && <ErrorMessage error={sessionError} />}
      {guestRenewed && <p className="notice" role="status">Создан новый виртуальный гость: прежняя учебная история в этой вкладке недоступна.</p>}
      {!authenticated && <Entry meta={meta} sessionExpired={sessionExpired} onAuth={(value) => { setProfile(value); if (PREVIEW_MODE && sessionExpired) setGuestRenewed(true); setSessionExpired(false); setAuthenticated(true); }} />}
      {authenticated && !!meta && !!profile && !canUpload(profile, meta) && location.pathname !== '/onboarding' && <div className="notice-box">
        <p><strong>Чтобы загружать платёжки,</strong> укажите роль и территорию и подтвердите уведомление.</p>
        <div className="actions"><Link className="btn" to="/onboarding">Первый запуск</Link></div>
      </div>}
      {loadingSession && waiting}
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/onboarding" element={!authenticated ? needsLogin : meta && catalog && profile ? <Onboarding meta={meta} catalog={catalog} profile={profile} onSaved={setProfile} /> : waiting} />
        <Route path="/upload" element={!authenticated ? needsLogin : meta ? <Upload meta={meta} profile={profile} catalog={catalog} onQueued={(value) => navigate(`/processing?job=${encodeURIComponent(value.job_id)}`)} /> : waiting} />
        <Route path="/processing" element={!authenticated ? needsLogin : <Processing stub={!!meta?.features.engine_stub} />} />
        <Route path="/review" element={!authenticated ? needsLogin : <ReceiptReview />} />
        <Route path="/explanation" element={!authenticated ? needsLogin : <ReceiptExplanation />} />
        <Route path="/history" element={!authenticated ? needsLogin : profile ? <History profile={profile} onConsentChanged={(enabled) => setProfile((current) => current ? { ...current, aggregate_opt_in: enabled } : current)} /> : waiting} />
        <Route path="/comparison" element={!authenticated ? needsLogin : <Comparison />} />
        <Route path="/city-comparison" element={!authenticated ? needsLogin : <CityComparison />} />
        <Route path="/draft" element={!authenticated ? needsLogin : <Draft catalog={catalog} />} />
        <Route path="/assistant" element={!authenticated ? needsLogin : <Assistant />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </main>
    <footer>{PREVIEW_MODE ? 'Учебная версия. Используйте только синтетические примеры.' : 'Цифры из квитанции проверяйте по оригиналу. Приложение не заменяет консультацию специалиста.'}
      {authenticated && <> <Link to="/onboarding">Изменить роль и территорию</Link></>}</footer>
    <TabBar />
  </div>;
}
