#!/usr/bin/env python3
"""Report whether a Valeton device is connected (and which one). Runs in
.venv-midi. Emits one JSON line for app/device_io.py:

  {"connected": bool, "device": {"key","name"}|null, "port": str|null}

Read-only enumeration of MIDI ports — touches no device, sends nothing."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from patch import device_protocol, live_read


def main():
    port, profile = live_read.find_port_optional()
    device = {"key": profile.key, "name": profile.name} if profile else None
    device_protocol.emit(
        device_protocol.status_result(port is not None, device=device, port=port)
    )


if __name__ == "__main__":
    main()
