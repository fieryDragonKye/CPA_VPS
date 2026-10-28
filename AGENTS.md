# Repository guidance

- This is a source-only distribution. Never add live config, keys, OAuth files, subscriptions, databases, logs, screenshots of private data or toolchain caches.
- Keep web, plugin, insights and deployment changes scoped; inspect each component's instructions and preserve upstream license notices.
- Do not install dependencies, restart services, deploy to a VPS, run paid model tests, publish releases or push to GitHub merely because a local check passes. These need authorization in the current task.
- Keep the four skills manual-only; do not load or install them through this AGENTS.md.
- Web uses Bun and its existing lockfile. Insights uses only the Python standard library. No large UI or test dependencies without evidence.
- Run focused checks and report actual results. Mock/unit/headless checks are not visible-browser or real-service acceptance.
- Runtime resources belong outside the repository. Backups are private; never overwrite existing nonempty instances.
