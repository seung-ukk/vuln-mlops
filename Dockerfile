FROM python:3.11.13-slim-bookworm@sha256:86adf8dbadc3d6e82ee5dd2c74bec2e1c2467cdad47886280501df722372d2e1

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    GIT_PYTHON_REFRESH=quiet \
    MLFLOW_ALLOW_PICKLE_DESERIALIZATION=false \
    KUBECONFIG=/opt/modelgate/ops/kubeconfig

WORKDIR /opt/modelgate

COPY requirements/base.txt /opt/modelgate/requirements/base.txt
RUN pip install --no-cache-dir --requirement /opt/modelgate/requirements/base.txt \
    && apt-get update \
    && apt-get install --no-install-recommends -y curl git procps \
    && curl -fsSL -o /usr/local/bin/kubectl https://dl.k8s.io/release/v1.36.4/bin/linux/amd64/kubectl \
    && echo '8b8f088da2dab964f853b38464033b1be15ede2839eca751482357c45abdd05a  /usr/local/bin/kubectl' | sha256sum -c - \
    && chmod 0755 /usr/local/bin/kubectl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 modelgate \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /bin/sh modelgate \
    && mkdir -p /var/lib/modelgate /artifacts /tmp/modelgate \
    && chown -R 10001:10001 /var/lib/modelgate /artifacts /tmp/modelgate

COPY --chown=10001:10001 modelgate /opt/modelgate/modelgate
COPY --chown=10001:10001 modelgate/VALIDATOR_OPERATIONS.txt /opt/modelgate/VALIDATOR_OPERATIONS.txt
COPY --chown=10001:10001 modelgate/ops /opt/modelgate/ops
COPY --chown=10001:10001 runtime_builder /opt/modelgate/runtime_builder

USER 10001:10001

EXPOSE 8080
CMD ["uvicorn", "modelgate.main:app", "--host", "0.0.0.0", "--port", "8080"]
