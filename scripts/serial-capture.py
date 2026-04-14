#!/usr/bin/env python3
"""Serial capture for Rock64 debug console.

Connects to the Rock64 UART2 debug serial port, printing output to stdout
and logging to a file simultaneously. Automatically reconnects when the
USB-serial adapter disconnects (e.g. during board power cycles).

Environment variables:
  SERIAL_PORT  — device path (default: /dev/cu.usbserial-DM02496T)
  SERIAL_BAUD  — baud rate (default: 1500000)
  SERIAL_LOG   — log file path (default: /tmp/rock64-serial.log)
  SERIAL_TIMEOUT — capture timeout in seconds, 0=infinite (default: 0)

Usage:
  nix-shell -p python3Packages.pyserial --run 'python3 scripts/serial-capture.py'

Or via mise:
  mise run serial
"""

import serial
import sys
import time
import os


PORT = os.environ.get("SERIAL_PORT", "/dev/cu.usbserial-DM02496T")
BAUD = int(os.environ.get("SERIAL_BAUD", "1500000"))
LOG = os.environ.get("SERIAL_LOG", "/tmp/rock64-serial.log")
TIMEOUT = int(os.environ.get("SERIAL_TIMEOUT", "0"))


def get_port(max_wait=120):
    """Wait for the serial device to appear and open it.

    Retries for up to max_wait seconds — handles the case where the
    USB-serial adapter disappears briefly during a board power cycle.
    """
    for attempt in range(max_wait):
        try:
            if os.path.exists(PORT):
                s = serial.Serial(PORT, BAUD, timeout=0.1)
                return s
        except serial.SerialException:
            pass
        if attempt == 0:
            print(f"[waiting for {PORT}...]", file=sys.stderr, flush=True)
        time.sleep(1)
    return None


def main():
    print(f"Serial capture — {PORT} @ {BAUD} baud", file=sys.stderr)
    print(f"Logging to {LOG}", file=sys.stderr)
    if TIMEOUT > 0:
        print(f"Timeout: {TIMEOUT}s", file=sys.stderr)
    print("Press Ctrl+C to stop.\n", file=sys.stderr, flush=True)

    conn = get_port()
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
                    print(
                        "\n[disconnected — reconnecting...]",
                        file=sys.stderr,
                        flush=True,
                    )
                    try:
                        conn.close()
                    except Exception:
                        pass
                    conn = get_port()
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
