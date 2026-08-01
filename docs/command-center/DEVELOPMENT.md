# Development

```bash
# API only
CC_OPEN_BROWSER=0 python3 -m scripts.command_center

# UI
cd apps/command-center
npm install
npm run dev   # 127.0.0.1:5173 proxies /api → 8765
```

## Frontend stack

React 18, TypeScript, Vite, React Router, TanStack Query, Vitest, Playwright.

## Backend stack

Python 3.12, FastAPI, Pydantic, Uvicorn, SQLite.
