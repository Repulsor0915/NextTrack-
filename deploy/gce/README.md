# NextTrack on one Google Compute Engine VM

This deployment profile uses one `e2-micro` VM, Gunicorn, WhiteNoise, and the
SQLite database already imported into `backend/db.sqlite3`. It is intended for
FYP demonstration traffic and small multi-user testing. It is not a
high-availability or horizontally-scaled deployment.

`config.settings_gce` excludes the offline evaluation Django app, so the
`backend/offline_evaluation/` source directory is not needed on this VM. The
public recommendation API and frontend use the imported SQLite catalogue.

Use an absolute database path on the VM's persistent disk, for example
`/opt/nexttrack/backend/db.sqlite3`, and set `NEXTTRACK_ALLOWED_HOSTS` to the
VM external IP (and later the domain name, if one is added).

## GCP resources

Install the Google Cloud CLI, then choose a project and a Free Tier-compatible
region such as `us-central1`:

```powershell
gcloud auth login
gcloud projects list
gcloud config set project YOUR_PROJECT_ID
gcloud services enable compute.googleapis.com
gcloud compute instances create nexttrack-vm `
  --zone=us-central1-a `
  --machine-type=e2-micro `
  --image-family=debian-12 `
  --image-project=debian-cloud `
  --boot-disk-size=30GB `
  --tags=http-server
gcloud compute firewall-rules create nexttrack-allow-http `
  --allow=tcp:80 `
  --target-tags=http-server
```

Free Tier eligibility depends on region, billing account, and monthly usage;
check the current GCP Free Program before creating resources. Set a budget
alert in the Cloud Console. Do not enable a paid service just to follow this
file.

## VM setup outline

SSH into the VM, install Python, Nginx, and Git, and copy the repository and
verified `backend/db.sqlite3`. Debian 12 ships Python 3.11, whereas the pinned
Django 6.1 needs Python 3.12 or newer. On an existing Debian 12 VM, install
Python 3.12 into a separate virtual environment with `uv`:

```bash
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip nginx
sudo useradd --system --create-home --shell /bin/bash nexttrack || true
sudo mkdir -p /opt/nexttrack
sudo chown -R nexttrack:www-data /opt/nexttrack
sudo -H -u nexttrack python3 -m venv /opt/nexttrack/.venv
sudo -H -u nexttrack /opt/nexttrack/.venv/bin/pip install uv
sudo -H -u nexttrack /opt/nexttrack/.venv/bin/uv venv --python 3.12 /opt/nexttrack/.venv312
sudo -H -u nexttrack /opt/nexttrack/.venv/bin/uv pip install --python /opt/nexttrack/.venv312/bin/python -r /opt/nexttrack/requirements-production.txt
/opt/nexttrack/.venv312/bin/python --version
/opt/nexttrack/.venv312/bin/python -m django --version
```

Keep the existing Python 3.11 environment until the 3.12 environment and
application start successfully. The supplied systemd service points to
`/opt/nexttrack/.venv312/bin/gunicorn`.

From the local machine, the application files and the already verified SQLite
database can be copied with:

```powershell
gcloud compute scp --recurse backend frontend requirements.txt requirements-production.txt deploy nexttrack-vm:/tmp/nexttrack-upload --zone=us-central1-a
gcloud compute scp backend/db.sqlite3 nexttrack-vm:/tmp/db.sqlite3 --zone=us-central1-a
```

Then, on the VM, move the upload into `/opt/nexttrack`, set ownership, and
create `/etc/nexttrack.env` from `deploy/gce/env.example`. Generate a secret
on the VM rather than putting the placeholder into production:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(50))'
sudo install -o nexttrack -g www-data -m 0640 /tmp/db.sqlite3 /opt/nexttrack/backend/db.sqlite3
sudo chown -R nexttrack:www-data /opt/nexttrack
sudo chown root:nexttrack /etc/nexttrack.env
sudo chmod 640 /etc/nexttrack.env
```

Load the environment variables from `/etc/nexttrack.env` before running
management commands. As the application user:

```bash
sudo -u nexttrack bash -c 'set -a; source /etc/nexttrack.env; set +a; cd /opt/nexttrack; .venv312/bin/python backend/manage.py migrate; .venv312/bin/python backend/manage.py collectstatic --noinput; .venv312/bin/python backend/manage.py check --deploy; .venv312/bin/python backend/manage.py catalogue_status'
```

Create `/etc/nexttrack.env` from `env.example`, then install the supplied
systemd and Nginx templates. The service binds Gunicorn to `127.0.0.1:8000`;
Nginx exposes port 80 and serves `/static/` from `backend/staticfiles/`.

```bash
sudo install -o root -g root -m 0644 deploy/gce/nexttrack-gunicorn.service /etc/systemd/system/nexttrack.service
sudo install -o root -g root -m 0644 deploy/gce/nexttrack-nginx.conf /etc/nginx/sites-available/nexttrack
sudo ln -sf /etc/nginx/sites-available/nexttrack /etc/nginx/sites-enabled/nexttrack
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl daemon-reload
sudo systemctl enable --now nexttrack
sudo systemctl restart nginx
```

After starting the service, test:

```bash
curl http://VM_EXTERNAL_IP/health/
curl http://VM_EXTERNAL_IP/api/v1/catalogue/
```

The catalogue endpoint must report
`spotify-tracks-zenodo-2024-merged-v1` and `186684` records.

## Limitations

SQLite is persistent on this VM but is not suitable for multiple application
instances or heavy concurrent writes. The suggestion endpoint and admin writes
should be treated as low-volume operations. Keep an offline backup of the DB
and processed catalogue. Do not expose Django DEBUG or the admin without a
strong password and HTTPS.
