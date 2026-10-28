# Private plugin fork

Preserve the upstream C ABI, test algorithms, credential handling and history schema unless explicitly changing them.
Run Node scripts/test-ui.cjs for UI, go vet ./..., go test -race ./... and a compatible CGO build before release.
The root tools/build-plugin.sh builds only; it never uploads, restarts CPA or runs paid tests.
Deploy only with explicit task authorization. Back up the original library, config and state, match file/pluginVersion/store version pins, check idle requests, and validate loaded status.
Use the root deployment guide, not the original author's hard-coded private deployment layout. Never overwrite a live library in place.
