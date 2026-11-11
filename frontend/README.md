# Berry Store Gemini dashboard

Imported from the user-supplied original Gemini ZIP on 2026-11-11. Original React components, assets and styling retained. The in-memory Express `server.ts` prototype is intentionally excluded.

Use Node 24: `npm ci`, `npm run lint`, `npm test`, `npm run build`.
The separate Python host (`admin_app.py`) serves `frontend/dist` and same-origin authenticated APIs. See `docs/gemini-staging-readiness.md` at repository root for verified status and limitations. No secrets or Supabase clients belong in this frontend.
