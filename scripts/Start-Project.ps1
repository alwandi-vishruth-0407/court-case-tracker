$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$localDir = Join-Path $projectRoot '.local'
$credential = Import-Clixml -LiteralPath (Join-Path $localDir 'mysql-app.credential.xml')
$pythonPath = Join-Path $projectRoot 'backend\.venv\Scripts\python.exe'
$nodePath = (Get-Command node.exe -ErrorAction Stop).Source
$vitePath = Join-Path $projectRoot 'frontend\node_modules\vite\bin\vite.js'
$env:DB_HOST = '127.0.0.1'
$env:DB_PORT = '3306'
$env:DB_USER = $credential.UserName
$env:DB_PASSWORD = $credential.GetNetworkCredential().Password
$env:DB_NAME = 'court_case_tracker'

function Test-LocalUrl([string]$url) {
    try { return (Invoke-WebRequest -Uri $url -TimeoutSec 3).StatusCode -eq 200 }
    catch { return $false }
}

try {
    if (-not (Test-LocalUrl 'http://127.0.0.1:8000/api/health')) {
        $backend = Start-Process -FilePath $pythonPath -ArgumentList @('-m','uvicorn','main:app','--host','127.0.0.1','--port','8000') `
            -WorkingDirectory (Join-Path $projectRoot 'backend') -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput (Join-Path $localDir 'backend.stdout.log') `
            -RedirectStandardError (Join-Path $localDir 'backend.stderr.log')
        $backend.Id | Set-Content -LiteralPath (Join-Path $localDir 'backend.pid')
    }
    for ($attempt = 0; $attempt -lt 15; $attempt++) {
        if (Test-LocalUrl 'http://127.0.0.1:8000/api/health') { break }
        Start-Sleep -Seconds 1
    }
    if (-not (Test-LocalUrl 'http://127.0.0.1:8000/api/health')) {
        throw 'Backend did not become ready. Inspect .local\backend.stderr.log.'
    }
} finally {
    foreach ($name in @('DB_HOST','DB_PORT','DB_USER','DB_PASSWORD','DB_NAME')) {
        Remove-Item -LiteralPath "Env:\$name" -ErrorAction SilentlyContinue
    }
}

if (-not (Test-LocalUrl 'http://127.0.0.1:5173')) {
    $frontend = Start-Process -FilePath $nodePath -ArgumentList @(('"{0}"' -f $vitePath),'--host','127.0.0.1','--port','5173','--strictPort') `
        -WorkingDirectory (Join-Path $projectRoot 'frontend') -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $localDir 'frontend.stdout.log') `
        -RedirectStandardError (Join-Path $localDir 'frontend.stderr.log')
    $frontend.Id | Set-Content -LiteralPath (Join-Path $localDir 'frontend.pid')
}
for ($attempt = 0; $attempt -lt 15; $attempt++) {
    if (Test-LocalUrl 'http://127.0.0.1:5173') { break }
    Start-Sleep -Seconds 1
}
if (-not (Test-LocalUrl 'http://127.0.0.1:5173')) {
    throw 'Frontend did not become ready. Inspect .local\frontend.stderr.log.'
}
Write-Output 'Application: http://127.0.0.1:5173'
Write-Output 'API documentation: http://127.0.0.1:8000/docs'
Write-Output (Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/health' | ConvertTo-Json -Compress)
