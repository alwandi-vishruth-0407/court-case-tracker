# Run this copied project

The local database setup was completed and verified on 8 October 2026 using MySQL 8.0.46. All six court domain tables contain the fictional sample data. Two additional authentication tables store the demo account and sessions. The schema, seed, and verification queries ran against the real MySQL server. Database constraints, triggers, and authenticated API reads passed 28 checks. Login verification passed 41 checks.

## Restart the configured application

From this project folder in PowerShell:

```powershell
.\scripts\Start-Project.ps1
```

Open <http://127.0.0.1:5173>. API documentation is at <http://127.0.0.1:8000/docs>.

The app opens with a login screen when there is no valid browser session. Sign in with username `demo` or email `demo@caseledger.local`. Display the generated application password with:

```powershell
.\scripts\Show-LoginCredentials.ps1
```

The application password is separate from the MySQL root password. Sign out using the sidebar button. An active session survives page refreshes and expires after eight hours; the cookie is a browser session cookie.

The startup script uses a separate MySQL account with SELECT and INSERT permissions on this project's database and UPDATE/DELETE permissions on auth_sessions for session cleanup and logout. Its credential, the reset root credential, and the demo login credential are encrypted with Windows protection for the current Windows user in `.local`. This folder is excluded from Git. Keep the encrypted credentials on this computer; they cannot be used as portable project credentials.

To see the generated root password locally, run:

```powershell
.\scripts\Show-MySqlPassword.ps1
```

For MySQL Workbench, connect to `127.0.0.1`, port `3306`, username `root`, using that password. The old stored Workbench password must be replaced.

To open the MySQL command line using the encrypted root credential:

```powershell
.\scripts\Open-MySql.ps1
```

Query output is saved in `docs/MYSQL_VERIFICATION.txt`. Live check results are in `docs/LIVE_VERIFICATION.txt`.
Authentication results are saved in `docs/LOGIN_VERIFICATION.txt`.

## Manual setup on another computer

The project files and dependencies are already in this folder. React packages are in `frontend/node_modules`. FastAPI and MySQL Connector/Python are in `backend/.venv`.

## 1. Prepare MySQL once

In MySQL Workbench, run `sql/schema.sql` and then `sql/seed.sql`. The second file adds fictional records for the demonstration. Run `sql/verify.sql` if you want to inspect the six tables, trigger result, view, join, and recursive appeal query.

Run `.\scripts\Setup-Login.ps1` from the project folder after the backend dependencies are installed. On another Windows computer it asks for a MySQL administrator password to create the demo account and authentication tables.

## 2. Start the backend

Open PowerShell and run:

```powershell
Set-Location 'C:\Users\alwan\Documents\court case app\backend'
$env:DB_USER = Read-Host 'MySQL user'
$securePassword = Read-Host 'MySQL password' -AsSecureString
$env:DB_PASSWORD = [System.Net.NetworkCredential]::new('', $securePassword).Password
.\.venv\Scripts\python.exe -m uvicorn main:app
```

Check `http://127.0.0.1:8000/api/health`. It should show `{"status":"ready"}` after the database has been created.

## 3. Start the frontend

Open a second PowerShell window and run:

```powershell
Set-Location 'C:\Users\alwan\Documents\court case app\frontend'
npm run dev
```

Open the local address shown by Vite, usually `http://localhost:5173`.

The MySQL password is requested at runtime. It is not stored in a project file. For the design explanation and viva sequence, read `README.md` and `docs/DBMS_DESIGN.md`.
