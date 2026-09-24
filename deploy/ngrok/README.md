# ngrok Hosting

This folder starts NextTrack on the Windows development machine for a small
remote user test. Waitress runs Django on `127.0.0.1:8000`; ngrok provides the
public HTTPS address.

## Install

From the repository root in CMD:

```cmd
.\.venv\Scripts\python.exe -m pip install -r requirements-production.txt
ngrok config add-authtoken YOUR_TOKEN
```

The active database must be available at
`backend\db.schema-final.sqlite3`. The hosted settings generate a private
secret in `backend\.nexttrack-secret-key` on first use. Git ignores this file.

## Run

Open the first CMD window and run:

```cmd
deploy\ngrok\start-waitress.cmd
```

Keep it open. Open a second CMD window and run:

```cmd
ngrok http 8000
```

The assigned public address is
`https://breeding-gusty-grower.ngrok-free.dev`. If ngrok assigns a different
domain, set it before starting Waitress:

```cmd
set "NEXTTRACK_PUBLIC_HOST=your-domain.ngrok-free.dev"
deploy\ngrok\start-waitress.cmd
```

Both CMD windows and the computer must remain running during the test.
