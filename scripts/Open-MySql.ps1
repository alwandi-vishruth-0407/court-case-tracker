$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$credential = Import-Clixml -LiteralPath (Join-Path $projectRoot '.local\mysql-root.credential.xml')
$env:MYSQL_PWD = $credential.GetNetworkCredential().Password
try {
    & 'C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe' `
        --no-defaults --host=127.0.0.1 --user=root court_case_tracker
} finally {
    Remove-Item Env:\MYSQL_PWD -ErrorAction SilentlyContinue
}
