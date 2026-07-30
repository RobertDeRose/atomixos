
# AtomixOS overview

- Project kind: `infrastructure`

## Purpose

Build a secure, reproducible appliance operating system for single-board computers, with atomic A/B OTA updates,
automatic rollback, and container-based application deployment.

## Intended users

Developers, device makers, system integrators, and operators building and managing secure, reproducible appliances on
single-board computers.

## Current scope

Develop and validate a NixOS-based SBC appliance platform with reproducible images, immutable A/B updates and rollback,
secure provisioning, persistent container workloads, and optional remote management. The current implementation uses
Rock64 and an isolated gateway profile as its initial reference platform.

Future behavior belongs in [Planned features](../planned-features.md) until delivered.

## Boundaries

AtomixOS owns the immutable base OS, secure provisioning, update and recovery lifecycle, hardware enablement, and
platform validation. It is not a general-purpose desktop/server distribution, container orchestrator, or universal
router. Application workloads and external fleet-management infrastructure remain deployment-owned, and hardware support
is added explicitly per board.
