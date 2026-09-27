# E4 C follow-up: Moscow and Moscow Oblast source audit

- Role: housing_engine/knowledge per §18.4. Base/accepted technical candidate: `01a271a506db1e65aedd68efc7101c761827d89a`. Work in a separate `agent-c/e4b` checkout; current stage remains E4.
- Produce `docs/territory-source-matrix.md`: for all 15 topics and both selected regions, identify which generic steps have an official primary source and which need a specific house, УК or provider. Include URL, publication/review date, applicability and exact unsupported boundary. Do not infer a provider, tariff, deadline, contact or recipient from the city alone.
- Update `knowledge/**` only for an official, currently verified, generally applicable claim; retain `pilot_territory_id=null` and conservative `unsupported` when evidence is absent. No real receipt/photo accuracy claim; no changes to A/B runtime.
- Verify `verify_contract.py`, engine unit tests, source allowlist and both frozen FAQ/OCR gold evaluations when knowledge changes. Push source/docs SHA and separate report SHA with evidence and remaining missing pilot data. Do not start E5.
