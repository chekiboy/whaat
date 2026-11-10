# whaat ui

The web UI: React 19, Vite, TanStack Router and Query, Tailwind and shadcn/ui, with a typed API client generated from `../openapi.json`. Use this page to work on the UI.

```
pnpm install
pnpm build        # type-check and build into dist/, which the server serves under /ui
pnpm dev          # http://localhost:5173, /api proxied to the server (WHAAT_SERVER, default http://127.0.0.1:1111)
pnpm api          # regenerate src/client after the server's openapi.json changed
pnpm check        # Biome lint and format
pnpm typecheck
pnpm test         # Vitest
pnpm e2e          # Playwright; starts the whaat server and the dev server
```

- **The token.** A built UI holds no token: the server writes its admin token into the `index.html` it serves, so one build works behind any instance. The dev server fills it in itself, from `WHAAT_TOKEN`, else the `token` file in `WHAAT_STATE_DIR` (default `~/Library/Application Support/whaat`).
- **Routes are files** in `src/routes/`; after adding one, run `pnpm build` once so `src/routeTree.gen.ts` knows it before `pnpm typecheck`.
- **Two languages.** Every string the UI shows lives in `src/i18n/en.ts` and `src/i18n/hu.ts`; a key missing from either is a type error. Memories, journals and reports are shown as they were written.
- **TypeScript stays on 6.x**: the client generator needs the TypeScript compiler API, which the 7.x native compiler does not have.
