FROM python:3.12-slim
ARG UID=568
ARG GID=568
RUN apt-get update && apt-get install -y --no-install-recommends frotz curl ca-certificates tini \
 && rm -rf /var/lib/apt/lists/* \
 && ln -s /usr/games/dfrotz /usr/local/bin/dfrotz \
 && groupadd -g ${GID} apps 2>/dev/null || true \
 && useradd -u ${UID} -g ${GID} -M -d /app -s /usr/sbin/nologin apps 2>/dev/null || true
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY bot ./bot
COPY scripts ./scripts
COPY tests ./tests
RUN mkdir -p /data/games /data/saves && chown -R ${UID}:${GID} /data /app
ENV GAMES_DIR=/data/games SAVES_DIR=/data/saves PYTHONUNBUFFERED=1
USER ${UID}:${GID}
VOLUME ["/data/games", "/data/saves"]
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "-m", "bot.main"]
