# MAX API CA trust in the backend image

`russian-trusted-root-ca.crt` is the public PEM root certificate of the Russian
Ministry of Digital Development. It is not a private key or application secret.
The backend Dockerfile pins the exact PEM file SHA-256 before adding it to the
image CA store; normal TLS certificate and hostname validation remain enabled.

- Source downloaded on 2026-09-27: [Ministry certificate distribution
  point](http://nuc-cdp.digital.gov.ru/cdp/rootca_ssl_rsa2022.crt).
- Official service requirement: [MAX API changelog](https://dev.max.ru/docs-api/changelog-api)
  says to call `platform-api2.max.ru` and trust the Ministry certificate.
- PEM file SHA-256:
  `936A43FEA6E8E525BCC0F81ACD9C3D21B4FC4B9B68ACEA7906D698005AFC6504`.
- Parsed certificate DER SHA-256:
  `D26D2D0231B7C39F92CC738512BA54103519E4405D68B5BD703E9788CA8ECF31`.
- Subject and issuer: `Russian Trusted Root CA`, Ministry of Digital
  Development and Communications, RU. Expires 2032-02-27 21:04:15 UTC.

The DER fingerprint matched the root of the trusted Windows TLS chain observed
for `platform-api2.max.ru` on 2026-09-27. Its server-sent chain contained the
MAX leaf and `Russian Trusted Sub CA`. OpenSSL without this CA reported verify
code 20; with this CA and hostname verification it reported code 0. An HTTP
distribution point alone would not authenticate a trust anchor, so the chain
fingerprint comparison is a required provenance check.

Before replacing this file, compare the new certificate fingerprint to the
official Ministry publication and live MAX chain, update the pinned PEM hash,
and repeat the worker container HTTPS check. Do not disable TLS verification.
