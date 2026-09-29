#!/usr/bin/env bash
# Deploy one release tarball to the team VM: production (vk-zhkh) first, then preview (vk-zhkh-preview).
# Runs ON the VM as the user that owns /srv/team/vk-hackathon and can use Docker. Earlier releases were
# rolled out as `artem`; from another login use: sudo -u artem bash deploy_vm_release.sh check|deploy ...
#
#   deploy_vm_release.sh check  /tmp/release-XXXXXXX.zip|.tar.gz <40-char release SHA>   # nothing is restarted
#   deploy_vm_release.sh deploy /tmp/release-XXXXXXX.zip|.tar.gz <40-char release SHA>
#
# Follows docs/deployment.md: a clean release directory next to the old ones, private backups
# (pg_dump + restore test + source documents archive), one-off migration, then only api/worker/web
# are recreated. Old release directories stay as rollback points. The shared Nginx, runtime env
# files and volumes are never touched; secrets are never printed; no `down -v`, no prune.
set -euo pipefail

MODE="${1:-}"; TARBALL="${2:-}"; SHA="${3:-}"
BASE="${VM_BASE:-/srv/team/vk-hackathon}"
INGRESS="${VM_INGRESS:-http://10.203.77.10:8080}"

say() { printf '\n== %s\n' "$*"; }
die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }
[[ "$MODE" == check || "$MODE" == deploy ]] || die "usage: $0 check|deploy /path/release.tar.gz <40-char SHA>"
[[ -f "$TARBALL" ]] || die "release tarball not found: $TARBALL"
[[ "$SHA" =~ ^[0-9a-f]{40}$ ]] || die "the third argument must be the full 40-character release SHA"
SHORT="${SHA:0:7}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
PROD_DIR="$BASE/deploy-release-$SHORT"
PREVIEW_DIR="$BASE/preview-release-$SHORT"

compose_prod() { (cd "$PROD_DIR" && docker compose --env-file ../runtime/app.env -p vk-zhkh -f compose.yaml -f compose.vm.yaml "$@"); }
compose_preview() { (cd "$PREVIEW_DIR" && docker compose --env-file ../runtime-preview/app.env -p vk-zhkh-preview -f compose.yaml -f compose.preview.vm.yaml "$@"); }

OLD_PROD_DIR=""; OLD_PREVIEW_DIR=""; ROLLOUT_STARTED=0
on_exit() {
  local code=$?
  (( code == 0 )) && return 0
  printf '\nSTOPPED (exit %s). Services that were already running were not removed.\n' "$code" >&2
  if (( ROLLOUT_STARTED )); then
    printf 'Rollback (this release adds no database migration, so the previous code runs on the same database):\n' >&2
    [[ -n "$OLD_PROD_DIR" && -d "$OLD_PROD_DIR" ]] && printf '  cd "%s" && docker compose --env-file ../runtime/app.env -p vk-zhkh -f compose.yaml -f compose.vm.yaml up -d --build --no-deps api worker web\n' "$OLD_PROD_DIR" >&2
    [[ -n "$OLD_PREVIEW_DIR" && -d "$OLD_PREVIEW_DIR" ]] && printf '  cd "%s" && docker compose --env-file ../runtime-preview/app.env -p vk-zhkh-preview -f compose.yaml -f compose.preview.vm.yaml up -d --build --no-deps api worker web\n' "$OLD_PREVIEW_DIR" >&2
  fi
  return "$code"
}
trap on_exit EXIT

