$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$localDir = Join-Path $projectRoot '.local'
$statusPath = Join-Path $localDir 'mysql-reset-status.json'
$credential = Import-Clixml -LiteralPath (Join-Path $localDir 'mysql-root.credential.xml')
$env:MYSQL_PWD = $credential.GetNetworkCredential().Password
try {
    if ((Get-Service MySQL80).Status -ne 'Running') {
        $temporaryServers = @(Get-Process -Name mysqld -ErrorAction SilentlyContinue)
        if ($temporaryServers.Count -gt 0) {
            & 'C:\Program Files\MySQL\MySQL Server 8.0\bin\mysqladmin.exe' `
                --no-defaults --host=127.0.0.1 --user=root --connect-timeout=5 shutdown
            if ($LASTEXITCODE -ne 0) { throw 'The temporary server could not be stopped gracefully.' }
            foreach ($server in $temporaryServers) {
                if (-not $server.WaitForExit(30000)) { throw 'The temporary server has not finished shutting down.' }
            }
        }
        Start-Service -Name MySQL80
        (Get-Service MySQL80).WaitForStatus('Running', [TimeSpan]::FromSeconds(30))
    }
    & 'C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe' `
        --no-defaults --host=127.0.0.1 --user=root --execute='SELECT 1;' *> $null
    if ($LASTEXITCODE -ne 0) { throw 'The normal service authentication check failed.' }
    @{state='complete';message='Root password reset verified. MySQL80 is running normally. The credential is encrypted for this Windows user.';time=(Get-Date).ToString('o')} |
        ConvertTo-Json | Set-Content -LiteralPath $statusPath -Encoding UTF8
} catch {
    @{state='failed';message=$_.Exception.Message;time=(Get-Date).ToString('o')} |
        ConvertTo-Json | Set-Content -LiteralPath $statusPath -Encoding UTF8
    exit 1
} finally {
    Remove-Item Env:\MYSQL_PWD -ErrorAction SilentlyContinue
}
