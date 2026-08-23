# Security Policy

English | [简体中文](SECURITY.md)

## Supported Versions

| Branch / version | Support status |
| ----------- | -------- |
| Latest code on `master` | ✅ receives security fixes |
| Historical commits / tags | ❌ please upgrade |

## How to Report a Vulnerability

**Do not report security issues through public Issues, PRs, or Discussions.**

Preferred channel: GitHub private security advisory — on the repo page go to **Security → Advisories → New draft security advisory**, or visit <https://github.com/YEYUbaka/LocalRAG/security/advisories/new>

Please include where possible:

- Vulnerability type and impact scope;
- Reproduction steps or a minimal PoC;
- Triggering preconditions (deployment mode, relevant configuration).

Maintainers acknowledge reports within **48 hours** and provide an initial assessment within about **7 days**. Disclosure timelines are agreed together; by default details are published only after a fix ships.

## Priority Areas

- **The local-first boundary**: any path that leaks original documents, vector indexes, or API keys to unintended third parties;
- Auth & sessions: JWT issuance/validation logic, default credentials, session expiry policy;
- Document parsing: parser flaws triggered by maliciously crafted PDF / Office / HTML files;
- Web security: SQL injection, path traversal (upload/export/preview endpoints), XSS (preview rendering), CORS configuration;
- Deployment surface: docker-compose default passwords, nginx proxy config, weak defaults in `.env.example`;
- Known high-severity CVEs in the dependency chain.

## Existing Security Design

- Secrets live only in the local `.env` (never committed; CI includes a secret-scanning job);
- Original documents and vector indexes stay local; the cloud LLM only ever receives sanitized retrieved snippets.

## Known Upstream Dependency Vulnerability (tracked)

- **GHSA-f4j7-r4q5-qw2c** (critical): pre-authentication code injection in chromadb, affecting 1.0.0 – 1.5.9. As of 2026-08-23 upstream has not released a patched version.
  - **Exposure analysis**: the flaw lives in chromadb’s HTTP server request-handling path. LocalRAG uses chromadb **embedded mode only** (`PersistentClient` in `app/core/vectorstore.py`, in-process, no network listener); neither source deployments nor docker-compose start a chroma server, so the default configuration has no attack surface.
  - **Policy**: upgrade immediately once upstream publishes a fix and remove this record; until then, contributors must **not** introduce changes that run chromadb in server mode or expose its ports.

Thank you for disclosing responsibly — your contribution makes every LocalRAG user safer.