http_code() { curl -sS -o /dev/null -w '%{http_code}' --max-time 15 "$@" || true; }
expect_code() { # expect_code <expected> <label> curl-args...
  local expected="$1" label="$2"; shift 2
  local got; got="$(http_code "$@")"
  printf '  %-46s %s\n' "$label" "$got"
  [[ "$got" == "$expected" ]] || die "$label: expected HTTP $expected, got $got"
}
wait_ready() { # wait_ready <url>
  local code=000
  for _ in $(seq 1 60); do
    code="$(http_code "$1")"
    [[ "$code" == 200 ]] && return 0
    sleep 3
  done
  die "readiness did not reach HTTP 200 ($1 gave $code)"
}
running_dir() { # working directory of the running compose project, from container labels
  local id; id="$(docker ps -q --filter "label=com.docker.compose.project=$1" --filter 'label=com.docker.compose.service=api' | head -1)"
  [[ -n "$id" ]] && docker inspect --format '{{ index .Config.Labels "com.docker.compose.project.working_dir" }}' "$id" || true
}

say "Preflight (read-only)"
id -un; hostname; df -h / | tail -1; free -h | sed -n 2p
[[ -d "$BASE" && -w "$BASE" ]] || die "$BASE is missing or not writable for $(id -un); run as the owner (earlier releases: artem), e.g. sudo -u artem bash $0 ..."
for runtime in runtime runtime-preview; do
  [[ -d "$BASE/$runtime" && -w "$BASE/$runtime" ]] || die "$BASE/$runtime is missing or not writable for $(id -un) (backups go there); run as the owner, e.g. sudo -u artem bash $0 ..."
done
docker info >/dev/null 2>&1 || die "this user cannot use Docker"
for env_file in "$BASE/runtime/app.env" "$BASE/runtime-preview/app.env"; do
  [[ -f "$env_file" && -r "$env_file" ]] || die "private env file $env_file is missing or not readable for $(id -un); run as the owner, e.g. sudo -u artem bash $0 ..."
  printf '  %s mode %s\n' "$env_file" "$(stat -c %a "$env_file")"
done
docker network inspect vk-zhkh-edge vk-zhkh-preview-edge >/dev/null 2>&1 || die "external networks vk-zhkh-edge / vk-zhkh-preview-edge are missing"
docker compose ls | sed -n '1,10p'
OLD_PROD_DIR="$(running_dir vk-zhkh)"; OLD_PREVIEW_DIR="$(running_dir vk-zhkh-preview)"
printf '  running production from : %s\n  running preview from    : %s\n' "${OLD_PROD_DIR:-none}" "${OLD_PREVIEW_DIR:-none}"
expect_code 200 "shared /team/ before" "$INGRESS/team/"
printf '  %-46s %s\n' "production ready before" "$(http_code "$INGRESS/team/zhkh/health/ready")"
printf '  %-46s %s\n' "preview ready before" "$(http_code "$INGRESS/team/zhkh-preview/health/ready")"

extract() { # extract <dir>
  if [[ -e "$1" ]]; then
    [[ "$(cat "$1/RELEASE_SHA" 2>/dev/null || true)" == "$SHA" ]] || die "$1 exists and is not this release"
    echo "  $1 already holds this release"
    return
  fi
  mkdir "$1"
  case "$TARBALL" in
    *.zip) if command -v unzip >/dev/null 2>&1; then unzip -q "$TARBALL" -d "$1"; else python3 -m zipfile -e "$TARBALL" "$1"; fi ;;
    *) tar -xzf "$TARBALL" -C "$1" ;;
  esac
  find "$1" -type f -exec chmod a+r {} +   # the image user `app` must be able to read the sources (docs/deployment.md)
  find "$1" -type d -exec chmod a+rx {} +
  printf '%s\n' "$SHA" > "$1/RELEASE_SHA"
  echo "  created $1"
}
say "Release directories for $SHORT"
extract "$PROD_DIR"; extract "$PREVIEW_DIR"

say "Compose configuration (quiet: secrets are not printed)"
compose_prod config --quiet && echo "  production config ok"
compose_preview config --quiet && echo "  preview config ok"

if [[ "$MODE" == check ]]; then
  say "Check finished: no service was restarted. Run again with 'deploy' to roll out."
  exit 0
fi

