# THEA — local CCTV face recognition and alerts

THEA turns existing RTSP cameras into a local face-recognition security system. It samples
camera frames, detects faces with a selectable InsightFace model, matches them against a
watchlist, and pushes confirmed alerts to a React dashboard over WebSockets.

Everything runs on your own machine or LAN. No cloud account, Telegram bot, or external
messaging service is required. The only network access on first run is InsightFace downloading
the `buffalo_l` model files.

## Features

- Multiple RTSP cameras with a smooth 30 FPS preview and separate 3-5 FPS AI detection.
- Selectable InsightFace engines (Buffalo L/S/SC, Antelope V2) plus a mock development engine.
- Admin engine switching from Settings with automatic watchlist re-indexing.
- InsightFace face detection and 512-dimensional embeddings.
- Watchlist enrollment from 1 photo; the image is auto-resampled and its embedding is stored.
- Cosine similarity matching with FAISS when available, NumPy fallback otherwise.
- Confirmation after N consecutive matching frames (default 3) plus per-person/camera cooldown.
- Real-time WebSocket alert events with snapshot, name, camera, time and match confidence.
- SQLite alert history with filters by person, camera and date.
- Cross-camera movement trails when the same person appears on different cameras within a
  configurable window.
- Face search against stored alert snapshots.
- Simple admin login with signed, expiring bearer tokens.
- Futuristic React command center: live camera grid, security posture, alert toasts with
  sound, history, watchlist and face search.
- Settings page for monitoring, match threshold, telemetry refresh, feed mode and alerts.
- Collapsible sidebar navigation that stays hidden until opened.
- Webcam, RTSP, local video and public YouTube Live camera sources.

## Project layout

```text
THEA/
├── app/
│   ├── main.py           # FastAPI app, WebSocket, static frontend serving
│   ├── camera_manager.py # camera ingest + per-camera pipeline workers
│   ├── streams.py        # YouTube Live URL resolution via yt-dlp
│   ├── face_engine.py    # multi-engine catalog, switcher and InsightFace wrapper
│   ├── matching.py       # FAISS/NumPy watchlist index + consecutive-frame logic
│   ├── tracking.py       # lightweight IoU face tracker
│   ├── alerts.py         # snapshot, cooldown, path linking, WebSocket publish
│   ├── watchlist_service.py
│   ├── db.py             # SQLite schema and queries
│   ├── auth.py           # password check and signed tokens
│   └── routers/          # REST endpoints
├── data/                 # generated DB, snapshots, enrolled photos, secret key
├── tests/
├── requirements.txt
├── config/
│   └── cameras.yaml      # camera list (name, RTSP/YouTube URL, location)
├── frontend/
│   ├── src/pages/        # Dashboard, Alerts, Watchlist, Search, Settings, Login
│   └── package.json
├── .env.example
└── README.md
```

## Requirements

- Python **3.12** (pinned to `3.12.11` in `.python-version`; required for prebuilt ML wheels)
- Node.js 18+ and npm
- `ffmpeg` available to OpenCV for RTSP streams (recommended)
- A CPU is enough; an NVIDIA GPU is used automatically if ONNX Runtime sees CUDA

## Quick start

### 1. Configure secrets

```bash
cd THEA
cp .env.example .env
```

Edit `.env` and change at least:

```dotenv
THEA_ADMIN_USERNAME=admin
THEA_ADMIN_PASSWORD=use-a-long-password-here
```

If `THEA_SECRET_KEY` is not set, THEA generates `data/secret.key` on first start.
Changing the secret invalidates existing login tokens.

### 2. Install and start the backend

```bash
cd THEA
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

On the first face detection or enrollment, InsightFace downloads the `buffalo_l` model
(roughly 300 MB) into `~/.insightface`. This is a one-time download.

The API is at `http://localhost:8000`, interactive docs at
`http://localhost:8000/docs`, and health at `http://localhost:8000/api/health`.

### 3. Start the frontend

In a second terminal:

```bash
cd THEA/frontend
npm install
npm run dev
```

Open `http://localhost:5173` and sign in with the credentials from `.env`.

The Vite dev server proxies `/api` and `/ws` to `http://127.0.0.1:8000`. If the backend runs on
another host, copy `frontend/.env.example` to `frontend/.env` and set `VITE_API_BASE`.

For a production-style single-server setup, build the frontend once:

```bash
cd THEA/frontend
npm run build
```

Then the backend serves `frontend/dist` at `http://localhost:8000/` (restart the backend if it
was already running).

