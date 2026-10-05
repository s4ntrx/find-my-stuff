# Device tracker on GitHub

Each device pushes a rounded location to `locations/<device>.json` every 5 minutes. A GitHub Action merges them into `locations/index.json`. A MapLibre page on GitHub Pages reads that one file.

**Read this first:** GitHub Pages on a free account requires a **public** repo. Every location, and every past location in git history, is world-readable to anyone who finds the repo URL. Coordinates are rounded to 3 decimals (~110 m), which still reveals your home and routine. A non-obvious repo name is obscurity, not security. If that is unacceptable, skip the map and use `view_devices.py` with a private repo.

## Quick start

```bash
# 1. Create an empty PUBLIC repo with an opaque name, then:
git clone https://github.com/s4ntrx/find-my-stuff.git && cd find-my-stuff
# 2. Copy these files in, then: git add -A && git commit -m init && git push
# 3. Settings > Pages > Deploy from a branch > main > /docs
# 4. Edit REPO (and BRANCH) near the top of docs/index.html
# 5. Create a PAT (below), then on every device:
pip install -r scripts/requirements.txt
export GH_TOKEN=github_pat_xxx GH_REPO=s4ntrx/find-my-stuff DEVICE_NAME=dev-a
python3 scripts/update_location.py        # first push
python3 scripts/view_devices.py           # terminal table
# 6. Actions tab > aggregate > Run workflow (once), then open:
#    https://yourusername.github.io/find-my-stuff
```

## Create the PAT

1. GitHub > Settings > Developer settings > Personal access tokens > **Fine-grained tokens** > Generate new token.
2. Expiration: 90 days. Resource owner: your account.
3. Repository access: **Only select repositories**, pick this repo.
4. Repository permissions: **Contents: Read and write**. Leave everything else, especially Workflows, at no access.
5. Copy the `github_pat_...` value once. Use one token per device so a lost device can be revoked alone.

## Environment variables

| Variable | Meaning | Default |
|---|---|---|
| `GH_TOKEN` | fine-grained PAT | required |
| `GH_REPO` | `s4ntrx/find-my-stuff` | required |
| `GH_BRANCH` | branch to write | `main` |
| `DEVICE_NAME` | file name, letters/digits/`-`/`_` | hostname |
| `LOCATION_COMMAND` | shell command printing JSON with `lat`/`lon` or `latitude`/`longitude` (e.g. GPS) | IP lookup via ip-api.com |

If coordinates are unchanged, the script skips the commit until the entry is 20 minutes old. This cuts commits roughly 4x for parked devices and keeps the marker fresh (<30 min).

## Automation

**Linux / macOS**: `crontab -e`

```cron
*/5 * * * * GH_TOKEN=github_pat_xxx GH_REPO=s4ntrx/find-my-stuff DEVICE_NAME=dev-a /usr/bin/python3 $HOME/your-repo/scripts/update_location.py >> /tmp/location.log 2>&1
```

**Windows**: Task Scheduler. Create Task > Triggers: Daily, repeat every 5 minutes indefinitely > Action: Start a program `cmd` with arguments
`/c set GH_TOKEN=github_pat_xxx&& set GH_REPO=s4ntrx/find-my-stuff&& set DEVICE_NAME=dev-b&& python C:\your-repo\scripts\update_location.py`.
Or in one line: `schtasks /Create /SC MINUTE /MO 5 /TN LocationSync /TR "cmd /c set GH_TOKEN=github_pat_xxx&& set GH_REPO=s4ntrx/find-my-stuff&& set DEVICE_NAME=dev-b&& python C:\your-repo\scripts\update_location.py"`.

**Android (Termux + Termux:API)**

```bash
pkg install python termux-api
cat > ~/loc.sh <<'SH'
#!/data/data/com.termux/files/usr/bin/sh
export GH_TOKEN=github_pat_xxx GH_REPO=s4ntrx/find-my-stuff DEVICE_NAME=phone
export LOCATION_COMMAND="termux-location -p gps -r once"
python $HOME/your-repo/scripts/update_location.py
SH
chmod +x ~/loc.sh
termux-job-scheduler --script ~/loc.sh --period-ms 900000
```

Android's job scheduler will not run periodic jobs more often than every 15 minutes, so that is the real cadence. For a true 5-minute loop, run `pkg install cronie termux-services`, `sv-enable crond`, add `*/5 * * * * ~/loc.sh` via `crontab -e`, and keep `termux-wake-lock` active. Expect battery cost.

**iOS (Shortcuts, fragile)**: Get Current Location > Round to 3 decimals > Dictionary `{device, lat, lon, accuracy, battery, timestamp}` > Get Contents of URL `GET https://api.github.com/repos/s4ntrx/find-my-stuff/contents/locations/phone.json` (headers `Authorization: Bearer github_pat_xxx`) > read `sha` > Base64 Encode the JSON > Get Contents of URL `PUT` same URL with JSON body `{message, content, sha}`. Personal Automations cannot repeat every 5 minutes; expect hourly or event-based runs at best.

## Housekeeping

**Monthly history reset** (run in a local clone; needs permission to force-push the branch):

```bash
git checkout --orphan fresh && git add -A && git commit -m "reset history"
git branch -D main && git branch -m main && git push -f origin main
```

Old commits stay fetchable by SHA until GitHub garbage-collects them, and any fork or clone keeps them. Squashing reduces bloat; it does not erase published locations.

**Rotate tokens every 90 days**: generate a new PAT with the same scope, update each device, then delete the old token.

**Lost device**: Settings > Developer settings > Fine-grained tokens > that device's token > Delete. Then delete `locations/<device>.json` and rebuild the index (Actions > aggregate > Run workflow).

## Tradeoffs

- **Not realtime.** Commits, Pages and the raw-file cache add up to a lag of minutes. GitHub is a file host, not a pub/sub store.
- **5-minute floor.** Each update is a commit plus an Action run. Faster means commit bloat and a growing history, for ~110 m resolution that does not need it.
- **Why the aggregate Action.** Unauthenticated API calls are limited to 60/hr per IP. One merged `index.json` keeps the viewer at a single request per refresh with no token in the browser.
- **Graduate** to OwnTracks or Traccar (self-hosted, real GPS clients, history UI) or Firebase/Supabase (realtime, auth, private data) when you need sub-minute updates, private data, or more than a handful of devices.
