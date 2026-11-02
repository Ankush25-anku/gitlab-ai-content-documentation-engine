# Environment setup

## 1. Supabase (database, vectors, auth)

1. Create a project at supabase.com. Note the project URL, anon key, and database password.
2. In **SQL Editor**, run in order:
   - `backend/database/migrations/001_init.sql` (tables + pgvector + HNSW index)
   - `backend/database/migrations/002_retrieval.sql` (similarity search function)
   - `backend/database/migrations/003_security.sql` (row-level security, append-only audit log)
3. **Project Settings > Database > Connection string**: copy the *session pooler* URI and change the scheme to
   `postgresql+psycopg://`. This is `DATABASE_URL`.
4. **Authentication > Users**: create one user per demo role (creator, reviewer, doc lead, publisher).
   After each user signs in once, set their role in the `profiles` table (new users start as `creator`):
   ```sql
   update profiles set role = 'tech_reviewer' where email = 'arjun@yourteam.dev';
   ```
5. JWT verification: new Supabase projects sign tokens with asymmetric keys, so leave `SUPABASE_JWT_SECRET` empty and
   set `SUPABASE_URL`; the backend reads the project's JWKS. Older projects can set the legacy JWT secret instead.

## 2. Gemini

Create an API key in Google AI Studio and set `GEMINI_API_KEY`. Check the current model names in the
[Gemini API docs](https://ai.google.dev/gemini-api/docs) and set `LLM_MODEL_DRAFT` / `LLM_MODEL_REVIEW`
(LiteLLM format: `gemini/<model-name>`). Set `EMBEDDING_PROVIDER=gemini`, keep `EMBEDDING_DIM=768`.

After switching embedding provider, re-ingest the knowledge base so all vectors come from the same model:
```bash
DATABASE_URL=... EMBEDDING_PROVIDER=gemini GEMINI_API_KEY=... python -m ai.retrieval.ingest --reset
```

## 3. GitLab sandbox for merge request export

1. Create a public project on gitlab.com, for example `your-team/gitlab-docs-sandbox`, with a `main` branch.
2. **Settings > Access tokens**: create a *project access token*, role Developer, scope `api`.
3. Set `GITLAB_PROJECT_ID` (numeric id or `your-team/gitlab-docs-sandbox`) and `GITLAB_TOKEN`.
   Never use a personal token for a real project here.

## 4. Variables by service

| Variable | Backend | Frontend | Secret |
|---|---|---|---|
| `APP_ENV=production` | yes | | |
| `AUTH_MODE=supabase` | yes | | |
| `DATABASE_URL` | yes | | yes |
| `SUPABASE_URL` | yes | as `NEXT_PUBLIC_SUPABASE_URL` | no |
| `SUPABASE_JWT_SECRET` (legacy only) | yes | | yes |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | | yes | public by design |
| `LLM_PROVIDER=crewai`, `GEMINI_API_KEY`, `LLM_MODEL_*` | yes | | key is secret |
| `EMBEDDING_PROVIDER=gemini` | yes | | |
| `GITLAB_PROJECT_ID`, `GITLAB_TOKEN` | yes | | token is secret |
| `ALLOWED_ORIGINS=https://<app>.vercel.app` | yes | | |
| `NEXT_PUBLIC_API_URL=https://<api>.onrender.com` | | yes | |

Only `NEXT_PUBLIC_*` values reach the browser. Model keys, database URLs and repository tokens stay on the backend.
