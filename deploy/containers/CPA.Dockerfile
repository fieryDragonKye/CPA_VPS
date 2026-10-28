ARG PYTHON_IMAGE
FROM ${PYTHON_IMAGE}
ARG TARGETARCH
RUN groupadd --gid 10001 cpa && useradd --uid 10001 --gid 10001 --no-create-home cpa && mkdir -p /var/lib/cpa /opt/cpa/static && chown 10001:10001 /var/lib/cpa
COPY deploy/vendor/linux-${TARGETARCH}/cli-proxy-api /opt/cpa/cli-proxy-api
COPY deploy/assets/management.html /opt/cpa/static/management.html
COPY licenses/CPA-LICENSE /opt/cpa/LICENSE
COPY web/LICENSE /opt/cpa/FRONTEND-LICENSE
COPY deploy/healthcheck.py /opt/cpa/healthcheck.py
RUN chmod 0555 /opt/cpa/cli-proxy-api
ENV MANAGEMENT_STATIC_PATH=/opt/cpa/static HOME=/var/lib/cpa XDG_CACHE_HOME=/tmp/cpa-cache
WORKDIR /var/lib/cpa
USER 10001:10001
ENTRYPOINT ["/opt/cpa/cli-proxy-api"]
CMD ["-config", "/etc/cpa/config.yaml"]
