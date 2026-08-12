[CmdletBinding()]
param(
    [string]$Server = "",
    [string]$User = "",
    [int]$Port = 0,
    [string]$IdentityFile = "",
    [string]$HomeRoot = "",
    [string]$ApiUrl = "https://api.smart.ktragroup.com",
    [switch]$SkipTests,
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$FrontendRoot = Join-Path $ProjectRoot "frontend_v2"
$ReleaseId = (Get-Date).ToUniversalTime().ToString("yyyyMMddHHmmss")
$TempRoot = Join-Path ([System.IO.Path]::GetTempPath()) "ktra-deploy-$ReleaseId"
$BundlePath = Join-Path $TempRoot "ktra-release-$ReleaseId.tar.gz"

if (-not $Server) { $Server = if ($env:KTRA_DEPLOY_HOST) { $env:KTRA_DEPLOY_HOST } else { "smart.ktragroup.com" } }
if (-not $User) { $User = if ($env:KTRA_DEPLOY_USER) { $env:KTRA_DEPLOY_USER } else { "smartktra" } }
if ($Port -le 0) { $Port = if ($env:KTRA_DEPLOY_PORT) { [int]$env:KTRA_DEPLOY_PORT } else { 22 } }
if (-not $IdentityFile -and $env:KTRA_DEPLOY_KEY) { $IdentityFile = $env:KTRA_DEPLOY_KEY }
if (-not $HomeRoot) { $HomeRoot = if ($env:KTRA_DEPLOY_HOME) { $env:KTRA_DEPLOY_HOME } else { "/home/smartktra" } }

function Write-Step([string]$Message) {
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Invoke-Native {
    param(
        [Parameter(Mandatory = $true)][string]$Command,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [string]$WorkingDirectory = $ProjectRoot
    )
    Push-Location $WorkingDirectory
    try {
        & $Command @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "$Command failed with exit code $LASTEXITCODE."
        }
    } finally {
        Pop-Location
    }
}

function Assert-Command([string]$Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' was not found."
    }
}

function Test-TcpPort([string]$HostName, [int]$RemotePort) {
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $connect = $client.ConnectAsync($HostName, $RemotePort)
        return $connect.Wait(5000) -and $client.Connected
    } catch {
        return $false
    } finally {
        $client.Dispose()
    }
}

function Get-SshCommonOptions {
    $options = @("-o", "ConnectTimeout=15", "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=4")
    if ($IdentityFile) { $options += @("-i", $IdentityFile) }
    return $options
}

if ($Server -notmatch '^[A-Za-z0-9.-]+$') { throw "Invalid SSH host name." }
if ($User -notmatch '^[A-Za-z0-9._-]+$') { throw "Invalid SSH user." }
if ($HomeRoot -notmatch '^/home/[A-Za-z0-9._/-]+$') { throw "KTRA_DEPLOY_HOME must be a path under /home/." }
if ($Port -lt 1 -or $Port -gt 65535) { throw "Invalid SSH port." }
if ($IdentityFile -and -not (Test-Path -LiteralPath $IdentityFile)) { throw "SSH identity file was not found: $IdentityFile" }

Assert-Command "ssh"
Assert-Command "scp"
Assert-Command "tar"
Assert-Command "git"

$Python = Join-Path $ProjectRoot "venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) { $Python = "python" }

