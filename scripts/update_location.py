#!/usr/bin/env python3
"""Push this device's rounded location to GitHub via the contents API (pure HTTP)."""
import base64, json, os, re, shutil, socket, subprocess, sys
import urllib.error, urllib.request
from datetime import datetime, timezone

API = "https://api.github.com"
HEARTBEAT_MINUTES = 20  # unchanged location is re-pushed at most this often


def fail(message):
    print(f"error: {message}", file=sys.stderr)
    sys.exit(1)


def http_json(url, method="GET", headers=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, method=method, headers=headers or {}, data=data)
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def locate():
    command = os.environ.get("LOCATION_COMMAND")
    if command:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=90)
        if result.returncode != 0:
            fail(f"LOCATION_COMMAND failed: {result.stderr.strip()}")
        fix = json.loads(result.stdout)
        return (fix.get("latitude", fix.get("lat")),
                fix.get("longitude", fix.get("lon")),
                fix.get("accuracy"))
    fix = http_json("http://ip-api.com/json?fields=status,message,lat,lon")
    if fix.get("status") != "success":
        fail(f"IP geolocation failed: {fix.get('message', 'unknown reason')}")
    return fix["lat"], fix["lon"], 5000  # IP lookups are city-level at best


def battery_percent():
    try:
        import psutil
        battery = psutil.sensors_battery()
        if battery:
            return round(battery.percent)
    except Exception:
        pass
    if shutil.which("termux-battery-status"):
        try:
            output = subprocess.run(["termux-battery-status"], capture_output=True, text=True, timeout=15)
            return json.loads(output.stdout)["percentage"]
        except Exception:
            pass
    return None


def fetch_existing(url, branch, headers):
    try:
        entry = http_json(f"{url}?ref={branch}", headers=headers)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None, None
        raise
    return entry["sha"], json.loads(base64.b64decode(entry["content"]))


def main():
    token, repo = os.environ.get("GH_TOKEN"), os.environ.get("GH_REPO")
    if not token or not repo:
        fail("GH_TOKEN and GH_REPO must be set")
    branch = os.environ.get("GH_BRANCH", "main")
    device = re.sub(r"[^A-Za-z0-9_-]", "-", os.environ.get("DEVICE_NAME") or socket.gethostname())
    if device == "index":
        fail("DEVICE_NAME 'index' is reserved")

    lat, lon, accuracy = locate()
    if lat is None or lon is None:
        fail("location source returned no coordinates")
    now = datetime.now(timezone.utc).replace(microsecond=0)
    record = {
        "device": device,
        "lat": round(float(lat), 3),
        "lon": round(float(lon), 3),
        "accuracy": accuracy,
        "battery": battery_percent(),
        "timestamp": now.isoformat(),
    }

    url = f"{API}/repos/{repo}/contents/locations/{device}.json"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    sha, previous = fetch_existing(url, branch, headers)
    if previous and (previous["lat"], previous["lon"]) == (record["lat"], record["lon"]):
        age_minutes = (now - datetime.fromisoformat(previous["timestamp"])).total_seconds() / 60
        if age_minutes < HEARTBEAT_MINUTES:
            print(f"{device}: location unchanged, skipped commit")
            return

    body = {
        "message": f"loc: {device}",
        "content": base64.b64encode((json.dumps(record, indent=2) + "\n").encode()).decode(),
        "branch": branch,
    }
    if sha:
        body["sha"] = sha
    http_json(url, method="PUT", headers=headers, body=body)
    print(f"{device}: pushed {record['lat']}, {record['lon']} at {record['timestamp']}")


if __name__ == "__main__":
    try:
        main()
    except urllib.error.HTTPError as error:
        fail(f"GitHub returned {error.code}: {error.read().decode()[:200]}")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, subprocess.TimeoutExpired) as error:
        fail(str(error))
