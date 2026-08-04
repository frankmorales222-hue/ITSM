# Security and healthcare-conscious operation

Northstar Desk is designed to minimize sensitive information, but software alone does not make an organization HIPAA compliant. Compliance also depends on approved hosting, access policies, workforce procedures, contracts, training, backups, incident response, risk assessments, and ongoing technical safeguards.

Implemented controls include Argon2id password hashes, password complexity and forced change, failed-login lockout, expiring server-side sessions, HttpOnly/SameSite cookies, optional Secure cookies, CSRF tokens, server-side role and record authorization, parameterized ORM access, restrictive browser headers, plain-text message rendering, input limits, masked secret handling, audit events, and generic error responses with correlation IDs. The interface warns on likely Social Security numbers, credentials, and medical language without claiming perfect detection.

Before production use:

1. Use PostgreSQL with a least-privilege database account.
2. Terminate TLS at IIS, a reverse proxy, or the application host; set `ITSM_COOKIE_SECURE=true`.
3. Generate a random 32+ byte `ITSM_SECRET_KEY` and protect `.env` with Windows ACLs.
4. Store mailbox secrets through Windows Credential Manager, never `.env`.
5. Configure encrypted, tested database backups and monitoring.
6. Replace seeded accounts, review every role, and define restricted-ticket membership.
7. Add outbound mail relay TLS and recipient controls before enabling external notification delivery.
8. Run vulnerability scanning, dependency review, penetration testing, and a formal risk assessment.

Known limitations: the first release has role-based restricted access rather than configurable per-ticket access lists; configuration catalogs use seeded defaults plus API/database administration; rate limiting is account-based and should be complemented by reverse-proxy IP throttling; SQLite is not appropriate for concurrent production workloads; notification email delivery is represented by durable in-app events until an SMTP relay is configured.

