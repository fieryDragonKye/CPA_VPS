ARG CADDY_IMAGE
FROM ${CADDY_IMAGE}
# High port8080 needs no file capability; keep cap_drop ALL + non-root runtime.
RUN setcap -r /usr/bin/caddy && test -z "$(getcap /usr/bin/caddy)"
USER 10001:10001
