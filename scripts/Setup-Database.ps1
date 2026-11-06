$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$localDir = Join-Path $projectRoot '.local'
$mysqlPath = 'C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe'
$credential = Import-Clixml -LiteralPath (Join-Path $localDir 'mysql-root.credential.xml')
$env:MYSQL_PWD = $credential.GetNetworkCredential().Password
$mysqlArguments = @('--no-defaults', '--host=127.0.0.1', '--user=root', '--default-character-set=utf8mb4', '--batch', '--raw')
$report = [Collections.Generic.List[string]]::new()

function Invoke-ProjectSql([string]$sql, [string]$label) {
    $result = $sql | & $mysqlPath @mysqlArguments 2>&1
    if ($LASTEXITCODE -ne 0) { throw "$label failed: $($result -join [Environment]::NewLine)" }
    $report.Add("`r`n$label")
    foreach ($line in $result) { $report.Add([string]$line); Write-Output $line }
}

try {
    Invoke-ProjectSql 'SELECT VERSION() AS mysql_version, CURRENT_USER() AS connected_account;' 'Connection'
    Invoke-ProjectSql (Get-Content -LiteralPath (Join-Path $projectRoot 'sql\schema.sql') -Raw) 'schema.sql'
    $existingRowsSql = @'
USE court_case_tracker;
SELECT (SELECT COUNT(*) FROM judges) + (SELECT COUNT(*) FROM parties)
     + (SELECT COUNT(*) FROM cases) + (SELECT COUNT(*) FROM case_parties)
     + (SELECT COUNT(*) FROM hearings) + (SELECT COUNT(*) FROM judgments);
'@
    $existingRows = $existingRowsSql | & $mysqlPath @mysqlArguments --skip-column-names
    if ($LASTEXITCODE -ne 0) { throw 'Could not inspect existing rows before seeding.' }
    if ([int]$existingRows -eq 0) {
        $seedSql = Get-Content -LiteralPath (Join-Path $projectRoot 'sql\seed.sql') -Raw
        Invoke-ProjectSql ("START TRANSACTION;`r`n" + $seedSql + "`r`nCOMMIT;") 'seed.sql'
        $report.Add('Seed inserted successfully.')
    } elseif ([int]$existingRows -eq 6) {
        $matchingRowsSql = @'
USE court_case_tracker;
SELECT
 (SELECT COUNT(*) FROM judges WHERE
   (judge_id=1 AND full_name='Justice Mira Rao' AND designation='Presiding Judge' AND court_name='District Civil Court') OR
   (judge_id=2 AND full_name='Justice Arvind Sen' AND designation='Appellate Judge' AND court_name='High Court'))
 + (SELECT COUNT(*) FROM parties WHERE
   (party_id=1 AND party_name='Asha Nair' AND party_type='Person') OR
   (party_id=2 AND party_name='Northbridge Housing Board' AND party_type='Organization') OR
   (party_id=3 AND party_name='Rohan Mehta' AND party_type='Person') OR
   (party_id=4 AND party_name='Cedar Works Ltd' AND party_type='Organization'));
'@
        $matchingRows = $matchingRowsSql | & $mysqlPath @mysqlArguments --skip-column-names
        if ($LASTEXITCODE -ne 0 -or [int]$matchingRows -ne 6) {
            throw 'The database contains nonmatching records. Automatic partial seed recovery stopped.'
        }
        $seedSql = Get-Content -LiteralPath (Join-Path $projectRoot 'sql\seed.sql') -Raw
        $seedSql = [regex]::Replace($seedSql, '(?s)(INSERT INTO judges\b.*?);', '$1 ON DUPLICATE KEY UPDATE judge_id = judge_id;')
        $seedSql = [regex]::Replace($seedSql, '(?s)(INSERT INTO parties\b.*?);', '$1 ON DUPLICATE KEY UPDATE party_id = party_id;')
        Invoke-ProjectSql ("START TRANSACTION;`r`n" + $seedSql + "`r`nCOMMIT;") 'seed.sql (verified partial seed recovery)'
        $report.Add('Existing demo judges and parties were confirmed identical and preserved. All remaining demo rows were inserted in one transaction.')
    } else {
        $report.Add("Seed was skipped because the database already contains $existingRows rows.")
        Write-Output "Seed skipped: $existingRows existing rows were preserved."
    }
    Invoke-ProjectSql (Get-Content -LiteralPath (Join-Path $projectRoot 'sql\verify.sql') -Raw) 'verify.sql'
    Invoke-ProjectSql @'
USE court_case_tracker;
SELECT 'judges' AS table_name, COUNT(*) AS row_count FROM judges
UNION ALL SELECT 'parties', COUNT(*) FROM parties
UNION ALL SELECT 'cases', COUNT(*) FROM cases
UNION ALL SELECT 'case_parties', COUNT(*) FROM case_parties
UNION ALL SELECT 'hearings', COUNT(*) FROM hearings
UNION ALL SELECT 'judgments', COUNT(*) FROM judgments;
SELECT COUNT(*) AS total_cases, SUM(case_status = 'Pending') AS pending_cases,
       SUM(case_status = 'Disposed') AS disposed_cases FROM cases;
SHOW TRIGGERS;
'@ 'Counts and triggers'
    $appCredentialPath = Join-Path $localDir 'mysql-app.credential.xml'
    if (-not (Test-Path -LiteralPath $appCredentialPath)) {
        $randomBytes = New-Object byte[] 24
        $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
        $rng.GetBytes($randomBytes)
        $rng.Dispose()
        $appUser = 'court_case_app_' + ([guid]::NewGuid().ToString('N').Substring(0,8))
        $appPassword = 'Ca9!' + [Convert]::ToBase64String($randomBytes)
        $accountSql = "CREATE USER '$appUser'@'localhost' IDENTIFIED BY '$appPassword'; GRANT SELECT, INSERT ON court_case_tracker.* TO '$appUser'@'localhost';"
        $accountResult = $accountSql | & $mysqlPath @mysqlArguments 2>&1
        if ($LASTEXITCODE -ne 0) { throw 'Creating the application database account failed.' }
        $securePassword = ConvertTo-SecureString $appPassword -AsPlainText -Force
        [Management.Automation.PSCredential]::new($appUser, $securePassword) |
            Export-Clixml -LiteralPath $appCredentialPath
        $report.Add("Application account: $appUser@localhost; SELECT and INSERT on court_case_tracker only.")
    }
    $report | Set-Content -LiteralPath (Join-Path $projectRoot 'docs\MYSQL_VERIFICATION.txt') -Encoding UTF8
    Write-Output 'Database setup and verification completed. Results: docs\MYSQL_VERIFICATION.txt'
} finally {
    Remove-Item Env:\MYSQL_PWD -ErrorAction SilentlyContinue
}
