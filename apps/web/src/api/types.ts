// Public DTOs are generated from the accepted contracts/http/openapi.yaml.
// Regenerate with `npm run generate:types` after an accepted contract change.
import type { components } from './openapi.generated';

type Schema = components['schemas'];
export type Id = Schema['Id'];
export type Timestamp = Schema['Timestamp'];
export type Money = Schema['Money'];
export type ApiErrorBody = Schema['ErrorEnvelope'];
export type Profile = Schema['Profile'];
export type AuthResponse = Schema['AuthResponse'];
export type MetaResponse = Schema['Meta'];
export type ReceiptRef = Schema['ReceiptRef'];
export type SourceRef = Schema['SourceRef'];
export type NextAction = Schema['NextAction'];
export type AnswerContext = Schema['AnswerContext'];
export type AnswerView = Schema['AnswerView'];
export type Issue = Schema['Issue.schema'];
// openapi-typescript includes the JSON Schema keyword `$defs` as an instance field
// for B's external BillData schema; JSON payloads intentionally omit it.
export type BillData = Omit<Schema['BillData.schema'], '$defs'>;
export type ReceiptView = Omit<Schema['ReceiptView'], 'bill_data'> & { bill_data: BillData };

export interface UnexpectedErrorBody {
  error: { code: 'UNEXPECTED_RESPONSE'; message: string; retryable: boolean; fields: []; details: {} };
  request_id: string;
}
