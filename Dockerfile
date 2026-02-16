FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    TZ=Asia/Shanghai \
    PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
    PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn

RUN set -eux; \
    if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
      sed -i 's|http://deb.debian.org/debian|https://mirrors.tuna.tsinghua.edu.cn/debian|g; s|http://security.debian.org/debian-security|https://mirrors.tuna.tsinghua.edu.cn/debian-security|g' /etc/apt/sources.list.d/debian.sources; \
    fi; \
    if [ -f /etc/apt/sources.list ]; then \
      sed -i 's|http://deb.debian.org/debian|https://mirrors.tuna.tsinghua.edu.cn/debian|g; s|http://security.debian.org/debian-security|https://mirrors.tuna.tsinghua.edu.cn/debian-security|g' /etc/apt/sources.list; \
    fi; \
    apt-get update; \
    # Oracle Instant Client runtime dependencies (11g/19c)
    if ! apt-get install -y --no-install-recommends libaio1; then \
      apt-get install -y --no-install-recommends libaio1t64; \
    fi; \
    apt-get install -y --no-install-recommends libnsl2; \
    # Debian trixie ships libaio.so.1t64; Oracle 11g looks for libaio.so.1
    if [ ! -e /usr/lib/x86_64-linux-gnu/libaio.so.1 ] && [ -e /usr/lib/x86_64-linux-gnu/libaio.so.1t64 ]; then \
      ln -s /usr/lib/x86_64-linux-gnu/libaio.so.1t64 /usr/lib/x86_64-linux-gnu/libaio.so.1; \
    fi; \
    if [ ! -e /lib/x86_64-linux-gnu/libaio.so.1 ] && [ -e /lib/x86_64-linux-gnu/libaio.so.1t64 ]; then \
      ln -s /lib/x86_64-linux-gnu/libaio.so.1t64 /lib/x86_64-linux-gnu/libaio.so.1; \
    fi; \
    apt-get update && apt-get install -y --no-install-recommends \
      tzdata \
      gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

RUN mkdir -p /app/logs

COPY monitor_wcnr_jq.py /app/
COPY zq_kshddpt_dsjfx_jq.py /app/
COPY data_scraper_multi.py /app/
COPY 0123_dxpt_ceshi.py /app/
COPY task_runner.py /app/

ENTRYPOINT ["python", "/app/task_runner.py"]
