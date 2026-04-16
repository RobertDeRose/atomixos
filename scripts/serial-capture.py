#!/usr/bin/env python3
"""Serial capture for Rock64 debug console.

Connects to the Rock64 UART2 debug serial port, printing output to stdout
and logging to a file simultaneously. Automatically reconnects when the
USB-serial adapter disconnects (e.g. during board power cycles).

Environment variables:
  SERIAL_PORT  — device path (set by mise task, auto-detected, should be /dev/cu.*)
  SERIAL_BAUD  — baud rate (default: 1500000)
  SERIAL_LOG   — log file path (default: /tmp/rock64-serial.log)
  SERIAL_TIMEOUT — capture timeout in seconds, 0=infinite (default: 0)

On macOS, always use /dev/cu.usbserial-* (not /dev/tty.usbserial-*). The tty.*
device waits for DCD (carrier detect) before open() returns, which blocks when
the board isn't powered yet. The cu.* device opens immediately.

Usage:
  nix-shell -p python3Packages.pyserial --run 'python3 scripts/serial-capture.py'

Or via mise:
  mise run serial
"""

import serial
import sys
import time
import os


PORT = os.environ.get("SERIAL_PORT")
if not PORT:
    print(
        "ERROR: SERIAL_PORT not set. Use 'mise run serial' for auto-detection.",
        file=sys.stderr,
    )
    sys.exit(1)
BAUD = int(os.environ.get("SERIAL_BAUD", "1500000"))
LOG = os.environ.get("SERIAL_LOG", "/tmp/rock64-serial.log")
TIMEOUT = int(os.environ.get("SERIAL_TIMEOUT", "0"))


def open_port():
    """Open the serial port. Returns None if it can't be opened.

    On macOS, PORT should be /dev/cu.usbserial-* which opens immediately
    without waiting for DCD (carrier detect). The tty.* variant blocks
    until the remote end asserts DCD, hanging if the board is off.
    """
    try:
        return serial.Serial(PORT, BAUD, timeout=0.5)
    except (serial.SerialException, OSError):
        return None


def wait_for_port(max_wait=120):
    """Wait for the serial device to appear and open it.

    Retries for up to max_wait seconds — handles the case where the
    USB-serial adapter disappears during a board power cycle.
    """
    printed = False
    for _ in range(max_wait):
        if os.path.exists(PORT):
            conn = open_port()
            if conn:
                return conn
        if not printed:
            print(f"[waiting for {PORT}...]", file=sys.stderr, flush=True)
            printed = True
        time.sleep(1)
    return None


def main():
    print(f"Serial capture — {PORT} @ {BAUD} baud", file=sys.stderr)
    print(f"Logging to {LOG}", file=sys.stderr)
    if TIMEOUT > 0:
        print(f"Timeout: {TIMEOUT}s", file=sys.stderr)
    print("Press Ctrl+C to stop.\n", file=sys.stderr, flush=True)

    conn = wait_for_port()
    if not conn:
        print(f"ERROR: Timed out waiting for {PORT}", file=sys.stderr)
        sys.exit(1)

    print("Connected! Capturing...\n", file=sys.stderr, flush=True)

    start = time.time()
    total_bytes = 0

    with open(LOG, "wb") as logfile:
        try:
            while True:
                # Check timeout
                if TIMEOUT > 0 and (time.time() - start) >= TIMEOUT:
                    print(
                        f"\n[timeout after {TIMEOUT}s]",
                        file=sys.stderr,
                        flush=True,
                    )
                    break

                try:
                    data = conn.read(4096)
                    if data:
                        total_bytes += len(data)
                        sys.stdout.buffer.write(data)
                        sys.stdout.buffer.flush()
                        logfile.write(data)
                        logfile.flush()
                except (serial.SerialException, OSError):
                    # The UART line can glitch during boot (e.g. U-Boot ->
                    # kernel handoff reconfigures the UART). This throws
                    # OSError even though the USB adapter is still present.
                    # Only treat it as a real disconnect if the device node
                    # has actually disappeared.
                    try:
                        conn.close()
                    except Exception:
                        pass

                    if os.path.exists(PORT):
                        # Device still present — transient UART glitch.
                        # Brief pause then re-open.
                        time.sleep(0.2)
                        conn = open_port()
                        if conn:
                            continue
                        # Couldn't re-open despite device existing — retry
                        # a few times before falling through to full wait.
                        for _ in range(5):
                            time.sleep(0.5)
                            conn = open_port()
                            if conn:
                                break
                        if conn:
                            continue

                    # Device actually gone — full reconnect wait
                    print(
                        "\n[disconnected — waiting for device...]",
                        file=sys.stderr,
                        flush=True,
                    )
                    conn = wait_for_port()
                    if conn:
                        print("[reconnected]\n", file=sys.stderr, flush=True)
                    else:
                        print(
                            "ERROR: Lost connection and timed out reconnecting",
                            file=sys.stderr,
                        )
                        break

        except KeyboardInterrupt:
            pass
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
            elapsed = int(time.time() - start)
            print(
                f"\nCapture stopped. {total_bytes} bytes in {elapsed}s, saved to {LOG}",
                file=sys.stderr,
            )


if __name__ == "__main__":
    main()
