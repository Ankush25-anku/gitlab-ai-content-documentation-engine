# Backend deployment (Render or Railway)

The backend is a Docker image built from the repository root (`Dockerfile`).

## Render

1. **New > Blueprint**, select the repository; Render reads `render.yaml`.
2. Fill the variables marked `sync: false` in the dashboard (see `environment_setup.md`).
3. Deploy. Check `https://<service>.onrender.com/health` returns `{"status": "ok", "llm_provider": "crewai", "auth_mode": "supabase"}`.
4. Seed the knowledge base once (from your machine, pointing at Supabase):
   `DATABASE_URL=... EMBEDDING_PROVIDER=gemini GEMINI_API_KEY=... python -m ai.retrieval.ingest --reset`
   (On first start the API also ingests automatically if `kb_chunks` is empty.)

Free instances sleep when idle and take up to a minute to wake. Before an evaluation or recording, open `/health`
first, or use a paid instance for submission week.

## Railway

New project > Deploy from GitHub repo. Railway detects the `Dockerfile`. Add the same variables; Railway sets `PORT`.

## Production safety checks

- The app refuses to start when `APP_ENV=production` and `AUTH_MODE=dev`.
- `simulate_failure` on `/api/agent-workflow/run` is rejected in production.
- CORS allows only `ALLOWED_ORIGINS`.

## A demo deployment without Supabase Auth

If you want evaluators to click straight in with demo users, deploy a second backend with `APP_ENV=staging`,
`AUTH_MODE=dev` and the same database. Label it clearly as a demo environment in the README.
