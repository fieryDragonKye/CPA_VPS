# Optional Codex transport diagnostics

This patch targets CLIProxyAPI **v8.0.47**, commit
`90c447d3a8727d115aa7552ec93ce023736ed492`.
It preserves the upstream license in `licenses/CPA-LICENSE`.

The patch and its regression tests trace proxy dial, TLS, negotiated protocol,
request write, response headers, first body read, and response completion. Each
attempt has an independent ID; only a validated UUID request ID is retained.
It records local source ports, stage timings and classified errors. It does not
record request/response headers, URLs, message bodies, account identifiers,
credentials or raw error strings. A separate deployment-specific observer can
correlate local ports with a proxy core; no observer, proxy config or live log is
included here.

## Build in a separate checkout

Use a compatible Linux/CGO toolchain, Go 1.26+ and the upstream lock files. For a
Bookworm runtime, use a compatible glibc build environment, such as Ubuntu 22.04.
The commands below do not install or deploy the resulting binary:

```sh
git clone --branch v8.0.47 --depth 1 https://github.com/router-for-me/CLIProxyAPI.git cpa-trace-build
cd cpa-trace-build
test "$(git rev-parse HEAD)" = "90c447d3a8727d115aa7552ec93ce023736ed492"
git apply --check /absolute/path/to/0001-metadata-trace.patch
git apply /absolute/path/to/0001-metadata-trace.patch
go test ./internal/logging
go test ./internal/runtime/executor/helps -run 'TestCodexTransportTrace|TestUtlsRoundTripUsesNegotiatedProtocol|TestChromeTLSHandshake'
go test -race ./internal/runtime/executor/helps -run TestCodexTransportTrace
CGO_ENABLED=1 go build -trimpath -o cli-proxy-api ./cmd/server
```

The archived sources were built with Go 1.26.10 for Linux amd64 in Ubuntu 22.04.
Other architectures require their own compatible build and validation.

Only requests to `chatgpt.com` using this uTLS transport are instrumented. This
is not a tracer for every provider or transport. Its additional per-attempt IDs,
file checks and synchronous log writes have a cost when enabled; it is a
diagnostic option, not a network or rate-limit fix.

## Explicit opt-in

The running patched process must have `CPA_CODEX_TRANSPORT_TRACE_FILE` set to an
operator-chosen sentinel path. The path must point to an existing regular file.
The file's contents are never read. Keep the sentinel and logs in a private
runtime directory outside Git, and remove the sentinel to stop enabling new
attempts. Existing attempts may finish emitting their records.

The normal `tools/prepare-assets.py` and Docker deployment still stage the
checksum-verified official binary. This patch does not alter those defaults,
install a service, enable tracing, or run model requests. Back up the binary and
configuration, check active requests, and follow the deployment guide before
choosing to replace an existing backend. Revert by restoring the prior binary;
do not restore an old usage database over newer records.
