param(
    [string]$ComposeFile = "docker-compose.yml",
    [string]$ApiBaseUrl = "http://127.0.0.1:8000",
    [switch]$SkipNgrok
)

$ErrorActionPreference = "Stop"

function Write-Check($label, $status, $detail = "") {
    $color = switch ($status) {
        "PASS" { "Green" }
        "WARN" { "Yellow" }
        "FAIL" { "Red" }
        default { "White" }
    }
    $line = "[{0}] {1}" -f $status, $label
    if ($detail) {
        $line = "$line - $detail"
    }
    Write-Host $line -ForegroundColor $color
}

function Test-Url($url) {
    try {
        $response = Invoke-WebRequest -Uri $url -Method Get -UseBasicParsing -TimeoutSec 8
        return @{ Ok = $true; StatusCode = [int]$response.StatusCode }
    } catch {
        $status = $_.Exception.Response.StatusCode.value__ 2>$null
        return @{ Ok = $false; StatusCode = $status; Error = $_.Exception.Message }
    }
}

Write-Host "Checking local notification stack..." -ForegroundColor Cyan

$dockerAvailable = $true
try {
    docker version | Out-Null
    Write-Check "Docker CLI available" "PASS"
} catch {
    $dockerAvailable = $false
    Write-Check "Docker CLI available" "FAIL" $_.Exception.Message
}

if (-not $dockerAvailable) {
    exit 1
}

try {
    $composeRaw = docker compose -f $ComposeFile ps --format json 2>$null
    if (-not $composeRaw) {
        Write-Check "Docker Compose services" "FAIL" "No services found. Run docker compose up -d --build"
        exit 1
    }
    $composeStatus = $composeRaw | ConvertFrom-Json
} catch {
    Write-Check "Docker Compose services" "FAIL" "Cannot read Docker Compose status. Check Docker Desktop permissions or start the services first."
    exit 1
}

$requiredServices = @("redis", "celery_worker", "celery_beat")
if (-not $SkipNgrok) {
    $requiredServices += "ngrok"
}

foreach ($serviceName in $requiredServices) {
    $service = $composeStatus | Where-Object { $_.Service -eq $serviceName }
    if (-not $service) {
        Write-Check "Service $serviceName" "FAIL" "Missing from compose status"
        continue
    }

    $state = $service.State
    $health = $service.Health
    if ($state -ne "running") {
        Write-Check "Service $serviceName" "FAIL" "State=$state"
    } elseif ($health -and $health -notin @("healthy", "")) {
        Write-Check "Service $serviceName" "WARN" "Health=$health"
    } else {
        $detail = if ($health) { "State=$state Health=$health" } else { "State=$state" }
        Write-Check "Service $serviceName" "PASS" $detail
    }
}

$apiHealth = Test-Url "$ApiBaseUrl/health"
if ($apiHealth.Ok -and $apiHealth.StatusCode -eq 200) {
    Write-Check "API health endpoint" "PASS" "$ApiBaseUrl/health"
} else {
    Write-Check "API health endpoint" "WARN" "Start uvicorn separately if needed. $($apiHealth.Error)"
}

if (-not $SkipNgrok) {
    $ngrokHealth = Test-Url "http://127.0.0.1:4040/api/tunnels"
    if ($ngrokHealth.Ok -and $ngrokHealth.StatusCode -eq 200) {
        Write-Check "ngrok local inspector" "PASS" "http://127.0.0.1:4040/api/tunnels"
    } else {
        Write-Check "ngrok local inspector" "WARN" $ngrokHealth.Error
    }
}

Write-Host ""
Write-Host "Recommended first-run flow:" -ForegroundColor Cyan
Write-Host "1. Copy .env.example to .env and set your own secrets"
Write-Host "2. Start the API locally: uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload"
Write-Host "3. Start Docker services: docker compose up -d --build"
Write-Host "4. Re-run this check script"
