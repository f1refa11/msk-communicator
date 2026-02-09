# msk-communicator

Lightweight Microdot + Jinja2 web app for step-by-step tutorials with user accounts, session-based auth, and per-tutorial assets (HTML, images, CSS, video).

## What it does
- Serves a catalog of tutorials (`/tutorials`) split by level (basic/advanced) from `templates/tutorials/<slug>/`.
- Renders individual steps (`1.tmpl`, `1.html`, etc.) inside a common viewer shell.
- Delivers per-tutorial static assets (CSS, images, video) via `/tutorials-assets/<slug>/<path>` with byte-range support for media.
- Stores users in SQLite (`database.db`) with SHA-256 password hashing and avatar selection.

## Quick start (local)
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install bcrypt jinja2 microdot pyjwt
set SESSION_SECRET=change-me  # Windows
export SESSION_SECRET=change-me  # Linux/macOS
python main.py
```
Open http://127.0.0.1:5000 in a browser.

## Deployment on Windows (server)
1) Prereqs: Windows Server 2019/2022, Python 3.12+, and optionally NSSM to run as a service.  
2) Clone/copy the project to a path without spaces, e.g. `C:\msk-communicator`.  
3) Create a virtual environment and install deps:
   ```cmd
   cd C:\msk-communicator
   py -3.12 -m venv .venv
   .venv\Scripts\activate
   pip install bcrypt jinja2 microdot pyjwt
   ```
4) Configure secrets (PowerShell example):
   ```powershell
   setx SESSION_SECRET "your-strong-secret"
   ```
5) Run the app (foreground):
   ```cmd
   .venv\Scripts\python main.py
   ```
6) Optional: run as Windows service with NSSM  
   ```cmd
   nssm install msk-communicator "C:\msk-communicator\.venv\Scripts\python.exe" "C:\msk-communicator\main.py"
   nssm set msk-communicator AppDirectory "C:\msk-communicator"
   nssm start msk-communicator
   ```

## Deployment on Linux (server)
Example for Ubuntu/Debian. Adjust paths/users to your policy.

1) Prereqs:
   ```bash
   sudo apt update
   sudo apt install -y python3.12 python3.12-venv git
   ```
2) Create an app user and fetch code:
   ```bash
   sudo useradd -r -m -d /opt/msk-communicator -s /bin/bash msk
   sudo -u msk git clone /path/to/repo /opt/msk-communicator
   ```
3) Setup venv and dependencies:
   ```bash
   sudo -u msk python3.12 -m venv /opt/msk-communicator/.venv
   sudo -u msk /opt/msk-communicator/.venv/bin/pip install bcrypt jinja2 microdot pyjwt
   ```
4) Configure environment:
   ```bash
   echo "SESSION_SECRET=change-me" | sudo tee /opt/msk-communicator/.env
   ```
5) Systemd service (`/etc/systemd/system/msk-communicator.service`):
   ```
   [Unit]
   Description=MSK Communicator
   After=network.target

   [Service]
   User=msk
   WorkingDirectory=/opt/msk-communicator
   EnvironmentFile=/opt/msk-communicator/.env
   ExecStart=/opt/msk-communicator/.venv/bin/python main.py
   Restart=on-failure

   [Install]
   WantedBy=multi-user.target
   ```
   Enable and start:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now msk-communicator
   ```
6) Reverse proxy (optional)  
   Point Nginx/Apache to `http://127.0.0.1:5000`, add TLS, and allow large uploads if you serve big videos.

## Adding tutorials
- Create `templates/tutorials/<slug>/`.
- Add `meta.json` with `title`, `description`, and `level` (`basic` or `advanced`).
- Add step files: `1.tmpl`/`1.html`, `2.tmpl`, etc. They are auto-sorted numerically.
- Place assets (CSS, images, video) alongside and reference them as `/tutorials-assets/<slug>/file.ext`.

## Environment variables
- `SESSION_SECRET` – secret key for sessions (set in production).

## Ports and data
- Default port: 5000 (Microdot default). Use a reverse proxy to expose 80/443.
- Data: SQLite file `database.db` in the project root.
