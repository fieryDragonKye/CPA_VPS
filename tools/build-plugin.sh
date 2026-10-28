#!/bin/sh
set -eu
cd "$(dirname "$0")/../plugin"
export CGO_ENABLED=1
export GOMAXPROCS="${GOMAXPROCS:-2}"
go vet -p 2 ./...
go test -p 2 -race ./...
mkdir -p dist
go build -p 2 -trimpath -ldflags='-s -w' -tags cshared -buildmode=c-shared -o dist/cpa-codex-candy-eval.so ./cmd/cpa-codex-candy-eval
file dist/cpa-codex-candy-eval.so
sha256sum dist/cpa-codex-candy-eval.so
