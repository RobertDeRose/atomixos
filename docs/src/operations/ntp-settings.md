# NTP Settings

AtomixOS uses `chrony` as both an upstream NTP client on WAN and an NTP server for LAN clients. LAN clients receive the
gateway address through DHCP option 42 and should query the gateway instead of reaching public NTP servers directly.

## Default Upstream

The default upstream is Cloudflare public NTP:

```chrony
server time.cloudflare.com iburst
```

Cloudflare is the default because its [NTP usage documentation](https://developers.cloudflare.com/time-services/ntp/usage/)
explicitly describes using `time.cloudflare.com`, the service is global anycast, and Cloudflare does not leap-smear time.
That non-smearing behavior matches standard NTP and keeps AtomixOS compatible with typical site-local NTP servers and
the NTP Pool.

If WAN is unavailable or upstream sync fails, chrony still serves LAN clients from `local stratum 10`. This keeps isolated
LAN devices moving forward, but the time is only as accurate as the gateway clock until upstream sync returns.

## Leap Smearing Warning

Some public NTP providers, including Google Public NTP, use leap smearing. A leap smear spreads a leap-second adjustment
over a window of time instead of exposing the leap second at one instant. That can be useful for large application fleets,
but during the smear window the smeared clock intentionally differs from standard UTC.

Do not mix leap-smearing and non-leap-smearing NTP sources in the same chrony configuration. Mixing them can make valid
time sources disagree, especially around leap-second events, and chrony may treat that as jitter or source instability.

If an operator chooses Google Public NTP, follow Google's
[configuration guidance](https://developers.google.com/time/guides) and use only Google time sources such as
`time1.google.com` through `time4.google.com`. Do not combine those sources with Cloudflare, NTP Pool, DHCP-provided NTP,
or other standard non-smearing servers.

## Operator Overrides

For production networks with an enterprise or site-local time service, prefer the local NTP service when it is reliable
and managed. Keep all configured upstreams in the same leap-second behavior family: either all standard non-smearing
sources or all sources from the same smearing provider.

Set upstream NTP servers with `[network.ntp].servers` in `config.toml`. The provisioning pipeline renders the values into
`/data/config/lan-settings.json`, and `lan-gateway-apply.service` updates the chrony runtime snippet during first
provisioning, re-apply, and rollback.

Host DNS resolver settings are separate from NTP. Use `network.dns_servers`, `network.dns_search_domains`, or
interface-specific DNS settings when the host resolver needs explicit DNS configuration; LAN clients still receive the
gateway address for DNS and NTP via DHCP options 6 and 42.

After applying NTP changes, verify synchronization with:

```sh
chronyc sources -v
chronyc tracking
timedatectl
```
