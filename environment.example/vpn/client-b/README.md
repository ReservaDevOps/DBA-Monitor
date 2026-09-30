# Client B VPN files

Create the real directory below and keep it ignored by Git:

```text
environment/vpn/client-b/
```

The compose service expects:

```text
environment/vpn/client-b/client.ovpn
```

Put any certificates, keys and passphrase files referenced by `client.ovpn` in
the same directory. Do not commit real VPN files.
