#!/usr/bin/env bash
# deploy-hetzner-lib.sh — shared helpers for deploying to the Hetzner hosts (theuws-prod, nimad-prod).
#
# Source of truth: ~/Documents/server-mini-development/templates/deploy-hetzner-lib.sh
# Rolled out by /adopt-tooling to <project>/scripts/deploy-hetzner-lib.sh. Do not edit the copy in a project:
# improve the template and re-run /adopt-tooling --update-only.
# Background: ~/Documents/server-mini-development/docs/HOSTING_HETZNER.md
#
# Usage in a project's deploy script (PROJECT = the project root, e.g. resolved from BASH_SOURCE):
#   set -euo pipefail
#   HZ_HOST=theuws-prod
#   HZ_DIR=/srv/apps/<project>            # or /srv/apps/static/<map> for a static site
#   HZ_SRC_DIR="$PROJECT"                 # what hz_export_head exports (default: the git toplevel)
#   source "$PROJECT/scripts/deploy-hetzner-lib.sh"
#   hz_check
#   hz_require_pushed_main                # only ship what is already on origin/<branch>
#   hz_backup
#   src=$(hz_export_head); hz_sync "$src" --exclude=/data/; rm -rf "$src"
#   hz_compose up -d --build
#   hz_wait_http "https://<domain>/api/health" "\"version\":\"$(cat VERSION)\""
#
# Lessons built in (07-11-2026): .env* on the server is never touched (at any depth); rsync never copies the Mac's
# uid/gid and never applies a 700 temp-dir mode to the target; an empty or failed export is never mirrored with
# --delete; the export does not depend on the cwd; only a pushed branch is shipped; a deploy is only reported as
# successful once the live endpoint shows the new version.
#
# Anything in HZ_DIR that exists only on the server (runtime data, uploads, certs, overrides) must be excluded by the
# caller, because hz_sync mirrors the source with --delete.

# Required: HZ_HOST, HZ_DIR. Optional: HZ_OWNER (deploy|root; default = current owner of HZ_DIR),
# HZ_SRC_DIR (default: git toplevel of the cwd), HZ_BRANCH (default main), HZ_KEEP_BACKUPS (default 10),
# HZ_BACKUP_EXCLUDES (space-separated paths relative to HZ_DIR; default "data"), HZ_WAIT_TRIES (default 24, 5 s).

hz_log() { printf '\033[34m[hz]\033[0m %s\n' "$*"; }
hz_die() { printf '\033[31m[hz] %s\033[0m\n' "$*" >&2; exit 1; }

# Run a command on the host. Arguments are quoted, so paths with spaces survive.
hz_ssh() {
    local cmd
    printf -v cmd '%q ' "$@"
    ssh -o ConnectTimeout=10 "$HZ_HOST" "$cmd"
}

