$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$credential = Import-Clixml -LiteralPath (Join-Path $projectRoot '.local\mysql-root.credential.xml')
Write-Output ('MySQL user: ' + $credential.UserName)
Write-Output ('MySQL password: ' + $credential.GetNetworkCredential().Password)
