import { useState, type FormEvent } from 'react';
import { api } from '../api/client';
import type { Catalog, MetaResponse, Profile } from '../api/types';
import { ErrorMessage } from './errors';

export function canUpload(profile: Profile | null, meta: MetaResponse | null): boolean {
  return !!profile?.onboarding_completed && !!profile.territory_id &&
    !!meta && profile.privacy_notice_version === meta.privacy_notice.version &&
    !!profile.privacy_acknowledged_at;
}

export function Onboarding({ meta, catalog, profile, onSaved }: {
  meta: MetaResponse; catalog: Catalog; profile: Profile; onSaved: (value: Profile) => void;
}) {
  const [role, setRole] = useState<Profile['role']>(profile.role);
  const [territoryId, setTerritoryId] = useState(profile.territory_id ?? '');
  const [accepted, setAccepted] = useState(canUpload(profile, meta));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [saved, setSaved] = useState(false);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!territoryId || !accepted) return;
    setBusy(true); setError(null); setSaved(false);
    try {
      const updated = await api.updateProfile({ role, territory_id: territoryId,
        privacy_notice_version: meta.privacy_notice.version, privacy_acknowledged: true });
      onSaved(updated); setSaved(true);
    } catch (cause) { setError(cause); }
    finally { setBusy(false); }
  }

  return <section className="panel">
    <h2>Первый запуск</h2>
    <p>Укажите роль и территорию, чтобы получить подходящие пояснения. Роль указывается вами и не подтверждает право собственности.</p>
    <form onSubmit={(event) => void save(event)}>
      <label htmlFor="role">Ваша роль</label>
      <select id="role" value={role} onChange={(event) => { setRole(event.target.value as Profile['role']); setSaved(false); }}>
        <option value="owner">Собственник</option><option value="tenant">Арендатор</option><option value="other">Другое</option>
      </select>
      <label htmlFor="territory">Территория</label>
      <select id="territory" value={territoryId} onChange={(event) => { setTerritoryId(event.target.value); setSaved(false); }}>
        <option value="">Выберите территорию</option>
        {catalog.territories.map((territory) => <option key={territory.id} value={territory.id}>{territory.label}</option>)}
      </select>
      {catalog.territories.length === 0 && <p className="notice">Территории пока не доступны. Попробуйте обновить данные позже.</p>}
      <div className="notice-box">
        <h3>Обработка документов</h3>
        <p>{meta.privacy_notice.text}</p>
        <p>Версия уведомления: {meta.privacy_notice.version}</p>
        <label className="check"><input type="checkbox" checked={accepted} onChange={(event) => { setAccepted(event.target.checked); setSaved(false); }} /> Я прочитал(а) уведомление и согласен(на) с обработкой загруженного документа</label>
      </div>
      <button type="submit" disabled={busy || !territoryId || !accepted}>{busy ? 'Сохраняем…' : 'Сохранить'}</button>
    </form>
    {saved && <p role="status">Профиль сохранён. Теперь можно загрузить платёжку.</p>}
    <ErrorMessage error={error} />
  </section>;
}
