# Staging deployment

Use the repository-root `Dockerfile.admin` for a separate Render service on the development branch. Do not use the bot's production `render.yaml` and do not run `bot.py` in staging.

See `docs/gemini-staging-readiness.md` at repository root for configuration, readiness and rollback. Never paste service-role keys into browser code or commit environment files.