### Deploy on Render

Keep the repository's `.python-version` file. Render defaults to Python 3.14, but the pinned
`onnx`/`numpy` builds have no Python 3.14 wheels and pip falls back to slow source builds.

- Build command: `bash build.sh`
- Start command: `bash start.sh`
- Health check path: `/api/health`
- Set `THEA_ADMIN_PASSWORD` and `THEA_SECRET_KEY` in the service environment.

`build.sh` installs the Python packages and builds the React dashboard into `frontend/dist`,
which the backend serves from the same URL. If you keep the old `pip install` build command,
the deployment will serve the API only.

### Development without InsightFace

If you want to work on the UI before installing InsightFace, set:

```dotenv
THEA_FACE_ENGINE=mock
```

Mock mode uses OpenCV's Haar detector and a simple pixel embedding. It is useful for layout and
API testing but **is not accurate enough for real security use**. Leave it as `auto` for real
recognition.

## Add your first camera

### Use the Mac camera for testing

The shipped `config/cameras.yaml` already enables the built-in Mac camera:

```yaml
cameras:
  - id: mac-webcam
    name: Mac Camera
    location: This Mac
    rtsp_url: "0"
    target_fps: 4
    width: 1280
    height: 720
    enabled: true
```

macOS may ask for camera permission the first time. If the feed stays offline, open
**System Settings → Privacy & Security → Camera** and allow the terminal/IDE process that runs
the backend (Terminal, iTerm, VS Code, etc.), then restart the backend.

`width` and `height` are optional capture hints. Lowering them (for example to `960x540`)
reduces CPU usage. They work for RTSP streams too when the camera honors them.

### Use an RTSP camera

Edit `config/cameras.yaml`:

```yaml
cameras:
  - id: front-door
    name: Front Door
    location: Main entrance
    rtsp_url: rtsp://username:password@192.168.1.50:554/Streaming/Channels/101
    target_fps: 4
    enabled: true
```

Notes:

- `id` must be unique and contain only letters, numbers, `.`, `_` or `-`.
- `target_fps` controls how often frames are run through face detection, not the camera's
  native frame rate. 3-5 FPS is a good CPU-friendly default. Preview video runs separately at
  `THEA_STREAM_FPS` (30 FPS by default), so detection load does not make the feed choppy.
- `rtsp_url` can also be a local video file path or a webcam index such as `"0"`.
- `width` and `height` are optional capture hints; omit them to use the camera default.
- Keep this file private: RTSP URLs often contain camera credentials.
- Most Hikvision/Dahua/Reolink cameras have an H.264 RTSP sub-stream; prefer it over 4K main
  streams to reduce CPU.

After editing, either restart the backend or click **Reload cameras** on the dashboard. The
reload endpoint is also available at `POST /api/cameras/reload` (authenticated).

If a camera cannot connect, test the URL outside THEA first:

```bash
ffplay -rtsp_transport tcp "rtsp://username:password@192.168.1.50:554/..."
```

THEA sets `OPENCV_FFMPEG_CAPTURE_OPTIONS=rtsp_transport;tcp` by default. Change
`THEA_RTSP_TRANSPORT=udp` if your camera requires UDP.

### Use a public YouTube Live camera

THEA can ingest public YouTube live streams. Add the watch URL to `config/cameras.yaml`:

```yaml
cameras:
  - id: ac-boardwalk
    name: AC Boardwalk Live
    location: Atlantic City Boardwalk
    rtsp_url: "https://www.youtube.com/watch?v=ghB-3979WwM"
    target_fps: 30
    enabled: true
```

At connection time THEA uses `yt-dlp` to resolve the current direct HLS URL, so expired
stream URLs recover automatically on reconnect. Only public streams are supported; private,
members-only or age-restricted videos need YouTube authentication and are not supported.

Cloud and datacenter IPs (including Render) are often asked to "Sign in to confirm you're not a
bot". Pass the cookies of a signed-in YouTube browser session to `yt-dlp`:

1. Sign in to YouTube in a browser and export cookies for `youtube.com` in Netscape format
   (for example with a "cookies.txt" browser extension).
2. On Render, add a **Secret File** named `youtube-cookies.txt` with the exported contents.
3. THEA detects `/etc/secrets/youtube-cookies.txt` automatically. To use another filename,
   set `THEA_YTDLP_COOKIES_FILE` to its absolute path.
4. Redeploy and restart or reload the camera.

