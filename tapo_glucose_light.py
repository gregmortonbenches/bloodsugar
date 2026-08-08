#!/usr/bin/env python3
"""
Polls Nightscout and sets a Tapo color bulb's hue to reflect the current glucose reading.
Must run on the same local network as the bulb (local control, not cloud).

Setup:
  pip install python-kasa

  export TAPO_EMAIL="your_tapo_account_email"
  export TAPO_PASSWORD="your_tapo_account_password"

Edit BULB_IP and NIGHTSCOUT_URL below, then run:
  python3 tapo_glucose_light.py
"""

import asyncio
import os
import time
import urllib.request
import json

from kasa import Discover, Module

# ---- Config - edit these ----
# Connecting directly to a known IP (Tapo app -> bulb -> Device Info) instead of
# broadcast discovery, since broadcast discovery can get silently blocked by
# firewalls/VPNs/network isolation and is much less reliable.
BULB_IP = "192.168.1.214"
NIGHTSCOUT_URL = "https://p01--nightscout--cqvfsjd8b54h.code.run"
POLL_SECONDS = 60

TAPO_EMAIL = os.environ["TAPO_EMAIL"]
TAPO_PASSWORD = os.environ["TAPO_PASSWORD"]

# same color stops as the web app, for consistency across everything you've built
# (mmol, hue in degrees)
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


async def find_bulb():
    print(f"Connecting to {BULB_IP}...")
    dev = await Discover.discover_single(
        BULB_IP, username=TAPO_EMAIL, password=TAPO_PASSWORD
    )
    await dev.update()
    print(f"Connected: {dev.alias}")
    return dev


async def main():
    bulb = await find_bulb()
    light = bulb.modules[Module.Light]

    while True:
        try:
            mmol = fetch_latest_mmol()
            hue = round(hue_for_mmol(mmol))
            print(f"{time.strftime('%H:%M:%S')}  {mmol:.1f} mmol/L -> hue {hue}")
            await light.set_hsv(hue, 100, 80)
        except Exception as err:
            print(f"Error this cycle: {err}")
            # try to reconnect in case the bulb dropped off the network
            try:
                bulb = await find_bulb()
                light = bulb.modules[Module.Light]
            except Exception as reconnect_err:
                print(f"Reconnect also failed: {reconnect_err}")

        await asyncio.sleep(POLL_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
