# WfGg role/security patch 0.3.0 — live schema aligned

Security model:
- Last War rank stays independent: R1-R5.
- R4 offices: WARLORD, RECRUITER, MUSE, BUTLER.
- WfGg system role: OWNER, exactly one protected account.
- Bootstrap creates R4 + OWNER, never a fake R5.
- D1 enforces one R5 per alliance and one holder per R4 office per alliance.
- R5 transfer uses POST /api/admin/leadership/transfer and requires the actor's current 6-digit code.
- Transfer permission: OWNER, current R5, or R4 BUTLER.
- Generic member editing cannot assign/demote R5.
- OWNER cannot be assigned through the application API and cannot be disabled by another user.

Live D1 note (2026-08-21): migration 0002 was applied manually through Cloudflare D1 Explorer before deployment. Do not execute the full 0002 file again on this already-migrated live database because SQLite would reject the duplicate officer_title column. The file is retained to reconstruct a fresh database from 0001 + 0002.

Deployment order:
1. Live D1 0002 migration (already done manually).
2. Deploy worker/src/index.js.
3. Confirm /api/health reports 0.3.0.
4. Bootstrap the first account as R4 + OWNER.
5. Create the real R5 initially as R4, then use the secure leadership-transfer endpoint.
6. Remove BOOTSTRAP_SECRET after successful bootstrap.