For local use, point the same variable at a local cookie file:

```dotenv
THEA_YTDLP_COOKIES_FILE=/absolute/path/to/youtube-cookies.txt
```

Cookie files contain login tokens. Never commit them; `.gitignore` excludes common names.
YouTube cookies expire periodically. If the error says the configured cookies were rejected,
export a fresh cookie file and redeploy. For production reliability, prefer a direct RTSP/HLS
source when one is available.

## Add your first watchlist person

1. Open **Watchlist** in the dashboard.
2. Click **Add person**.
3. Enter a name and choose **1 clear, front-facing photo** with one face.
4. Click **Add to watchlist**.

The backend rejects uploads where no face is detected, auto-resamples the photo, saves it under
`data/watchlist/` and adds the person to the FAISS/NumPy index. You can later rename the
person, add more photos, or delete them from the same page.

Equivalent API call:

```bash
curl -X POST http://localhost:8000/api/watchlist \
  -H "Authorization: Bearer $THEA_TOKEN" \
  -F "name=Alex Morgan" \
  -F "files=@alex.jpg"
```

## How matching works

For every sampled frame:

1. InsightFace detects faces and produces normalized 512-d embeddings.
2. An IoU tracker keeps a track ID for each face across frames.
3. The watchlist index returns the closest person and cosine similarity.
4. A match only counts if similarity is at or above `THEA_MATCH_THRESHOLD`.
5. The same track must match the same person for `THEA_CONSECUTIVE_FRAMES` consecutive
   processed frames (default 3).
6. After confirmation, the alert is suppressed for the same person and camera for
   `THEA_ALERT_COOLDOWN_SECONDS` (default 60).
7. The snapshot and embedding are stored in SQLite, and a WebSocket event is pushed to all
   dashboards.
8. If the same person was seen on a **different** camera within
   `THEA_PATH_WINDOW_SECONDS` (default 120), the alert reuses that trail ID. This is how the
   movement trails are built.

### Face engines

Open **Settings → Face engine** to choose the model used for detection and embeddings. THEA
ships with these profiles:

| Engine | Best for |
| --- | --- |
| `buffalo_l` | Balanced accuracy and speed (default) |
| `buffalo_s` | Lower CPU and memory use |
| `buffalo_sc` | Lower-powered machines |
| `antelopev2` | Difficult angles and higher accuracy at a heavier cost |
| `mock` | Development and UI testing only |

The active engine is stored in SQLite and survives restarts. The first switch to an uncached
model downloads it from the InsightFace model zoo. THEA waits for the model to load, then
re-embeds every saved watchlist photo so the index stays compatible with the new engine.
Historical alert embeddings remain tied to the engine that captured them.

Tune these values in `.env`:

| Variable | Default | Purpose |
| --- | --- | --- |
| `THEA_MATCH_THRESHOLD` | `0.45` | Minimum cosine similarity for a match |
| `THEA_CONSECUTIVE_FRAMES` | `3` | Frames required before confirming |
| `THEA_ALERT_COOLDOWN_SECONDS` | `60` | Suppress repeat alerts for the same person/camera |
| `THEA_PATH_WINDOW_SECONDS` | `120` | Cross-camera trail linking window |
| `THEA_TARGET_FPS` | `4` | Default sampling rate for cameras without `target_fps` |
| `THEA_STREAM_FPS` | `30` | Smooth preview/MJPEG rate; AI detection stays at `target_fps` |
| `THEA_MAX_UPLOAD_MB` | `12` | Maximum size of an uploaded photo |

Raising the threshold reduces false positives but may miss real matches. Start at `0.45`, then
check the alert history and adjust.

## REST API overview

