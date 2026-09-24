# Google Compute Engine Deployment

This directory contains the files needed to run NextTrack on one Google
Compute Engine VM with Gunicorn, Nginx, WhiteNoise, and SQLite. The profile is
intended for an FYP demonstration and small user-testing workload.

## Files

| File | Purpose |
| --- | --- |
| `env.example` | Lists the environment variables required by `config.settings_gce`. |
| `nexttrack-gunicorn.service` | Runs one Gunicorn worker with two threads through systemd. |
| `nexttrack-nginx.conf` | Proxies application requests to Gunicorn and serves collected static files. |

The service expects the project at `/opt/nexttrack`, the Python environment at
`/opt/nexttrack/.venv312`, and environment variables in
`/etc/nexttrack.env`.

## VM outline

The example profile uses Debian 12 and an `e2-micro` VM in `us-central1-a`:

```powershell
gcloud config set project YOUR_PROJECT_ID
gcloud services enable compute.googleapis.com

gcloud compute instances create nexttrack-vm `
  --zone=us-central1-a `
  --machine-type=e2-micro `
  --image-family=debian-12 `
  --image-project=debian-cloud `
  --boot-disk-size=30GB `
  --boot-disk-type=pd-standard `
  --tags=http-server

gcloud compute firewall-rules create nexttrack-allow-http `
  --network=default `
  --allow=tcp:80 `
  --target-tags=http-server
```

Check current [Google Cloud Free Program](https://cloud.google.com/free/docs/free-cloud-features)
conditions before creating resources. The full 964,224-track catalogue can be
slow on `e2-micro`; use a larger VM if the process exceeds its memory or
timeout limits.

## Upload

From the repository root, archive the committed source and upload it with the
current database:

```powershell
git archive --format=zip --output nexttrack-release.zip HEAD

gcloud compute scp nexttrack-release.zip `
  nexttrack-vm:/tmp/nexttrack-release.zip `
  --zone=us-central1-a

gcloud compute scp backend\db.schema-final.sqlite3 `
  nexttrack-vm:/tmp/db.schema-final.sqlite3 `
  --zone=us-central1-a

gcloud compute ssh nexttrack-vm --zone=us-central1-a
```

`git archive` excludes ignored local databases, virtual environments, and
cache files.

## VM setup

On the VM, install the application and database:

```bash
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip nginx unzip
id -u nexttrack >/dev/null 2>&1 || \
  sudo useradd --system --create-home --shell /bin/bash nexttrack

sudo install -d -o nexttrack -g www-data /opt/nexttrack
sudo unzip -q /tmp/nexttrack-release.zip -d /opt/nexttrack
sudo install -o nexttrack -g www-data -m 0640 \
  /tmp/db.schema-final.sqlite3 \
  /opt/nexttrack/backend/db.sqlite3
sudo chown -R nexttrack:www-data /opt/nexttrack
```

The deployed filename is `db.sqlite3`, but it contains the same database as the
local `db.schema-final.sqlite3`.

Create the Python 3.12 environment and install production dependencies:

```bash
sudo -u nexttrack python3 -m venv /opt/nexttrack/.bootstrap-venv
sudo -u nexttrack /opt/nexttrack/.bootstrap-venv/bin/pip install uv
sudo -H -u nexttrack \
  /opt/nexttrack/.bootstrap-venv/bin/uv python install 3.12
sudo -H -u nexttrack \
  /opt/nexttrack/.bootstrap-venv/bin/uv venv \
  --python 3.12 /opt/nexttrack/.venv312
sudo -H -u nexttrack \
  /opt/nexttrack/.bootstrap-venv/bin/uv pip install \
  --python /opt/nexttrack/.venv312/bin/python \
  -r /opt/nexttrack/requirements-production.txt
```

## Environment

Generate a secret and install the environment template:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(50))'
sudo install -o root -g nexttrack -m 0640 \
  /opt/nexttrack/deploy/gce/env.example /etc/nexttrack.env
sudo nano /etc/nexttrack.env
```

Replace the placeholders in `/etc/nexttrack.env`:

```dotenv
DJANGO_SETTINGS_MODULE=config.settings_gce
NEXTTRACK_SECRET_KEY=GENERATED_SECRET
NEXTTRACK_ALLOWED_HOSTS=VM_EXTERNAL_IP
NEXTTRACK_DB_PATH=/opt/nexttrack/backend/db.sqlite3
NEXTTRACK_HTTPS=0
NEXTTRACK_CSRF_TRUSTED_ORIGINS=
```

## Django and services

Prepare Django and confirm the catalogue:

```bash
sudo -u nexttrack bash -c '
  set -a; source /etc/nexttrack.env; set +a
  cd /opt/nexttrack
  .venv312/bin/python backend/manage.py migrate
  .venv312/bin/python backend/manage.py collectstatic --noinput
  .venv312/bin/python backend/manage.py check --deploy
  .venv312/bin/python backend/manage.py catalogue_status
'
```

The status should report `spotify-merged-v2`, 964,224 tracks and features, and
`state_consistent: true`.

Create the superuser:

```bash
sudo -u nexttrack bash -c '
  set -a; source /etc/nexttrack.env; set +a
  cd /opt/nexttrack
  .venv312/bin/python backend/manage.py createsuperuser
'
```

Install and start the supplied service files:

```bash
sudo install -m 0644 /opt/nexttrack/deploy/gce/nexttrack-gunicorn.service \
  /etc/systemd/system/nexttrack.service
sudo install -m 0644 /opt/nexttrack/deploy/gce/nexttrack-nginx.conf \
  /etc/nginx/sites-available/nexttrack
sudo ln -sf /etc/nginx/sites-available/nexttrack \
  /etc/nginx/sites-enabled/nexttrack
sudo rm -f /etc/nginx/sites-enabled/default

sudo nginx -t
sudo systemctl daemon-reload
sudo systemctl enable --now nexttrack nginx
```

## Verify and maintain

Check the deployment:

```bash
curl --fail http://127.0.0.1/health/
curl --fail http://127.0.0.1/api/v1/catalogue/
sudo systemctl status nexttrack --no-pager
sudo journalctl -u nexttrack -n 100 --no-pager
```

Then check `/`, `/analytics/`, `/admin/`, catalogue search, and one
recommendation through the external IP.

Before replacing code or the database, stop the service and copy
`/opt/nexttrack/backend/db.sqlite3` to a separate backup location. After a code
update, reinstall requirements if needed, then run `migrate`, `collectstatic`,
`check --deploy`, and `catalogue_status` before restarting the service.

The supplied Nginx file configures HTTP only. Add a domain and TLS certificate,
then set `NEXTTRACK_HTTPS=1` and `NEXTTRACK_CSRF_TRUSTED_ORIGINS` before public
user testing. SQLite and LocMem cache remain suitable only for one small VM and
low write volume.
