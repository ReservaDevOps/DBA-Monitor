FROM debian:bookworm-slim

RUN apt-get update \
  && apt-get install -y --no-install-recommends \
    ca-certificates \
    iproute2 \
    iputils-ping \
    netcat-openbsd \
    openvpn \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /vpn

CMD ["openvpn", "--cd", "/vpn", "--config", "/vpn/client.ovpn"]
