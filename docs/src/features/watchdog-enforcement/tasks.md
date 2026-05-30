# Tasks: watchdog-enforcement

## Feature Spec And Setup

- [x] T000 Create feature branch and worktree from `dev`
- [x] T001 Draft `design.md` from `docs/src/planned-features.md`
- [x] T002 Review existing watchdog module, boot-count script, RAUC rollback docs, and VM tests
- [x] T003 Resolve hardware enforcement default policy
- [ ] T004 Resolve physical hang simulation method before hardware execution

## Watchdog Option Surface

- [x] T010 Inspect existing `modules/watchdog.nix` option structure
- [x] T011 Add or refine `atomixos.watchdog.*` options for hardware enforcement
- [x] T012 Keep VM, development, and Rock64 defaults disabled unless explicitly enabled
- [x] T013 Add module assertions or guards for unsupported hardware contexts if needed

## Rock64 Systemd Enforcement

- [x] T020 Render `RuntimeWatchdogSec=30s` when hardware enforcement is enabled
- [x] T021 Render `RebootWatchdogSec=10min` when hardware enforcement is enabled
- [ ] T022 Confirm Rock64 watchdog driver/device availability in the target image
- [x] T023 Ensure disabled enforcement leaves local recovery and VM boot unchanged

## Rollback Integration

- [x] T030 Review watchdog boot-count recording path
- [ ] T031 Verify watchdog-triggered boots count toward rollback threshold
- [x] T032 Preserve existing custom-backend `rauc-watchdog` VM rollback behavior
- [x] T033 Document U-Boot `BOOT_*_LEFT` hardware assumptions and custom VM simulation differences

## Tests And Validation

- [x] T040 Add Nix evaluation or module tests for watchdog option defaults
- [x] T041 Add or update VM assertions for rendered systemd manager settings where applicable
- [x] T042 Keep existing `rauc-watchdog` VM check passing
- [x] T043 Add hardware test instructions for systemd hang and watchdog reboot timing
- [x] T044 Add hardware test instructions for three-failure rollback validation
- [x] T045 Add 72-hour soak validation checklist

## Documentation And Closeout

- [x] T900 Update `docs/src/architecture/update-rollback.md` with watchdog-triggered rollback behavior
- [x] T901 Update `docs/src/hardware-testing.md` with physical watchdog validation steps
- [x] T902 Update watchdog specs/module docs if applicable
- [x] T903 Update `docs/src/planned-features.md` after implementation completes
- [x] T904 Add this feature spec to `docs/src/SUMMARY.md` if feature specs are listed there
- [x] T999 Run targeted tests, docs reconciliation, hardware-validation gap review, and close out the feature spec
