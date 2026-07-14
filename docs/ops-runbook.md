# Auto-Crypto Platform Operations Runbook

This operations runbook provides instruction on managing, monitoring, triggering emergency controls, and recovering the Auto-Crypto platform on Windows Server.

---

## 🚦 System Service Control

### 1. Starting the Application
To start the FastAPI backend service and the background scheduler tasks:
```powershell
# Navigate to the workspace
cd "C:\Users\Admitrator\Desktop\auto crypto trader"

# Activate the virtual environment
.venv\Scripts\activate

# Run the tradecore main module
python -m tradecore
```
The server binds to the configured port (default `8080`) and is accessible in the browser at:
`http://127.0.0.1:8080/dashboard/static/index.html`

### 2. Stopping the Application
To stop the server run loop:
- **Interactive Console Mode**: Press `Ctrl+C` in the running PowerShell terminal to trigger a graceful shutdown sequence.
- **Process Termination**: If running in the background, identify and terminate the Python process:
  ```powershell
  # Find the Process ID (PID)
  Get-Process -Name "python" | Select-ID, CommandLine
  # Terminate processes
  Stop-Process -Id <PID>
  ```
The platform handles exit signals cleanly: canceling WebSocket streams, pausing scheduler tasks, and notifying operators via Telegram.

### 3. Restarting the Application
Execute a clean restart:
1. Stop the application task (using `Ctrl+C` or PID termination).
2. Check that no stray python worker handles are locking the database:
   ```powershell
   Get-Process python -ErrorAction SilentlyContinue
   ```
3. Boot the application:
   ```powershell
   python -m tradecore
   ```

---

## 📝 Directory Log Files

All logs printed by modules within `tradecore` are routed dynamically to stdout/stderr and file writers:
- **Default Location**: Logs are written directly to stdout and mapped to files using target logging. (Standard configuration logs are routed as specified in system policies, e.g., standard platform outputs).
- **Log Level Config**: Modify target log levels in `config/config.yaml` or change the `logging.config` setup in your environment.
- **Key Modules to Watch**:
  - `tradecore.scheduler.jobs`: Job execution reports (candle sync, ticker poll, strategy ticks).
  - `tradecore.riskengine.killswitch`: Watchdog logs, drawdown violations, and killswitch locks.
  - `tradecore.execution.tracker`: Trade execution logs, fills, fees, and balance snapshots.
  - `tradecore.ailayer`: Ollama API client outputs and report generation failures.

---

## 🚨 Risk Isolation & Recovery Procedures

### 1. Manually Triggering the Kill-Switch
If market conditions necessitate emergency manual system freeze:
- **Via Dashboard**: Click the prominent red **KILL SWITCH** button in the dashboard header, click confirm on the alert.
- **Via API Payload**: Send a POST request to the killswitch endpoint:
  ```powershell
  Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8080/api/killswitch"
  ```
*This flattens all open positions immediately and halts strategy generation.*

### 2. Recovering & Re-arming the Platform
Once risk factors are resolved and execution can resume:
1. Navigate to the dashboard.
2. Click **Re-arm Engine**.
3. Type the authorization confirmation string `RE-ARM` inside the modal.
4. Click **Re-arm Engine** to submit.
   - Alternatively, trigger via API:
     ```powershell
     Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8080/api/killswitch/rearm" -ContentType "application/json" -Body '{"confirmation": "RE-ARM"}'
     ```

---

## 🛠️ Crash Recovery & Database Integrity

### 1. Database Locking issues
If the server crashes unexpectedly, SQLite databases may hold lingering journal handles:
1. Halt the platform process.
2. Locate the workspace db `tradecore.db`.
3. If an temporary SQLite `.db-wal` or `.db-shm` journal exists, ensure the python process is completely dead before clean start.
4. Test integrity via check script:
   ```powershell
   python -m tradecore --selfcheck
   ```

### 2. Out-of-Sync Reconciliation
At startup, `LiveAdapter` performs automated inventory reconciliation. If orders were cleared manually on the exchange while the platform was offline, startup checks will trigger a mismatch alarm. Refer to `TestingPlan.md` or contact system administrators to resolve mismatches.
