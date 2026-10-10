#!/usr/bin/env sh
# Creates the three .env files for the live server, with fresh secrets (docs/DEPLOYMENT.md section 3).
#
#   sh scripts/deploy/new-env.sh knowbuddy.example.com
#
# Run once, on the server, from the repository folder. It never overwrites an existing
# .env and never prints a secret. Afterwards, fill in LLM_API_KEY and the sign-in apps'
# client IDs and secrets in backend/.env (section 4).
set -eu

ADDRESS="${1:-}"
case "$ADDRESS" in
  "" | http://* | https://* | */*)
    echo "Usage: sh scripts/deploy/new-env.sh <domain>   (just the name, e.g. knowbuddy.example.com)" >&2
    exit 2 ;;
esac

cd "$(dirname "$0")/../.."
for f in .env backend/.env frontend/.env; do
  if [ -e "$f" ]; then
    echo "Refusing to continue: $f already exists. Move it away first if you really mean to replace it." >&2
    exit 1
  fi
done
command -v openssl >/dev/null || { echo "openssl is required" >&2; exit 1; }

secret() { openssl rand -base64 48 | tr -dc 'A-Za-z0-9' | cut -c1-40; }
# Fernet key: 32 random bytes, URL-safe base64 with padding.
fernet_key() { openssl rand -base64 32 | tr '+/' '-_'; }

URL="https://$ADDRESS"
umask 077  # the files hold secrets: readable by their owner only

sed -e "s|^APP_ENV=.*|APP_ENV=production|" \
    -e "s|^APP_URL=.*|APP_URL=$URL|" \
    -e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$(secret)|" \
    -e "s|^APP_DB_PASSWORD=.*|APP_DB_PASSWORD=$(secret)|" \
    backend/.env.example > backend/.env
{
  echo ""
  echo "# Set by scripts/deploy/new-env.sh"
  echo "FRONTEND_URL=$URL"
  echo "TOKEN_ENCRYPTION_KEY=$(fernet_key)"
} >> backend/.env

sed -e "s|^BACKEND_LOCAL_URL=.*|BACKEND_LOCAL_URL=$URL|" frontend/.env.example > frontend/.env

printf 'SITE_ADDRESS=%s\n' "$ADDRESS" > .env

echo "Created .env, backend/.env and frontend/.env for $URL (secrets not shown)."
echo "Next: put LLM_API_KEY and the sign-in apps' IDs and secrets in backend/.env, then run:"
echo "  docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d"