All endpoints except login, health and the docs require a bearer token. Media endpoints
(snapshots, camera streams, watchlist photos) also accept `?token=...` so browser `<img>` tags
can load them.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/api/auth/login` | Get a token |
| `GET` | `/api/auth/me` | Current user |
| `GET` | `/api/health` | Engine, index, camera, alert and monitoring status |
| `GET` | `/api/controls` | Runtime monitoring and match threshold |
| `PATCH` | `/api/controls` | Pause monitoring or adjust the match threshold |
| `GET` | `/api/face-engines` | List face engines and the active model |
| `POST` | `/api/face-engines/{id}/select` | Switch engines and re-index the watchlist |
| `GET` | `/api/cameras` | Camera list and live status |
| `POST` | `/api/cameras/reload` | Re-read `config/cameras.yaml` and restart workers |
| `POST` | `/api/cameras/{id}/reconnect` | Restart a single camera worker |
| `GET` | `/api/cameras/{id}/snapshot` | Latest JPEG frame |
| `GET` | `/api/cameras/{id}/stream` | MJPEG live stream |
| `GET` | `/api/watchlist` | List watchlist people |
| `POST` | `/api/watchlist` | Add a person (multipart: `name`, `files`) |
| `PATCH` | `/api/watchlist/{id}` | Rename a person |
| `DELETE` | `/api/watchlist/{id}` | Remove a person and enrolled photos |
| `POST` | `/api/watchlist/{id}/photos` | Add photos and recompute embedding |
| `GET` | `/api/alerts` | Alert history (`person`, `camera_id`, `date_from`, `date_to`, `limit`, `offset`) |
| `GET` | `/api/alerts/{id}` | One alert |
| `GET` | `/api/alerts/{id}/snapshot` | Alert snapshot |
| `GET` | `/api/alerts/paths` | Recent cross-camera trails |
| `GET` | `/api/alerts/paths/{path_id}` | Ordered events in a trail |
| `POST` | `/api/search/face` | Upload a photo, search stored alert embeddings |
| `WS` | `/ws/alerts?token=...` | Real-time alert events |

## Tests

Backend tests use the mock face engine and do not need InsightFace or FAISS:

```bash
cd THEA
python3 -m pytest -q
```

Frontend build check:

```bash
cd THEA/frontend
npm run build
```

## Security notes

- Change the default password. THEA logs a warning while `admin/admin` is active.
- Keep the dashboard on a trusted LAN or behind a reverse proxy with HTTPS. The built-in
  server uses plain HTTP.
- RTSP credentials are stored in `config/cameras.yaml`; restrict file permissions.
- `data/` contains the SQLite database, face embeddings, snapshots and the generated
  token secret. Back it up securely and do not commit it.
- There is one admin account by design. For multi-user access, put THEA behind an
  authenticated reverse proxy (for example Caddy or nginx with basic auth/OIDC).
- Face embeddings and snapshots are sensitive biometric data. Follow the laws that apply where
  you operate the system.

## Troubleshooting

**Camera shows "Offline" or "Could not open camera stream"**

- Test the RTSP URL with `ffplay` or VLC outside THEA.
- Try the camera's H.264 sub-stream.
- Switch between TCP and UDP with `THEA_RTSP_TRANSPORT`.
- Check that the camera allows enough concurrent connections.

**InsightFace installation fails**

- Use Python 3.12 in the virtual environment (see `.python-version`).
- Make sure a C/C++ build toolchain is available; some InsightFace versions build Cython
  extensions from source.
- As a temporary UI-development fallback, set `THEA_FACE_ENGINE=mock`.

**"Face engine unavailable" in the UI**

- The backend is running without InsightFace or the model failed to download.
- Check the backend log for the exact error. Run `pip install insightface onnxruntime` and
  restart. The first real detection downloads `buffalo_l`.

**FAISS is not available**

- THEA automatically falls back to an exact NumPy cosine search. This is fine for a home or
  office watchlist. Install `faiss-cpu` if you want the FAISS index.

**No face detected during enrollment**

- Use a clear, well-lit, front-facing photo. Avoid sunglasses, heavy blur, or multiple faces.
- InsightFace needs the person's face to be reasonably large in the image.

**High CPU usage**

- Lower each camera's `target_fps` to 2-3.
- Use camera sub-streams instead of 4K main streams.
- Close unused dashboard streams (each MJPEG stream is lightweight, but the backend still
  processes every enabled camera).
- Run the backend on a machine with a GPU and install `onnxruntime-gpu` if available.

**Dashboard does not receive alerts**

- Check the connection indicator in the top bar.
- If you put the frontend behind a different host or reverse proxy, make sure WebSocket
  upgrade headers are forwarded for `/ws/alerts`.
- Verify the token has not expired; sign in again.

## Limitations

- THEA stores **confirmed alert snapshots**, not continuous video recordings. The search page
  searches those stored alert embeddings/snapshots. Add an NVR or recording worker if you need
  full-footage search.
- The tracker is a lightweight IoU tracker intended for sampled frames, not a full re
  identification system.
- Watchlist matching is one averaged embedding per person. Very large watchlists or difficult
  viewing angles may need per-photo embeddings or a stronger re-ID model.
- The built-in auth is a single admin account with bearer tokens, not a full user-management
  system.