try {
    if (-not $DryRun) {
        Write-Step "Checking SSH endpoint $User@$Server`:$Port"
        if (-not (Test-TcpPort $Server $Port)) {
            throw "SSH is not reachable on $Server`:$Port. Set the correct port with KTRA_DEPLOY_PORT or pass -Port. The public website is not the SSH endpoint unless cPanel enabled SSH there."
        }
        $sshOptions = Get-SshCommonOptions
        Invoke-Native "ssh" (@("-p", "$Port") + $sshOptions + @("$User@$Server", "printf 'SSH authenticated.\n'"))
    }

    Write-Step "Reviewing the working tree"
    Invoke-Native "git" @("status", "--short")
    Write-Host "The deploy package includes application directories only; .env, keys, logs, archives, caches and local databases are excluded." -ForegroundColor Yellow

    if (-not $SkipTests) {
        Write-Step "Running Django regression tests"
        # pytest لا manage.py test: الأخير يكتشف أصناف TestCase وحدها ويفوّت 253
        # اختباراً بنمط الدوال (docs/CHANGELOG.md 2026-08-12) — بوابة النشر يجب
        # أن تكون الأكمل لا الأنقص. الإعدادات من pytest.ini (core.test_settings).
        Invoke-Native $Python @("-m", "pytest", "-q", "-n", "auto")
        Invoke-Native $Python @("manage.py", "makemigrations", "--check", "--dry-run")
        Invoke-Native $Python @("manage.py", "check")
    } else {
        Write-Host "WARNING: tests were skipped by request." -ForegroundColor Yellow
    }

    Write-Step "Building the production frontend"
    $previousApiUrl = $env:VITE_API_URL
    try {
        $env:VITE_API_URL = $ApiUrl
        Invoke-Native "npm.cmd" @("run", "build") $FrontendRoot
    } finally {
        $env:VITE_API_URL = $previousApiUrl
    }

    Write-Step "Creating a secret-free deployment bundle"
    New-Item -ItemType Directory -Path $TempRoot -Force | Out-Null
    $backendArchive = Join-Path $TempRoot "backend.tar.gz"
    $frontendArchive = Join-Path $TempRoot "frontend.tar.gz"
    $remoteScriptPath = Join-Path $TempRoot "deploy_remote.sh"

    $backendItems = @(
        "accounting", "bridge", "core", "hr", "inventory", "logistics",
        "partners", "realestate", "sales", "tenants", "tools",
        "frontend_v2", "manage.py", "requirements.txt"
    )
    $backendExcludes = @(
        "--exclude=frontend_v2/node_modules",
        "--exclude=frontend_v2/dist",
        "--exclude=frontend_v2/test-results*",
        "--exclude=frontend_v2/playwright-report",
        "--exclude=frontend_v2/smart-product-search-platform",
        "--exclude=frontend_v2/*.zip",
        "--exclude=frontend_v2/*.rar",
        "--exclude=frontend_v2/.env*",
        "--exclude=.env*",
        "--exclude=*/.env*",
        "--exclude=**/.env",
        "--exclude=**/.env.*",
        "--exclude=**/__pycache__",
        "--exclude=**/*.pyc",
        "--exclude=**/*.pem",
        "--exclude=**/*.sqlite3",
        "--exclude=**/*.db",
        "--exclude=**/serviceAccountKey.json"
    )
    Invoke-Native "tar" (@("-czf", $backendArchive) + $backendExcludes + $backendItems)
    Invoke-Native "tar" @("-czf", $frontendArchive, "-C", (Join-Path $FrontendRoot "dist"), ".")

    $backendEntries = @(& tar -tzf $backendArchive)
    if ($LASTEXITCODE -ne 0) { throw "Could not audit the backend archive." }
    $forbiddenEntries = @($backendEntries | Where-Object {
        $_ -match '(^|/)(\.env($|\.)|node_modules(/|$)|dist(/|$)|serviceAccountKey\.json$)' -or
        $_ -match '\.(pem|sqlite3|db|zip|rar)$'
    })
    if ($forbiddenEntries.Count -gt 0) {
        throw "Secret or generated files entered the deployment archive: $($forbiddenEntries -join ', ')"
    }
    if ($backendEntries -notcontains "manage.py") { throw "manage.py is missing from the backend archive." }

    $remoteScript = @'
#!/usr/bin/env bash
set -Eeuo pipefail

RELEASE_ID="$1"
HOME_ROOT="$2"

case "$HOME_ROOT" in
  /home/*) ;;
  *) echo "Unsafe home path: $HOME_ROOT" >&2; exit 2 ;;
esac

DEPLOY_ROOT="$HOME_ROOT/.deploy"
WORK_DIR="$DEPLOY_ROOT/incoming/$RELEASE_ID"
BACKUP_DIR="$DEPLOY_ROOT/backups/$RELEASE_ID"
BACKEND_DIR="$HOME_ROOT/backend"
PUBLIC_DIR="$HOME_ROOT/public_html"
PYTHON="$BACKEND_DIR/venv/bin/python"
PIP="$BACKEND_DIR/venv/bin/pip"
GUNICORN="$BACKEND_DIR/venv/bin/gunicorn"
MUTATED=0

log() { printf '\n==> %s\n' "$1"; }
require() { command -v "$1" >/dev/null 2>&1 || { echo "Required server command not found: $1" >&2; exit 3; }; }

# ── gunicorn (المرحلة 5 / P0-1 — SCALABILITY_AUDIT §6) ──────────────────────
# كان: --workers 3 من نوع sync بلا threads ⇒ **السقف المطلق 3 طلبات متزامنة**،
# بلا --timeout (الافتراضي 30ث < مهلة المساعد 60–120ث ⇒ الـworker يُقتل وسط
# استدعاء المساعد)، وإعادة التشغيل بـpkill + sleep ⇒ انقطاع كامل عند كل نشر.
#
# صار: gthread — السعة = workers × threads. السقف الأعلى ليس الـCPU بل **اتصالات
# MySQL**: مع CONN_MAX_AGE=60 (core/settings.py:172) كل خيط يمسك اتصالاً دائماً،
# فـworkers × threads هو عدد الاتصالات التي يحجزها التطبيق. الافتراضات أدناه
# تُبقيه ≤20 — يناسب حصة الاستضافة المشتركة، ويظل ~7 أضعاف الوضع السابق.
# ارفعها بمتغيّرات البيئة بعد التأكد من حصة max_connections على الخادم.
GUNICORN_PID_FILE="$HOME_ROOT/logs/gunicorn.pid"
if [[ -z "${GUNICORN_WORKERS:-}" ]]; then
  _cores="$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 2)"
  GUNICORN_WORKERS=$(( _cores * 2 + 1 ))
  (( GUNICORN_WORKERS > 5 )) && GUNICORN_WORKERS=5
fi
GUNICORN_THREADS="${GUNICORN_THREADS:-4}"
# 180ث > أطول مهلة مساعد مُعلنة (core/settings.py:302-304,329).
GUNICORN_TIMEOUT="${GUNICORN_TIMEOUT:-180}"

start_gunicorn() {
  cd "$BACKEND_DIR"
  "$GUNICORN" --bind 127.0.0.1:8000 --daemon \
    --worker-class gthread \
    --workers "$GUNICORN_WORKERS" --threads "$GUNICORN_THREADS" \
    --timeout "$GUNICORN_TIMEOUT" --graceful-timeout 60 --keep-alive 5 \
    --max-requests 1000 --max-requests-jitter 100 \
    --pid "$GUNICORN_PID_FILE" \
    --access-logfile "$HOME_ROOT/logs/gunicorn-access.log" \
    --error-logfile "$HOME_ROOT/logs/gunicorn.log" core.wsgi
}

restart_gunicorn() {
  local pid=""
  [[ -f "$GUNICORN_PID_FILE" ]] && pid="$(cat "$GUNICORN_PID_FILE" 2>/dev/null || true)"
  # إعادة تحميل رشيقة: SIGHUP يُنهي الطلبات الجارية ويُقلع عمّالاً جدداً بالكود
  # الجديد بلا إسقاط اتصال واحد. **قيد معروف:** HUP لا يلتقط تغيّر وسائط سطر
  # الأوامر (workers/threads/timeout) — بعد تعديل أيٍّ منها شغّل النشر مرة
  # بـGUNICORN_FORCE_RESTART=1 لإعادة تشغيل كاملة.
  if [[ -n "$pid" ]] && [[ "${GUNICORN_FORCE_RESTART:-0}" != "1" ]] \
     && kill -0 "$pid" 2>/dev/null; then
    kill -HUP "$pid" 2>/dev/null && return 0
  fi
  # لا pidfile (أول نشر بعد هذا التغيير) أو العملية ميتة أو إعادة تشغيل مفروضة.
  if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
    kill -TERM "$pid" 2>/dev/null || true
  else
    pkill -f "gunicorn.*core.wsgi" >/dev/null 2>&1 || true
  fi
  sleep 2
  rm -f "$GUNICORN_PID_FILE"
  start_gunicorn
}

rollback() {
  local exit_code=$?
  trap - ERR
  set +e
  if [[ "$MUTATED" == "1" ]]; then
    echo "Deployment failed; restoring backend and frontend files from $BACKUP_DIR" >&2
    rsync -a --delete \
      --exclude='.env' --exclude='venv/' --exclude='media/' --exclude='staticfiles/' \
      --exclude='django_cache/' --exclude='frontend_v2/node_modules/' --exclude='frontend_v2/dist/' \
      "$BACKUP_DIR/backend/" "$BACKEND_DIR/"
    rsync -a --delete \
      --exclude='api.smart.ktragroup.com/' --exclude='.well-known/' --exclude='.htaccess' --exclude='cgi-bin/' \
      "$BACKUP_DIR/frontend/" "$PUBLIC_DIR/"
    "$PIP" install -r "$BACKEND_DIR/requirements.txt" >/dev/null 2>&1 || true
    restart_gunicorn || true
    echo "File rollback completed. Database backup: $BACKUP_DIR/database.sql.gz" >&2
    echo "Database migrations are not auto-reversed because doing so can destroy live writes." >&2
  fi
  exit "$exit_code"
}
trap rollback ERR

require rsync
require tar
require curl
require mysqldump
[[ -x "$PYTHON" ]] || { echo "Python venv not found: $PYTHON" >&2; exit 4; }
[[ -x "$PIP" ]] || { echo "pip not found: $PIP" >&2; exit 4; }
[[ -x "$GUNICORN" ]] || { echo "gunicorn not found: $GUNICORN" >&2; exit 4; }

# P2-5 (SCALABILITY_AUDIT): كانت البوابة تطلب 3.12+ بحجة «المشروع Django 6»،
# بينما requirements.txt يثبّت Django 5.1 LTS عمداً لأن السيرفر على Python 3.10.
# النتيجة: بوابة تمنع النشر على البيئة الصحيحة نفسها. الأرضية الحقيقية هي أدنى
# نسخة يدعمها Django 5.1 — أي 3.10. أي رفع هنا يجب أن يتبع رفع requirements.txt.
if ! "$PYTHON" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
  echo "This project pins Django 5.1 LTS, which requires Python 3.10+. The server venv reports: $($PYTHON --version 2>&1)" >&2
  exit 5
fi

export DJANGO_ENV=production

"$PYTHON" - "$BACKEND_DIR/.env" <<'PY'
import sys
from pathlib import Path

values = {}
for raw_line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
    line = raw_line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    values[key.strip()] = value

required = (
    "DJANGO_ENV",
    "DJANGO_SECRET_KEY",
    "MYSQL_DATABASE",
    "MYSQL_USER",
    "MYSQL_PASSWORD",
    "MYSQL_HOST",
    "MYSQL_PORT",
    "CLOUDINARY_CLOUD_NAME",
    "CLOUDINARY_API_KEY",
    "CLOUDINARY_API_SECRET",
    "OPENCLAW_BEARER_TOKEN",
)
missing = [name for name in required if not values.get(name)]
if missing:
    raise SystemExit(
        "Missing required production variables in .env: " + ", ".join(missing)
    )
if values["DJANGO_ENV"].strip().lower() not in {"production", "prod"}:
    raise SystemExit("DJANGO_ENV must be set to production in the server .env")
secret_key = values["DJANGO_SECRET_KEY"]
if len(secret_key) < 50 or "change-me" in secret_key.lower():
    raise SystemExit("DJANGO_SECRET_KEY must be a rotated, non-placeholder value of at least 50 characters")
PY

mkdir -p "$WORK_DIR/backend" "$WORK_DIR/frontend" "$BACKUP_DIR/backend" "$BACKUP_DIR/frontend"
tar -xzf "$WORK_DIR/backend.tar.gz" -C "$WORK_DIR/backend"
tar -xzf "$WORK_DIR/frontend.tar.gz" -C "$WORK_DIR/frontend"
[[ -f "$WORK_DIR/backend/manage.py" ]] || { echo "Invalid backend package." >&2; exit 6; }
[[ -f "$WORK_DIR/frontend/index.html" ]] || { echo "Invalid frontend package." >&2; exit 6; }

log "Backing up current application files"
rsync -a \
  --exclude='.env' --exclude='venv/' --exclude='media/' --exclude='staticfiles/' \
  --exclude='django_cache/' --exclude='frontend_v2/node_modules/' --exclude='frontend_v2/dist/' \
  "$BACKEND_DIR/" "$BACKUP_DIR/backend/"
rsync -a \
  --exclude='api.smart.ktragroup.com/' --exclude='.well-known/' --exclude='.htaccess' --exclude='cgi-bin/' \
  "$PUBLIC_DIR/" "$BACKUP_DIR/frontend/"

log "Backing up MySQL before migrations"
cd "$BACKEND_DIR"
"$PYTHON" - "$BACKUP_DIR/database.sql.gz" <<'PY'
import gzip
import os
import shutil
import subprocess
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
from django.conf import settings

db = settings.DATABASES["default"]
env = os.environ.copy()
env["MYSQL_PWD"] = str(db.get("PASSWORD") or "")
command = [
    "mysqldump", "--single-transaction", "--quick", "--skip-lock-tables",
    "--host", str(db.get("HOST") or "localhost"),
    "--port", str(db.get("PORT") or "3306"),
    "--user", str(db.get("USER") or ""),
    str(db.get("NAME") or ""),
]
process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
with gzip.open(sys.argv[1], "wb") as target:
    assert process.stdout is not None
    shutil.copyfileobj(process.stdout, target)
stderr = process.communicate()[1]
if process.returncode:
    raise SystemExit(f"mysqldump failed: {stderr.decode(errors='replace')}")
PY

MUTATED=1
log "Synchronizing backend code"
rsync -a --delete \
  --exclude='.env' --exclude='venv/' --exclude='media/' --exclude='staticfiles/' \
  --exclude='django_cache/' --exclude='frontend_v2/node_modules/' --exclude='frontend_v2/dist/' \
  "$WORK_DIR/backend/" "$BACKEND_DIR/"

log "Installing Python requirements"
"$PIP" install -r "$BACKEND_DIR/requirements.txt"

log "Applying Django checks, migrations and static files"
cd "$BACKEND_DIR"
"$PYTHON" manage.py check
"$PYTHON" manage.py migrate --noinput
"$PYTHON" manage.py collectstatic --noinput

log "Synchronizing frontend while preserving cPanel and API directories"
rsync -a --delete \
  --exclude='api.smart.ktragroup.com/' --exclude='.well-known/' --exclude='.htaccess' --exclude='cgi-bin/' \
  "$WORK_DIR/frontend/" "$PUBLIC_DIR/"

log "Restarting Gunicorn"
restart_gunicorn

log "Running health checks"
healthy=0
for _ in {1..12}; do
  if curl -fsS --max-time 10 http://127.0.0.1:8000/api/health/ >/dev/null; then healthy=1; break; fi
  sleep 2
done
[[ "$healthy" == "1" ]] || { echo "Local API health check failed." >&2; false; }
curl -fsS --max-time 20 https://api.smart.ktragroup.com/api/health/ >/dev/null
curl -fsS --max-time 20 https://smart.ktragroup.com/ >/dev/null

MUTATED=0
trap - ERR
rm -rf "$WORK_DIR"
find "$DEPLOY_ROOT/backups" -mindepth 1 -maxdepth 1 -type d -printf '%T@ %p\n' \
  | sort -nr | tail -n +6 | cut -d' ' -f2- | xargs -r rm -rf
log "Deployment $RELEASE_ID completed successfully"
'@
    [System.IO.File]::WriteAllText($remoteScriptPath, $remoteScript.Replace("`r`n", "`n"), [System.Text.UTF8Encoding]::new($false))
    Invoke-Native "tar" @("-czf", $BundlePath, "-C", $TempRoot, "backend.tar.gz", "frontend.tar.gz", "deploy_remote.sh")

    $bundleHash = (Get-FileHash -LiteralPath $BundlePath -Algorithm SHA256).Hash
    Write-Host "Bundle SHA256: $bundleHash"

    if ($DryRun) {
        Write-Host "Dry run completed. No files were uploaded and the server was not changed." -ForegroundColor Green
        exit 0
    }

    $remoteTarget = "$User@$Server"
    $remoteUpload = "$HomeRoot/ktra-release-$ReleaseId.tar.gz"
    $remoteWork = "$HomeRoot/.deploy/incoming/$ReleaseId"
    $sshCommon = Get-SshCommonOptions

    Write-Step "Uploading one deployment bundle"
    Invoke-Native "scp" (@("-P", "$Port") + $sshCommon + @($BundlePath, "${remoteTarget}:$remoteUpload"))

    Write-Step "Deploying on the server"
    $remoteCommand = "set -e; mkdir -p '$remoteWork'; tar -xzf '$remoteUpload' -C '$remoteWork'; rm -f '$remoteUpload'; bash '$remoteWork/deploy_remote.sh' '$ReleaseId' '$HomeRoot'"
    Invoke-Native "ssh" (@("-p", "$Port") + $sshCommon + @($remoteTarget, $remoteCommand))

    Write-Host "`nDeployment completed: https://smart.ktragroup.com" -ForegroundColor Green
} catch {
    Write-Host "`nDEPLOYMENT STOPPED: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "No credentials were stored by this script." -ForegroundColor Yellow
    exit 1
} finally {
    if (Test-Path -LiteralPath $TempRoot) {
        Remove-Item -LiteralPath $TempRoot -Recurse -Force
    }
}
