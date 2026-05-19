<#
.SYNOPSIS
  AoT-AI Docker helper for Windows.

.EXAMPLE
  .\docker\aot.ps1 up        # build (if needed) and start in background
  .\docker\aot.ps1 build     # rebuild image only
  .\docker\aot.ps1 logs      # tail combined logs
  .\docker\aot.ps1 logs aot-app
  .\docker\aot.ps1 ps
  .\docker\aot.ps1 down
  .\docker\aot.ps1 restart
  .\docker\aot.ps1 shell     # open a shell inside aot-app
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('up','down','build','rebuild','logs','ps','restart','shell','health')]
    [string]$Command = 'up',

    [Parameter(Position = 1, ValueFromRemainingArguments = $true)]
    [string[]]$Rest
)

$ErrorActionPreference = 'Stop'
$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $ScriptDir
$Compose    = @('compose', '-f', (Join-Path $ScriptDir 'docker-compose.yml'))

function Invoke-Docker {
    param([string[]]$Args)
    & docker @Args
    if ($LASTEXITCODE -ne 0) { throw "docker $($Args -join ' ') failed (exit $LASTEXITCODE)" }
}

# Pre-flight: Docker daemon must be running
try { docker info *> $null } catch {
    Write-Error "Docker is not running. Start Docker Desktop and try again."
    exit 1
}

# Ensure host-side dirs exist (compose bind-mounts them)
foreach ($d in @('logs', 'influxdb_config', (Join-Path 'aot' 'databases'))) {
    $full = Join-Path $ProjectDir $d
    if (-not (Test-Path $full)) { New-Item -ItemType Directory -Path $full -Force | Out-Null }
}

# Auto-create docker/.env from .env.example on first run
$EnvFile     = Join-Path $ScriptDir '.env'
$EnvExample  = Join-Path $ScriptDir '.env.example'
if (-not (Test-Path $EnvFile) -and (Test-Path $EnvExample)) {
    Copy-Item $EnvExample $EnvFile
    Write-Host "[init] Created docker/.env from .env.example — edit it to set real credentials." -ForegroundColor Yellow
}

switch ($Command) {
    'up' {
        Invoke-Docker ($Compose + @('up', '-d', '--build'))
        Write-Host ""
        Write-Host "AoT-AI is starting. UI will be at http://localhost:8084" -ForegroundColor Green
        Write-Host "Tail logs:    .\docker\aot.ps1 logs"
        Write-Host "Stop stack:   .\docker\aot.ps1 down"
    }
    'build'   { Invoke-Docker ($Compose + @('build')) }
    'rebuild' { Invoke-Docker ($Compose + @('build', '--no-cache')) }
    'down'    { Invoke-Docker ($Compose + @('down')) }
    'restart' { Invoke-Docker ($Compose + @('restart') + $Rest) }
    'ps'      { Invoke-Docker ($Compose + @('ps')) }
    'logs'    {
        $svc = if ($Rest) { $Rest } else { @() }
        Invoke-Docker ($Compose + @('logs', '-f', '--tail=200') + $svc)
    }
    'shell'   { Invoke-Docker ($Compose + @('exec', 'aot-app', 'bash')) }
    'health'  {
        Invoke-Docker ($Compose + @('ps'))
        Write-Host ""
        try {
            $resp = Invoke-WebRequest -Uri 'http://localhost:8084/' -UseBasicParsing -TimeoutSec 5
            Write-Host "Flask app: HTTP $($resp.StatusCode)" -ForegroundColor Green
        } catch {
            Write-Host "Flask app: NOT RESPONDING ($($_.Exception.Message))" -ForegroundColor Red
        }
    }
}
