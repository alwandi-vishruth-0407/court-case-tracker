$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$localDir = Join-Path $projectRoot '.local'
$credentialPath = Join-Path $localDir 'mysql-root.credential.xml'
$initPath = Join-Path $localDir 'mysql-reset-init.sql'
$statusPath = Join-Path $localDir 'mysql-reset-status.json'
$serverPath = 'C:\Program Files\MySQL\MySQL Server 8.0\bin\mysqld.exe'
$configPath = 'C:\ProgramData\MySQL\MySQL Server 8.0\my.ini'
$pythonPath = Join-Path $projectRoot 'backend\.venv\Scripts\python.exe'
$checkPath = Join-Path $PSScriptRoot 'mysql_connection.py'
$resetProcess = $null
$serviceStopped = $false

function Write-ResetStatus($state, $message) {
    @{ state = $state; message = $message; time = (Get-Date).ToString('o') } |
        ConvertTo-Json | Set-Content -LiteralPath $statusPath -Encoding UTF8
}

try {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'The password reset requires an administrator PowerShell process.'
    }
    New-Item -ItemType Directory -Path $localDir -Force | Out-Null
    $acl = [Security.AccessControl.DirectorySecurity]::new()
    $acl.SetAccessRuleProtection($true, $false)
    foreach ($sid in @($identity.User.Value, 'S-1-5-18', 'S-1-5-32-544')) {
        $rule = [Security.AccessControl.FileSystemAccessRule]::new(
            [Security.Principal.SecurityIdentifier]::new($sid), 'FullControl',
            'ContainerInherit,ObjectInherit', 'None', 'Allow')
        $acl.AddAccessRule($rule)
    }
    Set-Acl -LiteralPath $localDir -AclObject $acl
    if (Test-Path -LiteralPath $credentialPath) {
        throw 'An encrypted root credential already exists. Refusing to replace it automatically.'
    }
    $randomBytes = New-Object byte[] 24
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($randomBytes)
    $rng.Dispose()
    $newPassword = 'Cc9!' + [Convert]::ToBase64String($randomBytes)
    $securePassword = ConvertTo-SecureString $newPassword -AsPlainText -Force
    [Management.Automation.PSCredential]::new('root', $securePassword) |
        Export-Clixml -LiteralPath $credentialPath
    [IO.File]::WriteAllText($initPath,
        "ALTER USER 'root'@'localhost' IDENTIFIED BY '$newPassword';`r`n",
        [Text.UTF8Encoding]::new($false))
    Write-ResetStatus 'stopping' 'Stopping MySQL80 for the requested root password reset.'
    Stop-Service -Name MySQL80
    (Get-Service -Name MySQL80).WaitForStatus('Stopped', [TimeSpan]::FromSeconds(30))
    $serviceStopped = $true
    $serverArguments = @(
        ('--defaults-file="{0}"' -f $configPath),
        ('--init-file="{0}"' -f ($initPath.Replace('\', '/'))),
        '--console', '--bind-address=127.0.0.1', '--mysqlx=OFF'
    )
    Write-ResetStatus 'resetting' 'Starting MySQL with a temporary password reset init file.'
    $resetProcess = Start-Process -FilePath $serverPath -ArgumentList $serverArguments `
        -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $localDir 'mysql-reset.stdout.log') `
        -RedirectStandardError (Join-Path $localDir 'mysql-reset.stderr.log')
    $env:DB_PASSWORD = $newPassword
    $connected = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Seconds 1
        if ($resetProcess.HasExited) { throw 'The temporary MySQL server exited. Inspect the reset log.' }
        & $pythonPath $checkPath *> $null
        if ($LASTEXITCODE -eq 0) { $connected = $true; break }
    }
    if (-not $connected) { throw 'Could not authenticate with the new password within the startup timeout.' }
    Remove-Item -LiteralPath $initPath -Force
    Write-ResetStatus 'restoring' 'The new password works. Restoring the normal MySQL80 service.'
    & $pythonPath $checkPath --shutdown *> $null
    if ($LASTEXITCODE -ne 0) { throw 'Could not gracefully shut down the temporary MySQL server.' }
    if (-not $resetProcess.WaitForExit(30000)) { throw 'The temporary MySQL server did not finish shutting down.' }
    Start-Service -Name MySQL80
    (Get-Service -Name MySQL80).WaitForStatus('Running', [TimeSpan]::FromSeconds(30))
    $serviceStopped = $false
    $normalConnected = $false
    for ($attempt = 0; $attempt -lt 15; $attempt++) {
        & $pythonPath $checkPath *> $null
        if ($LASTEXITCODE -eq 0) { $normalConnected = $true; break }
        Start-Sleep -Seconds 1
    }
    if (-not $normalConnected) { throw 'MySQL80 is running but the final authentication check failed.' }
    Write-ResetStatus 'complete' 'Root password reset verified. MySQL80 is running normally. The credential is encrypted for this Windows user.'
} catch {
    Write-ResetStatus 'failed' $_.Exception.Message
    exit 1
} finally {
    Remove-Item Env:\DB_PASSWORD -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $initPath) { Remove-Item -LiteralPath $initPath -Force }
    if ($serviceStopped -and (($null -eq $resetProcess) -or $resetProcess.HasExited)) {
        Start-Service -Name MySQL80 -ErrorAction SilentlyContinue
    }
}
