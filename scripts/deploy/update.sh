#!/usr/bin/env sh
# Updates the live server to the latest main and rebuilds (docs/DEPLOYMENT.md section 5).
#
#   sh scripts/deploy/update.sh
#
# Run on the server as the `ubuntu` user. GitHub Actions runs it after every merge to main,
# through an SSH key that can run nothing else (docs/DEPLOYMENT.md section 8). Running it by
# hand is safe too. Everything is inside main() so the shell has read the whole script before
# `git merge` can replace this file.
set -eu

main() {
  cd "$(dirname "$0")/../.."
  compose() { docker compose -f docker-compose.yml -f docker-compose.prod.yml "$@"; }

  # One deploy at a time, whether started by GitHub or by hand.
  exec 9>/tmp/knowbuddy-deploy.lock
  if ! flock -n 9; then
    echo "Another deploy is running. Try again when it finishes." >&2
    exit 1
  fi

  echo "== Fetching main"
  git fetch --quiet origin main
  git checkout --quiet main
  if ! git merge --ff-only --quiet origin/main; then
    echo "Refusing to deploy: this server's main has changes that are not on GitHub. Fix it by hand." >&2
    exit 1
  fi
  echo "Now at: $(git log --oneline -1)"

  echo "== Rebuilding and restarting what changed"
  compose up --build -d --remove-orphans

  echo "== Removing unused images"
  docker image prune -f >/dev/null

  echo "== Waiting for the backend to report healthy"
  health=""
  i=0
  while [ "$i" -lt 36 ]; do
    health=$(docker inspect --format '{{.State.Health.Status}}' "$(compose ps -q backend)" 2>/dev/null || true)
    [ "$health" = "healthy" ] && break
    i=$((i + 1))
    sleep 5
  done
  compose ps
  if [ "$health" != "healthy" ]; then
    echo "Deploy finished but the backend is not healthy (${health:-unknown}). See: docker compose logs backend" >&2
    exit 1
  fi
  echo "== Deployed $(git log --oneline -1)"
}

main "$@"
