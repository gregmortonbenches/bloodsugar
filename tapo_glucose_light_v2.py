#!/usr/bin/env python3
"""
Glucose -> Tapo L530 bulb colour.

Uses the `tapo` library (mihai-dinculescu), NOT python-kasa. python-kasa cannot
control this bulb: firmware 1.4.x uses TPAP encryption, which the stable release
rejects outright and the experimental fork gets past only to hit 403 on every
set_device_info call. This library works.

Note: the bulb expires its auth session in well under a minute, so this opens a
fresh session on every cycle rather than holding one open.

Setup:
  /opt/homebrew/bin/pip3.11 install tapo
  export TAPO_EMAIL="..."
  export TAPO_PASSWORD="..."
  /opt/homebrew/bin/python3.11 tapo_glucose_light_v2.py
"""

import asyncio
import json
import os
import time
import urllib.request

from tapo import ApiClient

BULB_IP = "192.168.1.214"
NIGHTSCOUT_URL = "https://p01--nightscout--cqvfsjd8b54h.code.run"
POLL_SECONDS = 60

TAPO_EMAIL = os.environ["TAPO_EMAIL"]
TAPO_PASSWORD = os.environ["TAPO_PASSWORD"]

TARGET_LOW = 6.0
TARGET_HIGH = 8.0

# Thermal ramp: cold = low, hot = high, green = in range.
#
# Hue must move in ONE direction across the whole scale (here: always decreasing).
# Hue is a circle, so a scale that goes up then down revisits colours and becomes
# ambiguous - the previous version did this and mapped 13.0 mmol/L to teal, nearly
# identical to 5.5. Keeping it monotonic guarantees each reading reads uniquely.
#
# The target band is deliberately flat green, so an in-range reading looks steady
# rather than drifting through shades.
STOPS = [
    (2.5, 300),   # magenta      - severe low
    (4.0, 240),   # blue         - low
    (5.5, 180),   # cyan         - drifting low
    (6.0, 120),   # green        - bottom of target
    (8.0, 120),   # green        - top of target
    (10.0, 60),   # yellow       - above target
    (12.0, 30),   # orange       - high
    (16.0, 0),    # red          - severe high
]

# Colour says which direction you're off; brightness says how urgently.
BRIGHTNESS_IN_RANGE = 60
BRIGHTNESS_MAX = 100


def hue_for_mmol(mmol):
    if mmol <= STOPS[0][0]:
        return STOPS[0][1]
    for (m0, h0), (m1, h1) in zip(STOPS, STOPS[1:]):
        if m0 <= mmol <= m1:
            t = (mmol - m0) / (m1 - m0)
            return h0 + (h1 - h0) * t
    return STOPS[-1][1]


def brightness_for_mmol(mmol):
    """Dim and calm in range, ramping to full brightness at the extremes."""
    if TARGET_LOW <= mmol <= TARGET_HIGH:
        return BRIGHTNESS_IN_RANGE
    if mmol < TARGET_LOW:
        t = (TARGET_LOW - mmol) / (TARGET_LOW - STOPS[0][0])
    else:
        t = (mmol - TARGET_HIGH) / (STOPS[-1][0] - TARGET_HIGH)
    t = max(0.0, min(1.0, t))
    return round(BRIGHTNESS_IN_RANGE + (BRIGHTNESS_MAX - BRIGHTNESS_IN_RANGE) * t)


def fetch_latest_mmol():
    url = f"{NIGHTSCOUT_URL}/api/v1/entries.json?count=1"
    with urllib.request.urlopen(url, timeout=10) as resp:
        entries = json.loads(resp.read())
    if not entries:
        raise RuntimeError("Nightscout returned no entries")
    return entries[0]["sgv"] / 18


async def main():
    print("Starting glucose light...")
    while True:
        try:
            mmol = fetch_latest_mmol()
            hue = max(1, min(360, round(hue_for_mmol(mmol))))
            brightness = brightness_for_mmol(mmol)
            device = await ApiClient(TAPO_EMAIL, TAPO_PASSWORD).l530(BULB_IP)
            await device.set_brightness(brightness)
            await device.set_hue_saturation(hue, 100)
            print(f"{time.strftime('%H:%M:%S')}  {mmol:.1f} mmol/L -> hue {hue}, {brightness}%")
        except Exception as err:
            print(f"{time.strftime('%H:%M:%S')}  error: {type(err).__name__}: {err}")

        await asyncio.sleep(POLL_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
