# NTP Settings

The device keeps its own clock in sync with upstream NTP servers over the WAN and serves time to LAN clients. Both roles
run in `chrony`. LAN clients learn the gateway address as their NTP server from DHCP option 42, so they never need to
reach a public NTP server themselves.

## Default upstream

By default the device syncs with Cloudflare's public NTP service:

```chrony
server time.cloudflare.com iburst
```

Cloudflare is the default because its [NTP usage documentation](https://developers.cloudflare.com/time-services/ntp/usage/)
invites this use, it is served by global anycast, and it does not smear leap seconds. Standard, non-smeared time keeps
the device compatible with typical site NTP servers and the NTP Pool.

If the WAN is down or upstream sync fails, chrony keeps serving LAN clients as a `local stratum 10` source. LAN devices
keep moving forward together, but only as accurately as the gateway's clock until upstream sync returns.

## Choose your own servers

1. Pick upstream servers that all handle leap seconds the same way (see below). On a network with a reliable,
   managed site time service, prefer that.
2. Set them in `config.toml`:

   ```toml
   [network.ntp]
   servers = ["ntp1.example.internal", "ntp2.example.internal"]
   ```

3. Apply the configuration. The device rewrites its chrony settings during first provisioning, every change, and every
   rollback.
4. Check that the device is synchronized:

   ```sh
   chronyc sources -v
   chronyc tracking
   timedatectl
   ```

Upstream DNS settings are separate from NTP. Use `network.dns_servers`, `network.dns_search_domains`, or the
per-interface DNS settings when the device itself needs specific resolvers. LAN clients still get the gateway address as
their DNS and NTP server through DHCP options 6 and 42.

## Do not mix leap-smearing sources

Some public NTP providers, including Google Public NTP, smear leap seconds: they spread the one-second adjustment over
a whole day instead of applying it at once. During that window their clocks deliberately differ from standard UTC.

If you mix smearing and non-smearing servers, valid sources disagree around a leap second, and chrony may treat them as
unstable. Keep every configured server in one family: either all standard, non-smearing sources, or all from the same
smearing provider. To use Google Public NTP, follow Google's [configuration guidance](https://developers.google.com/time/guides)
and list only `time1.google.com` through `time4.google.com`, with no Cloudflare, NTP Pool, or other standard servers.
