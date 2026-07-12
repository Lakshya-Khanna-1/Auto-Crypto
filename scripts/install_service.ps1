# PowerShell Service Installer script for Auto-Crypto platform using NSSM
# Run this script as Administrator to install.

$ServiceName = "tradecore"
$NssmExecutable = "nssm.exe"

# Resolve absolute paths
$AppDirectory = "c:\Users\Admitrator\Desktop\auto crypto trader"
$PythonExecutable = "$AppDirectory\.venv\Scripts\python.exe"
$StdoutLog = "$AppDirectory\data\logs\service-out.log"
$StderrLog = "$AppDirectory\data\logs\service-err.log"

# Check if NSSM is available in PATH
$HasNssm = Get-Command $NssmExecutable -ErrorAction SilentlyContinue
if (-not $HasNssm) {
    # Fallback to look for nssm.exe in the AppDirectory root
    if (Test-Path "$AppDirectory\nssm.exe") {
        $NssmExecutable = "$AppDirectory\nssm.exe"
    } else {
        Write-Error "nssm.exe was not found in Windows PATH or at '$AppDirectory\nssm.exe'."
        Write-Output "Please configure NSSM or place a copy of nssm.exe in the project folder root."
        exit 1
    }
}

# Ensure log directory exists
$LogDirectory = "$AppDirectory\data\logs"
if (-not (Test-Path $LogDirectory)) {
    New-Item -ItemType Directory -Force -Path $LogDirectory | Out-Null
}

# Install service via NSSM
Write-Output "Installing Windows Service '$ServiceName'..."
& $NssmExecutable install $ServiceName "$PythonExecutable" "-m tradecore"
& $NssmExecutable set $ServiceName AppDirectory "$AppDirectory"
& $NssmExecutable set $ServiceName AppStdout "$StdoutLog"
& $NssmExecutable set $ServiceName AppStderr "$StderrLog"
& $NssmExecutable set $ServiceName AppRotateFiles 1
& $NssmExecutable set $ServiceName AppRotateOnline 1
& $NssmExecutable set $ServiceName AppRotateBytes 10485760 # 10MB rotation

Write-Output "Service '$ServiceName' registered successfully."
Write-Output "To start the service, run: Start-Service $ServiceName"
