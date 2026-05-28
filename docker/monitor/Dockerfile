FROM postgres:16-bookworm

RUN apt-get update \
  && apt-get install -y --no-install-recommends \
    bash \
    ca-certificates \
    curl \
    jq \
    tzdata \
  && rm -rf /var/lib/apt/lists/*

ENV TZ=America/Sao_Paulo
ENV PGCONNECT_TIMEOUT=10

WORKDIR /work

CMD ["bash"]

