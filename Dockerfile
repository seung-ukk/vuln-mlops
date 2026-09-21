FROM python:3.11.13-slim-bookworm@sha256:86adf8dbadc3d6e82ee5dd2c74bec2e1c2467cdad47886280501df722372d2e1

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    GIT_PYTHON_REFRESH=quiet \
    MLFLOW_ALLOW_PICKLE_DESERIALIZATION=false

WORKDIR /opt/modelgate

COPY requirements/base.txt /opt/modelgate/requirements/base.txt
RUN pip install --no-cache-dir --requirement /opt/modelgate/requirements/base.txt \
    && groupadd --gid 10001 modelgate \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin modelgate \
    && mkdir -p /var/lib/modelgate /artifacts /tmp/modelgate \
    && chown -R 10001:10001 /var/lib/modelgate /artifacts /tmp/modelgate

COPY --chown=10001:10001 modelgate /opt/modelgate/modelgate
COPY --chown=10001:10001 poc /opt/modelgate/poc

USER 10001:10001

EXPOSE 8080
CMD ["uvicorn", "modelgate.main:app", "--host", "0.0.0.0", "--port", "8080"]
