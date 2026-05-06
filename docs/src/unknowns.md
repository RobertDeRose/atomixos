# Operational Unknowns

These items are intentionally outside the current firmware contract and must be resolved before changing the contract.

| Area                        | Current State                                                              | Resolution Needed                                                                                               |
|-----------------------------|----------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------|
| Active watchdog enforcement | Hardware driver is present; systemd manager watchdog settings are disabled | Complete Rock64 boot reliability validation, then enable `RuntimeWatchdogSec=30s` and `RebootWatchdogSec=10min` |
| USB WiFi                    | Kernel WiFi and Bluetooth stacks are disabled in the current image         | Select supported hardware and firmware, then update kernel config, tests, and docs                              |
| hawkBit updates             | `useHawkbit` disables polling and installs `rauc-hawkbit-updater` only     | Define server configuration, credentials, systemd unit, and verification tests                                  |
| Nixstasis client            | Device-side state paths and management model are documented                | Implement enrollment client, tunnel lifecycle, and credential rotation                                          |
| Provisioned applications    | AtomixOS renders and starts Quadlets from operator config                 | Define fleet policy for image provenance, registry auth, and rollout approval                                   |
