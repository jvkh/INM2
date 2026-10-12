# INM2
Internet Noise Monitor - Monitors traffic on a dedicated internet server

## GeoLite IP localization

The collector optionally uses local MaxMind GeoLite2 databases. Put these files
in the project-level `geoip/` directory:

- `GeoLite2-City.mmdb` for city and country
- `GeoLite2-ASN.mmdb` for ASN and network organization/provider

Docker Compose mounts this directory read-only at `/geoip`. The paths can be
overridden with `GEOLITE_CITY_DB` and `GEOLITE_ASN_DB`. If a database is
missing, the collector continues importing and leaves the corresponding actor
fields empty. Existing actors with missing location data are looked up only
when a new request from that actor is imported.

GeoLite2 files must be obtained under MaxMind's terms; they are local data files
and are excluded from version control.

The collector only imports globally routable client IP addresses. Requests with
private, loopback, link-local, reserved, or invalid addresses are skipped and
removed from the processed log prefix.
