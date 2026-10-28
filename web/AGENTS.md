# Management UI guidance

React19/TypeScript/Vite, v8 Management API under /v8/management. Plugin resource/custom extension paths are exceptions; preserve backend-declared paths. Keep hash routing and single-file management.html deployment.

Use Bun1.3.14 and bun.lock. Run bun run verify for code changes. Tests are Bun/unit/server-render/contract checks, not a browser DOM harness; report real browser verification separately.

Reuse API client auth/error guards, config cache/invalidation and existing components; preserve session isolation, reduced-motion/transparency, mobile width constraints and the same-origin statistics path. Do not reintroduce navigation cross-fade.

Keep feature changes scoped, translated strings in all supported locale files, keys entered at runtime, and no real data in fixtures. Upstream API contracts must be checked against the pinned CPA version; the backend source is not vendored in this repository.

Do not run deployments or replace a runtime management.html just because build passes. Root AGENTS and current user authorization govern external operations.
