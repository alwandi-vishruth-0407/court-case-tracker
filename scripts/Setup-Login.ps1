$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$localDir = Join-Path $projectRoot '.local'
if (-not (Test-Path -LiteralPath $localDir)) {
    New-Item -ItemType Directory -Path $localDir | Out-Null
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $acl = Get-Acl -LiteralPath $localDir
    $acl.SetAccessRuleProtection($true, $false)
    foreach ($sid in @($identity.User.Value, 'S-1-5-18', 'S-1-5-32-544')) {
        $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
            [Security.Principal.SecurityIdentifier]::new($sid), 'FullControl',
            'ContainerInherit,ObjectInherit', 'None', 'Allow'))
    }
    Set-Acl -LiteralPath $localDir -AclObject $acl
}
$credentialPath = Join-Path $localDir 'login-demo.credential.xml'
$rootCredentialPath = Join-Path $localDir 'mysql-root.credential.xml'
if (Test-Path -LiteralPath $rootCredentialPath) {
    $rootCredential = Import-Clixml -LiteralPath $rootCredentialPath
} else {
    $rootCredential = Get-Credential -UserName 'root' -Message 'MySQL administrator credential for creating the demo login'
}
$appCredentialPath = Join-Path $localDir 'mysql-app.credential.xml'
if (Test-Path -LiteralPath $credentialPath) {
    $loginCredential = Import-Clixml -LiteralPath $credentialPath
} else {
    $randomBytes = New-Object byte[] 12
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($randomBytes)
    $rng.Dispose()
    $password = 'Case9!' + [Convert]::ToBase64String($randomBytes)
    $securePassword = ConvertTo-SecureString $password -AsPlainText -Force
    $loginCredential = [Management.Automation.PSCredential]::new('demo', $securePassword)
    $loginCredential | Export-Clixml -LiteralPath $credentialPath
}
$env:DB_PASSWORD = $rootCredential.GetNetworkCredential().Password
$env:AUTH_DB_USER = $rootCredential.UserName
$env:APP_DB_USER = if (Test-Path -LiteralPath $appCredentialPath) {
    (Import-Clixml -LiteralPath $appCredentialPath).UserName
} else { '' }
$env:AUTH_DEMO_PASSWORD = $loginCredential.GetNetworkCredential().Password
try {
    & (Join-Path $projectRoot 'backend\.venv\Scripts\python.exe') (Join-Path $PSScriptRoot 'setup_auth.py')
    if ($LASTEXITCODE -ne 0) { throw 'Login setup failed.' }
} finally {
    foreach ($name in @('DB_PASSWORD', 'AUTH_DB_USER', 'APP_DB_USER', 'AUTH_DEMO_PASSWORD')) {
        Remove-Item -LiteralPath "Env:\$name" -ErrorAction SilentlyContinue
    }
}
