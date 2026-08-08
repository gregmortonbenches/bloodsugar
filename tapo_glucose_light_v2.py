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
BRIGHTNESS = 80

TAPO_EMAIL = os.environ["TAPO_EMAIL"]
TAPO_PASSWORD = os.environ["TAPO_PASSWORD"]

# (mmol, hue degrees) - same stops as the penguin web app
STOPS = [
    (2.8, 230),   # deep blue - very low
    (3.9, 355),   # red - low
    (5.5, 165),   # teal - low-normal
    (7.5, 150),   # green - target
    (10.0, 40),   # amber - high
    (16.0, 300),  # magenta - very high
]


def hue_for_mmol(mmol):
    if mmol <= STOPS[0][0]:
        return STOPS[0][1]
    for (m0, h0), (m1, h1) in zip(STOPS, STOPS[1:]):
        if m0 <= mmol <= m1:
            t = (mmol - m0) / (m1 - m0)
            return h0 + (h1 - h0) * t
    return STOPS[-1][1]


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
            device = await ApiClient(TAPO_EMAIL, TAPO_PASSWORD).l530(BULB_IP)
            await device.set_brightness(BRIGHTNESS)
            await device.set_hue_saturation(hue, 100)
            print(f"{time.strftime('%H:%M:%S')}  {mmol:.1f} mmol/L -> hue {hue}")
        except Exception as err:
            print(f"{time.strftime('%H:%M:%S')}  error: {type(err).__name__}: {err}")

        await asyncio.sleep(POLL_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
