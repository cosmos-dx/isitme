# web-api

The isitme **Web API / BFF** (FastAPI, port **5050**).

It provides Google OAuth login, signed session cookies for the frontend on
`http://localhost:4000`, API-key management (the keys the browser extension /
MCP server use to authenticate to the brain), an MCP-config generator, and a
read-only proxy over the Core Brain (`http://127.0.0.1:8077`) for the dashboard.

See `packages/web/README.md` for run instructions.
