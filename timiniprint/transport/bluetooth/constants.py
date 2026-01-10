from __future__ import annotations

import sys
import uuid

SPP_UUID = uuid.UUID("00001101-0000-1000-8000-00805f9b34fb")
RFCOMM_CHANNELS = [1, 2, 3, 4, 5]
IS_WINDOWS = sys.platform.startswith("win")
