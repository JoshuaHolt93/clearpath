# ClearPath Web

Next.js 15 App Router web client. Phase 4 is being ported one Flask/Jinja route at a time.

Set `CLEARPATH_API_URL` to the FastAPI origin; local development defaults to `http://127.0.0.1:8000`.

```powershell
pnpm --filter @clearpath/web dev
```

The login page is available at `http://127.0.0.1:3000/login`.
