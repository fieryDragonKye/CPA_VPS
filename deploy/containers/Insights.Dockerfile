ARG PYTHON_IMAGE
FROM ${PYTHON_IMAGE}
RUN groupadd --gid 10001 cpa && useradd --uid 10001 --gid 10001 --no-create-home cpa
COPY insights/server.py insights/run.py insights/pricing.json deploy/healthcheck.py /opt/cpa/
COPY deploy/assets/management.html /opt/cpa/static/management.html
COPY web/LICENSE /opt/cpa/FRONTEND-LICENSE
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /opt/cpa
USER 10001:10001
ENTRYPOINT ["python", "/opt/cpa/run.py"]
