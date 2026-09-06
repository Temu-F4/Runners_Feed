# Mac mini development setup

This guide creates a fresh Apple Silicon development environment. Source code
moves through GitHub; dependencies, images, volumes, and secrets do not.

## 1. Prerequisites

Install Git and Docker Desktop, start Docker Desktop, and verify:

```bash
uname -m
git --version
docker version
docker compose version
```

Do not copy `node_modules`, `.next`, Python virtual environments, Docker images,
or Docker volumes from another Mac. Rebuild them locally.

## 2. GitHub SSH key

Create a device-specific key. Do not copy the private key from another Mac.

```bash
mkdir -p ~/.ssh
chmod 700 ~/.ssh
ssh-keygen -t ed25519 -C "acesport0316@gmail.com" -f ~/.ssh/github-temu-f4
chmod 600 ~/.ssh/github-temu-f4
chmod 644 ~/.ssh/github-temu-f4.pub
```

Add the contents of `~/.ssh/github-temu-f4.pub` to GitHub under **Settings >
SSH and GPG keys**, then add this block to `~/.ssh/config` without replacing
existing entries:

```sshconfig
Host github.com
    HostName github.com
    User git
    IdentityFile ~/.ssh/github-temu-f4
    IdentitiesOnly yes
    AddKeysToAgent yes
    UseKeychain yes
```

Protect and test the configuration:

```bash
chmod 600 ~/.ssh/config
ssh-add --apple-use-keychain ~/.ssh/github-temu-f4
ssh -T git@github.com
```

GitHub reports a successful authentication while also stating that it does not
provide shell access. That is expected.

## 3. Clone the repository

```bash
git clone git@github.com:Temu-F4/Runners_Feed.git ~/OCI
cd ~/OCI
git fetch --all --prune
git switch feat/coach-pipeline-migration
git pull --ff-only
git status -sb
git log -1 --oneline --decorate
```

Set the Git identity if it is not already configured:

```bash
git config --global user.name "jimmypak"
git config --global user.email "acesport0316@gmail.com"
```

## 4. Local secrets

Create `.env` from the tracked template and fill it using a password manager,
AirDrop, or direct entry. Never commit or paste secret values into chat.

```bash
cp .env.example .env
mkdir -p runtime/oci runtime/models runtime/run
```

The default Mac override mounts `./runtime/oci` at `/.oci`. Basic health checks
do not require OCI credentials. Object Storage operations do. For those, either
place a valid `config` and signing key under `runtime/oci`, or set this in `.env`
to an absolute directory outside the repository:

```dotenv
RUNNERS_FEED_OCI_CONFIG_DIR=/Users/YOUR_USERNAME/.oci
```

The `key_file` entry in the OCI config must resolve inside the mounted `/.oci`
directory. Do not commit the OCI config or signing key.

Recommended local value:

```dotenv
COACH_DEVICE=cpu
RUNNERS_FEED_RUNTIME_DIR=./runtime
```

`OCI_BACKUP_BUCKET` is required only when using the backup profile.

## 5. Validate the Compose model

The production Compose file contains Linux host mounts used by OCI. Always use
the Mac override locally and start only the named development services.

```bash
docker compose \
  -f compose.yaml \
  -f compose.coach.yaml \
  -f compose.mac.yaml \
  config --services
```

Do not start these OCI/Linux-specific services on Docker Desktop:

- `web` and `certbot` (production TLS mounts)
- `cadvisor`
- `node-exporter`
- `host-metrics-collector`

## 6. Build and test

Build the frontend from its lockfile:

```bash
cd ~/OCI/frontend
npm ci
npm run build
cd ~/OCI
```

Build the core Docker images:

```bash
docker compose \
  -f compose.yaml \
  -f compose.coach.yaml \
  -f compose.mac.yaml \
  build api frontend coach-worker
```

Start only the core services first:

```bash
docker compose \
  -f compose.yaml \
  -f compose.coach.yaml \
  -f compose.mac.yaml \
  up -d postgres redis api frontend
```

Verify them:

```bash
docker compose \
  -f compose.yaml \
  -f compose.coach.yaml \
  -f compose.mac.yaml \
  ps
curl -fsS http://127.0.0.1:8000/health
curl -I http://127.0.0.1:3000
```

Start `coach-worker` and `maintenance` only after OCI credentials and required
model assets are available:

```bash
docker compose \
  -f compose.yaml \
  -f compose.coach.yaml \
  -f compose.mac.yaml \
  --profile coach up -d coach-worker maintenance
```

The Mac coach path is CPU-only. CUDA GPU A/B work belongs on RunPod or another
CUDA host.

## 7. OCI server SSH access

Create a separate key on the Mac mini:

```bash
ssh-keygen -t ed25519 -C "macmini-runners-feed-oci" -f ~/.ssh/runners-feed-oci.key
chmod 600 ~/.ssh/runners-feed-oci.key
chmod 644 ~/.ssh/runners-feed-oci.key.pub
```

Have an already-authorized machine add the public key to the OCI server's
`~ubuntu/.ssh/authorized_keys`. Add this local SSH configuration:

```sshconfig
Host runners-feed-oci
    HostName 140.238.0.197
    User ubuntu
    IdentityFile ~/.ssh/runners-feed-oci.key
    IdentitiesOnly yes
    ServerAliveInterval 60
    ServerAliveCountMax 3
```

Then run a read-only verification:

```bash
ssh -o BatchMode=yes runners-feed-oci \
  'uname -srm; cd /home/ubuntu/runners-feed-poc-deploy && git status -sb && git log -1 --oneline'
```

A GitHub push does not deploy the OCI server. Do not pull, rebuild, or restart
production services without a separate deployment decision.

## 8. Before committing or pushing

```bash
git status -sb
