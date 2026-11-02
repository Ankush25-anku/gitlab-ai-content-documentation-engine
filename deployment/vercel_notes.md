# Frontend deployment (Vercel)

1. **Add New > Project**, import the repository.
2. **Root Directory**: `frontend`. Framework preset: Next.js (auto-detected).
3. Environment variables:
   - `NEXT_PUBLIC_API_URL` = your backend URL, for example `https://content-engine-api.onrender.com`
   - `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY` only when the backend uses `AUTH_MODE=supabase`.
     Without them the login page shows the demo users (backend must use `AUTH_MODE=dev`).
4. Deploy, then add the Vercel URL to the backend's `ALLOWED_ORIGINS` and redeploy the backend.
5. Put the Vercel URL at the top of the README.

Netlify works the same way: base directory `frontend`, build command `npm run build`, and the Next.js runtime plugin.
