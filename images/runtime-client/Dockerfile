# syntax=docker/dockerfile:1.7
FROM debian:bookworm-slim@sha256:3783cc01769c7b2b1b83a5c5ad96c815348e28ed7da68e2e3687004faa906251 AS crictl

ADD --checksum=sha256:83855e114566a8a8c44c548d515670f51de3a5e1da8b2effb59870e2f10c25a3 \
    https://github.com/kubernetes-sigs/cri-tools/releases/download/v1.36.0/crictl-v1.36.0-linux-amd64.tar.gz \
    /tmp/crictl.tar.gz
RUN mkdir /out \
    && tar -xzf /tmp/crictl.tar.gz -C /out crictl \
    && chmod 0755 /out/crictl

FROM debian:bookworm-slim@sha256:3783cc01769c7b2b1b83a5c5ad96c815348e28ed7da68e2e3687004faa906251

COPY --from=crictl /out/crictl /usr/local/bin/crictl
COPY images/runtime-client/crictl.yaml /etc/crictl.yaml

USER 0:0
CMD ["sleep", "infinity"]
