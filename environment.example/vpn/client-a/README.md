# VPN Environment Example

Create a matching ignored directory at `environment/vpn/client-a` with the
OpenVPN profile and any referenced credentials/certificates.

The runtime image expects the OpenVPN config to be named:

```text
client.ovpn
```

If the profile references files such as `ca.crt`, `client.crt`, `client.key`,
`secret`, or `key-password.txt`, keep those files in the same ignored
directory and reference them with relative paths from `client.ovpn`.

