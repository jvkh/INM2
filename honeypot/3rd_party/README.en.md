# Cowrie SSH Honeypot on a Raspberry Pi

This Compose project publishes Cowrie on TCP port 2222 on the Pi. Cowrie's
container listens on 2222 as in the official Docker quick start. The Pi's own
SSH service remains on TCP port 22.

## FRITZ!Box port forwarding

Create these IPv4 port-sharing rules for the Raspberry Pi's reserved LAN IP:

| Protocol | External port | Destination device | Internal port | Purpose |
|---|---:|---|---:|---|
| TCP | 22 | Raspberry Pi | 2222 | Cowrie honeypot |
| TCP | 2222 | Raspberry Pi | 22 | Real Raspberry Pi SSH |

Do not forward external port 22 to internal port 22; that would expose the
real SSH server instead of Cowrie. Reserve the Pi's LAN address in the FRITZ!Box
so the forwarding rules keep pointing to the right device.

## Start and inspect Cowrie

On the Pi, in this directory:

```sh
docker compose up -d
docker compose logs -f cowrie
```

From outside the home network, test the honeypot with:

```sh
ssh -p 22 root@YOUR_PUBLIC_IP
```

Connect to the real Pi with:

```sh
ssh -p 2222 YOUR_PI_USER@YOUR_PUBLIC_IP
```

Cowrie is an emulated SSH honeypot, not a proxy to the Pi. Keep it isolated and
do not mount host directories or Docker sockets into it. The Compose file drops
Linux capabilities and limits Docker's captured stdout/stderr logs. Those
Docker logs are retained with this setup; Cowrie's own session logs and captured
downloads inside the container do not survive container recreation. Add
persistent storage for Cowrie's `var/` data if you need those artifacts long
term.

## Network checks

The Pi's local firewall must allow inbound TCP 2222 for the forwarded honeypot
traffic. If Docker manages the host firewall, verify that its port publication
is not bypassing your intended firewall policy. Do not expose other container
ports. Confirm the two external ports from a network outside your home LAN.
