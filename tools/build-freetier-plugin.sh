#!/bin/sh
set -eu
cd "$(dirname "$0")/../plugin-freetier"
export CGO_ENABLED=1
export GOMAXPROCS="${GOMAXPROCS:-2}"
go vet -p 2 ./...
go test -p 2 ./... -count=1 -timeout 300s
go test -p 2 -race ./... -count=1 -timeout 300s
mkdir -p dist
go build -p 2 -trimpath -buildmode=c-shared \
  -ldflags='-s -w -X main.pluginVersion=0.1.21-personal.1' \
  -o dist/freetier2api-v0.1.21-personal.1.so .
file dist/freetier2api-v0.1.21-personal.1.so
sha256sum dist/freetier2api-v0.1.21-personal.1.so
