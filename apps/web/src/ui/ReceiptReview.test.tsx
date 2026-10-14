// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { readFileSync } from 'node:fs';
import { api, ApiRequestError } from '../api/client';
import type { ReceiptView } from '../api/types';
import { ReceiptReview } from './ReceiptReview';
import { Processing } from './Upload';

const fixture = JSON.parse(readFileSync('../../contracts/http/examples/receipt-confirmed.json', 'utf8')) as ReceiptView;
function failed(): ReceiptView {
  return { ...structuredClone(fixture), status: 'failed', revision: 1, extraction_outcome: null,
    confirmed_at: null, issues: [], field_evidence: [], document: { ...fixture.document, available: false } };
}
function mount(entry = `/review?id=${fixture.id}`) {
  render(<MemoryRouter initialEntries={[entry]}><Routes>
    <Route path="/review" element={<ReceiptReview />} />
    <Route path="/processing" element={<Processing stub={false} />} />
    <Route path="/explanation" element={<p>Объяснение открыто</p>} />
  </Routes></MemoryRouter>);
}
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

it('recovers a failed receipt through manual API and confirms the new server revision', async () => {
  const original = failed();
  original.bill_data.period = null; original.bill_data.services = [];
  const manual = { ...failed(), id: '10000000-0000-4000-8000-000000000009', status: 'needs_review' as const,
    extraction_outcome: 'manual_required' as const, issues: [{ code: 'TOTAL_DUE_UNKNOWN', severity: 'warning' as const, message: 'Итого неизвестно.', path: '/document_total_due' }], bill_data: structuredClone(fixture.bill_data) };
  vi.spyOn(api, 'receipt').mockImplementation(async (id) => id === manual.id ? manual : original);
  const create = vi.spyOn(api, 'createManualReceipt').mockResolvedValue(manual);
  const edit = vi.spyOn(api, 'editReceipt');
  const confirm = vi.spyOn(api, 'confirmReceipt').mockResolvedValue({ ...manual, revision: 2, status: 'confirmed' });
  mount();
  fireEvent.click(await screen.findByRole('button', { name: 'Заполнить вручную' }));
  const save = screen.getByRole('button', { name: 'Сохранить ручной ввод' });
  expect((save as HTMLButtonElement).disabled).toBe(true);
  fireEvent.change(screen.getByLabelText('Период (ГГГГ-ММ)'), { target: { value: '2026-09' } });
  fireEvent.click(screen.getByRole('button', { name: 'Добавить строку' }));
  fireEvent.change(screen.getByLabelText('Название в квитанции'), { target: { value: 'Вода' } });
  fireEvent.change(screen.getByLabelText('Сумма, ₽'), { target: { value: '200,5' } });
  fireEvent.click(save);
  await waitFor(() => expect(create).toHaveBeenCalledOnce());
  expect(create.mock.calls[0][0].bill_data.services[0].charge_amount).toBe('200.50');
  expect(edit).not.toHaveBeenCalled();
  const confirmation = await screen.findByRole('button', { name: 'Подтвердить проверенные данные' });
  expect((confirmation as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(screen.getByRole('checkbox'));
  fireEvent.click(confirmation);
  await screen.findByText('Объяснение открыто');
  expect(confirm.mock.calls[0].slice(0, 2)).toEqual([manual.id, { expected_revision: 1, acknowledged_warning_codes: ['TOTAL_DUE_UNKNOWN'] }]);
});

it('preserves manual data and reuses the idempotency key after network failure; shows server validation', async () => {
  vi.spyOn(api, 'receipt').mockResolvedValue(failed());
  const create = vi.spyOn(api, 'createManualReceipt')
    .mockRejectedValueOnce(new TypeError('Network failed'))
    .mockRejectedValueOnce(new ApiRequestError(422, { request_id: 'test', error: {
      code: 'VALIDATION_FAILED', message: 'Проверьте сумму.', retryable: false,
      fields: [{ path: '/period', message: 'Неверный период.' }], details: {},
    } }));
  mount(`/review?id=${fixture.id}&manual=1`);
  fireEvent.click(await screen.findByRole('button', { name: 'Сохранить ручной ввод' }));
  await screen.findByText('Нет соединения с сервером. Проверьте сеть и повторите попытку.');
  fireEvent.click(screen.getByRole('button', { name: 'Сохранить ручной ввод' }));
  await screen.findByText('Неверный период.');
  expect(create.mock.calls[0]).toEqual(create.mock.calls[1]);
  expect((screen.getByLabelText('Период (ГГГГ-ММ)') as HTMLInputElement).value).toBe('2026-08');
  expect(screen.queryByRole('button', { name: 'Подтвердить проверенные данные' })).toBeNull();
});

it('offers direct manual entry from a failed processing job even when retry fails', async () => {
  vi.spyOn(api, 'job').mockResolvedValue({ id: 'job', kind: 'receipt_ocr', state: 'failed', receipt_id: fixture.id, stage: null,
    error: { code: 'OCR_TIMEOUT', message: 'Ошибка распознавания.', retryable: true }, updated_at: fixture.updated_at });
  vi.spyOn(api, 'receipt').mockResolvedValue(failed());
  vi.spyOn(api, 'retryReceipt').mockRejectedValue(new TypeError('Network failed'));
  mount('/processing?job=job');
  fireEvent.click(await screen.findByRole('button', { name: 'Повторить обработку' }));
  await screen.findByText('Не удалось запустить повторную обработку. Попробуйте ещё раз.');
  fireEvent.click(screen.getByRole('link', { name: 'Заполнить вручную' }));
  await screen.findByRole('button', { name: 'Сохранить ручной ввод' });
});
