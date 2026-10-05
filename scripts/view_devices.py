#!/usr/bin/env python3
"""Print every device in the repo with age and distance from DEVICE_NAME."""
import json, math, os, socket, sys
import urllib.error, urllib.request
from datetime import datetime, timezone

API = "https://api.github.com"
STALE_MINUTES = 30


def fail(message):
    print(f"error: {message}", file=sys.stderr)
    sys.exit(1)


def api_get(path, token, raw=False):
    accept = "application/vnd.github.raw+json" if raw else "application/vnd.github+json"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": accept,
        "X-GitHub-Api-Version": "2022-11-28",
    }
    request = urllib.request.Request(f"{API}{path}", headers=headers)
    with urllib.request.urlopen(request, timeout=20) as response:
        body = response.read().decode()
    return body if raw else json.loads(body)


def haversine_km(lat_a, lon_a, lat_b, lon_b):
    phi_a, phi_b = math.radians(lat_a), math.radians(lat_b)
    delta_phi = phi_b - phi_a
    delta_lambda = math.radians(lon_b - lon_a)
    chord = math.sin(delta_phi / 2) ** 2 + math.cos(phi_a) * math.cos(phi_b) * math.sin(delta_lambda / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(chord))


def format_age(minutes):
    if minutes < 1:
        return "just now"
    if minutes < 60:
        return f"{minutes:.0f}m"
    if minutes < 1440:
        return f"{minutes / 60:.0f}h"
    return f"{minutes / 1440:.0f}d"


def format_distance(km):
    return f"{km * 1000:.0f} m" if km < 1 else f"{km:.1f} km"


def main():
    token, repo = os.environ.get("GH_TOKEN"), os.environ.get("GH_REPO")
    if not token or not repo:
        fail("GH_TOKEN and GH_REPO must be set")
    branch = os.environ.get("GH_BRANCH", "main")
    me = os.environ.get("DEVICE_NAME") or socket.gethostname()

    entries = api_get(f"/repos/{repo}/contents/locations?ref={branch}", token)
    devices = {}
    for entry in entries:
        if entry["name"].endswith(".json") and entry["name"] != "index.json":
            text = api_get(f"/repos/{repo}/contents/{entry['path']}?ref={branch}", token, raw=True)
            record = json.loads(text)
            devices[record["device"]] = record
    if not devices:
        fail("no device files found in locations/. Run update_location.py on a device first")

    now = datetime.now(timezone.utc)
    here = devices.get(me)
    rows = []
    for name, record in devices.items():
        minutes = (now - datetime.fromisoformat(record["timestamp"])).total_seconds() / 60
        if here is None or name == me:
            distance = "-"
        else:
            distance = format_distance(haversine_km(here["lat"], here["lon"], record["lat"], record["lon"]))
        age = format_age(minutes) + (" (stale)" if minutes > STALE_MINUTES else "")
        rows.append((minutes, [name, f"{record['lat']:.3f}", f"{record['lon']:.3f}", age, distance]))
    rows.sort(key=lambda row: row[0])

    table = [["DEVICE", "LAT", "LON", "AGE", "DIST-TO-ME"]] + [cells for _, cells in rows]
    widths = [max(len(row[column]) for row in table) for column in range(5)]
    for row in table:
        print("  ".join(cell.ljust(width) for cell, width in zip(row, widths)).rstrip())
    if here is None:
        print(f"\nnote: '{me}' has no location file, so distances are unavailable.", file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except urllib.error.HTTPError as error:
        fail(f"GitHub returned {error.code}: {error.read().decode()[:200]}")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        fail(str(error))
