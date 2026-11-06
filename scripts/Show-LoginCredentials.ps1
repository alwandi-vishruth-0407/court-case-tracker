$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$credential = Import-Clixml -LiteralPath (Join-Path $projectRoot '.local\login-demo.credential.xml')
Write-Output 'App username: demo'
Write-Output 'App email: demo@caseledger.local'
Write-Output ('App password: ' + $credential.GetNetworkCredential().Password)
