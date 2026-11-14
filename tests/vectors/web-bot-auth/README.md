# Web Bot Auth and HTTP message signature test vectors

Used by `tests/test_ed25519.py`, `tests/test_sfv.py` and `tests/test_webbotauth.py` (S3.2). All keys here are the
published test keys of RFC 9421 Appendix B.1; they must never be trusted outside tests (draft-ietf-webbotauth-httpsig-protocol-01
section 6.8), and Agent Cake's default settings reject the Ed25519 one (`agentcake/data/webbotauth.json`).

## From cloudflare/web-bot-auth (copied unchanged)

Repository https://github.com/cloudflare/web-bot-auth, commit `01c0d10a5f00d4e77cc5677576a7a2b6e4954d50`
("Release v0.8.0", 2026-11-10), folder `packages/web-bot-auth/test/test_data/`. Licence: Apache License 2.0, full
text in `LICENSE-cloudflare-web-bot-auth.txt` (the repository has no NOTICE file).

| File | SHA-256 |
|---|---|
| `web_bot_auth_architecture_v1.json` | `12ed35aaf50368d9cf6d3c704b8942e6603b1ef2bbd119c3040868b87e596ef4` |
| `web_bot_auth_architecture_v2.json` | `d0c8dbb7631dcc22639d12318af2b1ac0a339e4fa5aa4ef6df67ca45b0094576` |
| `web_bot_auth_directory_response_v1.json` | `ab2226c895940f0d169433ea0485ca7938e2dd2b89090945088b931031a7a1de` |
| `web_bot_auth_signature_agent_v2.json` | `5efff4fa640956ad5ef8664f34c6dbea82495c1e14ab129e7496529085753cbb` |

The two `architecture` files each hold two RSA-PSS and two Ed25519 signatures of `GET https://example.com/path/to/resource`;
Agent Cake verifies Ed25519 only, so the RSA-PSS ones are expected to come out as declared (algorithm not supported).

## Transcribed from IETF documents

- `draft-ietf-webbotauth-httpsig-protocol-01.json`: Appendix E.2.1, E.2.2 and E.2.3 of
  https://www.ietf.org/archive/id/draft-ietf-webbotauth-httpsig-protocol-01.txt (29 October 2026).
- `rfc9421.json`: RFC 9421 Appendix B.1.4 (public part of test-key-ed25519), B.2 (test-request) and B.2.6,
  https://www.rfc-editor.org/rfc/rfc9421.txt.

The RFC 8792 backslash line wrapping of the documents was undone by script; nothing else was changed. Both documents
are IETF-stream documents whose code components carry this licence (IETF Trust Legal Provisions, section 4.e):

> Copyright (c) 2024, 2026 IETF Trust and the persons identified as authors of the code. All rights reserved.
>
> Redistribution and use in source and binary forms, with or without modification, is permitted pursuant to, and
> subject to the license terms contained in, the Revised BSD License set forth in Section 4.c of the IETF Trust's
> Legal Provisions Relating to IETF Documents (https://trustee.ietf.org/license-info).

The RFC 8032 Ed25519 vectors used by `tests/test_ed25519.py` are written in that file itself (RFC 8032 section 7.1).
