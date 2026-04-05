ARG PYTHON_BASE_IMAGE=python:3.11-slim-bookworm

FROM ${PYTHON_BASE_IMAGE} AS builder

ARG UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ARG UV_EXTRA_INDEX_URL=https://pypi.org/simple

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_INDEX_URL=${UV_INDEX_URL} \
    PIP_EXTRA_INDEX_URL=${UV_EXTRA_INDEX_URL} \
    UV_INDEX_URL=${UV_INDEX_URL} \
    UV_EXTRA_INDEX_URL=${UV_EXTRA_INDEX_URL} \
    UV_LINK_MODE=copy

WORKDIR /app

RUN python -m pip install "uv>=0.6,<1"

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev


FROM ${PYTHON_BASE_IMAGE} AS runtime

ARG APT_MIRROR=https://mirrors.tuna.tsinghua.edu.cn/debian
ARG APT_SECURITY_MIRROR=https://mirrors.tuna.tsinghua.edu.cn/debian-security

ENV PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    TZ=Asia/Shanghai \
    PATH=/app/.venv/bin:$PATH \
    ORACLE_CLIENT_LIB_DIR=/opt/oracle/instantclient_11_2 \
    ORACLE_THICK_MODE=true \
    LD_LIBRARY_PATH=/opt/oracle/instantclient_11_2:$LD_LIBRARY_PATH

RUN set -eux; \
    if [ -n "${APT_MIRROR}" ]; then \
      if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
        sed -i "s|http://deb.debian.org/debian|${APT_MIRROR}|g; s|http://security.debian.org/debian-security|${APT_SECURITY_MIRROR}|g" /etc/apt/sources.list.d/debian.sources; \
      fi; \
      if [ -f /etc/apt/sources.list ]; then \
        sed -i "s|http://deb.debian.org/debian|${APT_MIRROR}|g; s|http://security.debian.org/debian-security|${APT_SECURITY_MIRROR}|g" /etc/apt/sources.list; \
      fi; \
    fi; \
    apt-get update; \
    if ! apt-get install -y --no-install-recommends libaio1; then \
      apt-get install -y --no-install-recommends libaio1t64; \
    fi; \
    apt-get install -y --no-install-recommends libnsl2 tzdata; \
    if [ ! -e /usr/lib/x86_64-linux-gnu/libaio.so.1 ] && [ -e /usr/lib/x86_64-linux-gnu/libaio.so.1t64 ]; then \
      ln -s /usr/lib/x86_64-linux-gnu/libaio.so.1t64 /usr/lib/x86_64-linux-gnu/libaio.so.1; \
    fi; \
    if [ ! -e /lib/x86_64-linux-gnu/libaio.so.1 ] && [ -e /lib/x86_64-linux-gnu/libaio.so.1t64 ]; then \
      ln -s /lib/x86_64-linux-gnu/libaio.so.1t64 /lib/x86_64-linux-gnu/libaio.so.1; \
    fi; \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY autotask_api /app/autotask_api
COPY frontend /app/frontend
COPY instantclient_11_2 /opt/oracle/instantclient_11_2

RUN set -eux; \
    ln -sf /opt/oracle/instantclient_11_2/libclntsh.so.11.1 /opt/oracle/instantclient_11_2/libclntsh.so; \
    ln -sf /opt/oracle/instantclient_11_2/libocci.so.11.1 /opt/oracle/instantclient_11_2/libocci.so; \
    mkdir -p /app/uploads/scripts /app/uploads/extracted

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5).read()"

CMD ["uvicorn", "autotask_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
