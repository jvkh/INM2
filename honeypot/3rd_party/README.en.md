# Cowrie SSH Honeypot for Linux Servers

This Compose project runs Cowrie in a container and publishes SSH on TCP port
2222 of the server.

## Requirements

- A Linux server with Docker Engine and the Docker Compose plugin
- TCP port 2222 available for the container
- Inbound TCP connectivity to the server, directly or through router or firewall
  forwarding
- Writable storage for `../../cowrie-data/var`

Host port 2222 must be available. With NAT or firewall forwarding, a different
public port can be forwarded to TCP port 2222 on the server. If a real SSH
service runs on the same server, configure its port and reachability separately.
Forwarding must not unintentionally expose the real SSH service.

## Start and inspect

From the directory containing this Compose file:

```sh
docker compose up -d
docker compose logs -f cowrie
```

The honeypot is reachable on TCP port 2222:

```sh
ssh -p 2222 root@SERVER_ADDRESS
```

Check access from an external network. The server firewall and any upstream
router or cloud firewall rules must allow inbound connections to the published
port.

## Behavior and stored data

Cowrie is an emulated SSH honeypot, not a proxy to the server. The container has
no host-directory or Docker-socket mounts. The Compose configuration drops
Linux capabilities, disables SSH forwarding, and limits Docker's captured
stdout/stderr logs. Cowrie presents a Debian 12-style `web01` host and matching
SSH banner. Its `var/` directory persists under `cowrie-data/var`, retaining
event logs, session transcripts, downloads, and generated host keys. Treat
captured files as untrusted; Cowrie does not execute them.

Successful password logins are limited to the decoy credentials in
`userdb.txt`. Twenty commonly exposed weak passwords are listed for `root`; all
other username/password combinations are rejected. Edit the file to change the
accepted pairs, then recreate the container for changes to take effect. Use only
credentials created specifically for the honeypot.
