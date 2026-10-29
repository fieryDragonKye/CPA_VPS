# FreeTier 2API private presentation fork

- Baseline: upstream v0.1.21, commit 9283810ec62f5b893824b2a6f991b7f5d9435550. Preserve its MIT license and notices.
- Keep provider, authentication, account isolation and scheduler logic scoped. The personal customization is in internal/admin/console.html.
- Build with sh tools/build-freetier-plugin.sh from the repository root, using Linux/WSL Go 1.24.13 and a compatible C compiler.
- Preserve upstream unit/integration/architecture tests. Do not add personal preview fixtures, browser scripts, traces, screenshots, binaries or deployment credentials here.
- Real OAuth, model requests, deployment, service restarts and Git publishing require task authorization. Never run live-tag provider tests by default.
- Plugin settings must reach the plugin as block YAML; its parser does not correctly consume flow-style JSON-as-YAML configuration.
