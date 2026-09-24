# Put the Coolify dashboard on HTTPS

After first registration through the SSH tunnel, use a dedicated HTTPS hostname for normal Coolify access. Keep raw management ports private.

## 1. Create the DNS record

Use a hostname such as:

```text
coolify.example.com
```

Point it at the VPS according to your DNS/proxy provider.

## 2. Set the Coolify instance URL

**Where: Coolify → Settings → Configuration → General**

Set:

```text
https://coolify.example.com
```

Use this HTTPS domain for the normal dashboard, live logs, realtime features, and browser terminal.

## Security contract

The intended exposure remains:

```text
public TCP:       22, 80, 443
loopback/private: 8000, 6001, 6002
```

The **raw management ports remain private**. Do not publish `8000`, `6001`, or `6002` to fix a browser problem.

## Verify the server-side path first

**Where: VPS/controller**

```bash
make verify-coolify
make audit
```

The verifier checks the loopback health endpoints and proves raw `8000/6001/6002` are not reachable through the managed public target address.

## Enable browser terminal access

**Where: Coolify**

```text
Servers
→ localhost
→ Security
→ Terminal Access
```

Enable terminal access only when you intend to use it. Open an application/container terminal through the HTTPS dashboard domain.

A minimal non-mutating test is:

```sh
id
pwd
printf 'terminal-ok\n'
```

The terminal uses the HTTPS/realtime **websocket** path; it does not require publishing the raw realtime ports.

## If the browser terminal fails

1. run `make verify-coolify`;
2. confirm Terminal Access is enabled;
3. inspect the failed browser WebSocket request/status in developer tools;
4. do not share cookies, XSRF tokens, authorization headers, SSH keys, or private API responses;
5. finish any reviewed server-side change with `make audit`.

A server-side readiness PASS plus a browser websocket failure points to the HTTPS proxy/session path, not to a need for public `6002`.

## References

- Coolify DNS configuration: <https://coolify.io/docs/knowledge-base/dns-configuration>
- Coolify terminal documentation: <https://coolify.io/docs/knowledge-base/internal/terminal>