hz_check() {
    [[ -n "${HZ_HOST:-}" && -n "${HZ_DIR:-}" ]] || hz_die "HZ_HOST and HZ_DIR must be set"
    [[ "$HZ_DIR" == /srv/apps/* ]] || hz_die "HZ_DIR must be under /srv/apps (got $HZ_DIR)"
    ssh -o ConnectTimeout=5 -o BatchMode=yes "$HZ_HOST" true 2>/dev/null || hz_die "ssh $HZ_HOST failed"
    ssh -o ConnectTimeout=5 -o BatchMode=yes "$HZ_HOST" sudo -n true 2>/dev/null || hz_die "sudo without password fails on $HZ_HOST"
    if [[ -z "${HZ_OWNER:-}" ]]; then
        HZ_OWNER=$(hz_ssh stat -c %U "$HZ_DIR" 2>/dev/null) || hz_die "$HZ_HOST:$HZ_DIR does not exist"
    fi
    [[ "$HZ_OWNER" == deploy || "$HZ_OWNER" == root ]] || hz_die "unexpected owner $HZ_OWNER of $HZ_DIR"
    hz_log "target $HZ_HOST:$HZ_DIR (owner $HZ_OWNER)"
}

# Refuse to ship anything that is not already on the remote release branch. It does not push for you: publishing a
# local commit is a decision, not a side effect of deploying.
hz_require_pushed_main() {
    local branch want="${HZ_BRANCH:-main}"
    branch=$(git rev-parse --abbrev-ref HEAD)
    [[ "$branch" == "$want" ]] || hz_die "deploy only from $want (current: $branch)"
    git fetch -q origin "$want" || hz_die "git fetch origin $want failed"
    [[ "$(git rev-parse HEAD)" == "$(git rev-parse "origin/$want")" ]] \
        || hz_die "HEAD differs from origin/$want: push (or pull) first, then deploy"
    if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
        hz_log "note: uncommitted changes are not shipped by hz_export_head"
    fi
}

# Export the committed HEAD of HZ_SRC_DIR (default: the git toplevel) into a fresh local directory (mode 755) and
# print its path. Independent of the cwd: `git archive HEAD` from a subdirectory would export only that subtree,
# which hz_sync --delete would then mirror over the whole app. REVISION holds the sha. Returns 1 (prints nothing)
# on any failure, so `src=$(hz_export_head)` under set -e stops the deploy.
hz_export_head() {
    local srcdir top prefix tmp
    srcdir="${HZ_SRC_DIR:-$(git rev-parse --show-toplevel)}" || return 1
    top=$(git -C "$srcdir" rev-parse --show-toplevel) || return 1
    prefix=$(git -C "$srcdir" rev-parse --show-prefix) || return 1
    tmp=$(mktemp -d) || return 1
    chmod 755 "$tmp"
    if ! git -C "$top" archive --format=tar "HEAD:${prefix}" | tar -C "$tmp" -xf - \
        || [[ ${PIPESTATUS[0]} -ne 0 ]] || [[ -z "$(ls -A "$tmp")" ]]; then
        rm -rf "$tmp"
        printf '\033[31m[hz] git archive of %s failed or was empty\033[0m\n' "$srcdir" >&2
        return 1
    fi
    git -C "$top" rev-parse --short HEAD > "$tmp/REVISION"
    printf '%s\n' "$tmp"
}

# Tar the current target to /srv/deploy-backups/hz/<path under /srv/apps, / as ->/<timestamp>.tar.gz and keep the
# newest N. The key is the full path, so /srv/apps/x and /srv/apps/static/x (and scripts/deploy.sh's per-site
# folders) never share a folder or prune each other. .env* (any depth) and HZ_BACKUP_EXCLUDES (default: data, live
# database files) stay out: a copy of a running database is not a backup.
hz_backup() {
    local key keep ts dir ex
    key=${HZ_DIR#/srv/apps/}; key=${key//\//-}
    keep=${HZ_KEEP_BACKUPS:-10}
    ts=$(date +%Y%m%d-%H%M%S)
    dir="/srv/deploy-backups/hz/$key"
    local excludes=(--exclude='.env' --exclude='.env.*')
    for ex in ${HZ_BACKUP_EXCLUDES-data}; do excludes+=("--exclude=./$ex"); done
    hz_ssh sudo mkdir -p "$dir"
    hz_ssh sudo tar -czf "$dir/$ts.tar.gz" "${excludes[@]}" -C "$HZ_DIR" . \
        || hz_die "backup of $HZ_DIR failed"
    # Prune in one remote command (a per-file ssh inside a read loop would swallow the loop's stdin).
    ssh -n -o ConnectTimeout=10 "$HZ_HOST" \
        "cd $(printf %q "$dir") && ls -1t -- *.tar.gz | tail -n +$((keep + 1)) | sudo xargs -r rm -f --" \
        || hz_log "note: pruning old backups in $dir failed"
    hz_log "backup $dir/$ts.tar.gz"
}

# rsync SRC/ to HZ_DIR/ with --delete. Extra rsync arguments (excludes) go after SRC.
# - .env and .env.* are excluded at any depth, which also protects them from --delete.
# - an empty source (failed export) is refused: mirroring it with --delete would wipe HZ_DIR.
# - -rlptz instead of -a: never copy the Mac's owner/group. Files land as the owner of HZ_DIR.
# - --chmod keeps everything readable for the web server, whatever the local mode (mktemp gives 700).
hz_sync() {
    local src="$1"; shift
    [[ -d "$src" && "$src" == /* ]] || hz_die "hz_sync needs an absolute source directory (got $src)"
    [[ $(find "$src" -mindepth 1 -maxdepth 1 ! -name REVISION ! -name VERSION | head -2 | wc -l) -ge 1 ]] \
        || hz_die "hz_sync refuses an empty source ($src): --delete would wipe $HZ_DIR"
    local rsync_path="sudo rsync"
    [[ "$HZ_OWNER" == deploy ]] && rsync_path="sudo -u deploy rsync"
    # rsync -p copies the mode of $src itself onto HZ_DIR, and macOS openrsync does not apply --chmod to that top
    # directory: a mktemp dir (700) locked out the web server on 07-11. Make it readable here and enforce it remotely.
    chmod go+rx "$src"
    rsync -rlptz --delete --chmod=Dgo+rx,Fgo+r \
        --exclude='.env' --exclude='.env.*' --exclude='.DS_Store' --exclude='.git/' \
        "$@" --rsync-path="$rsync_path" "$src/" "$HZ_HOST:$HZ_DIR/" \
        || hz_die "rsync to $HZ_HOST:$HZ_DIR failed"
    hz_ssh sudo chmod go+rx "$HZ_DIR" || hz_die "could not make $HZ_DIR readable"
    hz_log "synced $src -> $HZ_DIR"
}

# docker compose in HZ_DIR, as the deploy user (owner of the app directory, member of the docker group).
hz_compose() {
    local cmd
    printf -v cmd '%q ' "$@"
    ssh -o ConnectTimeout=10 "$HZ_HOST" "cd $(printf %q "$HZ_DIR") && sudo -u deploy docker compose $cmd"
}

# Plain docker as the deploy user (exec, tag, inspect, ps).
hz_docker() { hz_ssh sudo -u deploy docker "$@"; }

# Poll URL until it answers 200 and (optionally) the body contains EXPECT. Exit 1 if it never does.
hz_wait_http() {
    local url="$1" expect="${2:-}" tries="${HZ_WAIT_TRIES:-24}" i body code
    for ((i = 1; i <= tries; i++)); do
        body=$(curl -s --max-time 20 -w $'\n%{http_code}' "$url" 2>/dev/null || true)
        code="${body##*$'\n'}"
        body="${body%$'\n'*}"
        if [[ "$code" == 200 ]] && { [[ -z "$expect" ]] || [[ "$body" == *"$expect"* ]]; }; then
            hz_log "live: $url (HTTP 200${expect:+, contains $expect})"
            return 0
        fi
        hz_log "waiting for $url ($i/$tries): HTTP $code"
        sleep 5
    done
    hz_die "$url is not live${expect:+ with $expect} after $((tries * 5)) s"
}

# Wait until a container reports healthy (or running, if it has no healthcheck).
hz_wait_container() {
    local name="$1" tries="${HZ_WAIT_TRIES:-24}" i state
    for ((i = 1; i <= tries; i++)); do
        state=$(hz_docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$name" 2>/dev/null || echo missing)
        if [[ "$state" == healthy || "$state" == running ]]; then
            hz_log "container $name: $state"
            return 0
        fi
        hz_log "waiting for container $name ($i/$tries): $state"
        sleep 5
    done
    hz_die "container $name not healthy after $((tries * 5)) s"
}

# Poll URL until its trimmed body is exactly VALUE (e.g. /VERSION or /REVISION). A substring check would accept
# 0.20.10 for 0.20.1.
hz_wait_exact() {
    local url="$1" want="$2" tries="${HZ_WAIT_TRIES:-24}" i got
    for ((i = 1; i <= tries; i++)); do
        got=$(curl -s --max-time 20 "$url" 2>/dev/null | tr -d '[:space:]' || true)
        if [[ "$got" == "$want" ]]; then
            hz_log "live: $url = $want"
            return 0
        fi
        hz_log "waiting for $url ($i/$tries): ${got:0:40}"
        sleep 5
    done
    hz_die "$url does not serve $want after $((tries * 5)) s"
}

# Cloudflare API token for cache purges: the first Token line under the "## Account API Token" heading of the shared
# credentials file (section-anchored: the file holds several tokens). Prints nothing and returns 1 if not found.
hz_cf_token() {
    local cred="${HZ_CF_CRED:-$HOME/Documents/server-mini-development/credentials/cloudflare.md}" token
    [[ -r "$cred" ]] || return 1
    token=$(awk '/^## Account API Token/{f=1} f && /\*\*Token\*\*:/{sub(/.*\*\*Token\*\*:[[:space:]]*`?/, ""); sub(/`.*/, ""); gsub(/[[:space:]]/, ""); print; exit}' "$cred")
    [[ -n "$token" ]] || return 1
    printf '%s\n' "$token"
}

# Purge everything in a Cloudflare zone. Resolve the token BEFORE changing production (hz_cf_token) and pass it in.
# The response is captured first: `curl | grep -q` under pipefail can fail a successful purge on SIGPIPE.
hz_cf_purge() {
    local zone="$1" token="$2" resp
    [[ -n "$zone" && -n "$token" ]] || hz_die "hz_cf_purge needs a zone id and a token"
    resp=$(curl -sS --max-time 30 -X POST "https://api.cloudflare.com/client/v4/zones/$zone/purge_cache" \
        -H "Authorization: Bearer $token" -H "Content-Type: application/json" \
        --data '{"purge_everything":true}' 2>&1) || true
    [[ "$resp" == *'"success":true'* ]] || hz_die "Cloudflare purge of zone $zone failed: ${resp:0:200}"
    hz_log "Cloudflare cache purged (zone $zone)"
}