backup() { # backup <production|preview> <runtime dir name> <project> <compose function>
  local label="$1" runtime="$2" project="$3" compose="$4"
  local dir="$BASE/$runtime/backup/predeploy-$SHORT-$STAMP" test_db="zhkh_restore_${STAMP}"
  (
    umask 077
    mkdir -p "$dir"
    "$compose" exec -T db pg_dump -U zhkh -d zhkh -Fc > "$dir/zhkh.dump"
    [[ -s "$dir/zhkh.dump" ]] || die "$label dump is empty"
    "$compose" exec -T db pg_restore --list < "$dir/zhkh.dump" >/dev/null
    local api_image; api_image="$(docker inspect --format '{{.Image}}' "$(docker ps -q --filter "label=com.docker.compose.project=$project" --filter 'label=com.docker.compose.service=api' | head -1)")"
    docker run --rm --network none -v "${project}_source_documents:/data:ro" --entrypoint tar "$api_image" czf - -C /data . > "$dir/sources.tar.gz"
    tar -tzf "$dir/sources.tar.gz" >/dev/null
    "$compose" exec -T db createdb -U zhkh "$test_db"
    "$compose" exec -T db pg_restore -U zhkh -d "$test_db" --no-owner --no-acl < "$dir/zhkh.dump"
    printf '  %s backup %s: restored revision %s\n' "$label" "$dir" "$("$compose" exec -T db psql -U zhkh -d "$test_db" -Atqc 'SELECT version_num FROM alembic_version')"
    "$compose" exec -T db dropdb -U zhkh "$test_db"   # only the temporary database created above
  )
}

roll_out() { # roll_out <label> <compose function> <url prefix> <expected mode>
  local label="$1" compose="$2" url="$3" mode="$4"
  say "$label: build, migrate, recreate api/worker/web"
  ROLLOUT_STARTED=1
  "$compose" build
  "$compose" run --rm --no-deps migrate
  "$compose" up -d --no-deps api worker web
  wait_ready "$INGRESS$url/health/ready"
  "$compose" ps
  printf '  alembic revision: %s\n' "$("$compose" exec -T db psql -U zhkh -d zhkh -Atqc 'SELECT version_num FROM alembic_version')"
  local meta; meta="$(curl -sS --max-time 15 "$INGRESS$url/api/v1/meta" | tr -d ' ')"
  [[ "$meta" == *"\"mode\":\"$mode\""* ]] || die "$label: meta does not report mode=$mode"
  expect_code 200 "$label UI" "$INGRESS$url/"
  expect_code 200 "$label deep link" "$INGRESS$url/history"
  local asset; asset="$(curl -sS --max-time 15 "$INGRESS$url/" | grep -o "$url/assets/[^\"' ]*\.js" | head -1)"
  [[ -n "$asset" ]] || die "$label: the page does not reference a JS asset"
  expect_code 200 "$label JS asset" "$INGRESS$asset"
  expect_code 404 "$label missing asset" "$INGRESS$url/assets/missing-$STAMP.js"
  expect_code 403 "$label webhook without secret" -X POST "$INGRESS$url/integrations/max/webhook"
}

say "Backups before the rollout (private, mode 0600, stay on the VM)"
backup production runtime vk-zhkh compose_prod
backup preview runtime-preview vk-zhkh-preview compose_preview
mkdir -p "$BASE/runtime/backup"
printf 'production=%s\npreview=%s\nnew=%s\n' "${OLD_PROD_DIR:-none}" "${OLD_PREVIEW_DIR:-none}" "$SHA" > "$BASE/runtime/backup/previous-release-$STAMP.txt"

roll_out production compose_prod /team/zhkh production
roll_out preview compose_preview /team/zhkh-preview preview

say "Shared ingress after the rollout"
expect_code 200 "shared /team/" "$INGRESS/team/"
expect_code 200 "shared /healthz" "$INGRESS/healthz"
printf '\nDONE: production and preview run release %s.\nPrevious release directories were left in place for rollback:\n  %s\n  %s\n' "$SHA" "${OLD_PROD_DIR:-none}" "${OLD_PREVIEW_DIR:-none}"
