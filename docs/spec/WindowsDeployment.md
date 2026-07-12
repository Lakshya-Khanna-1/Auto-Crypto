# WindowsDeployment.md

Target: Windows Server (2019+), no Docker, admin PowerShell for setup steps.

## 1. Prerequisites (manual checkpoint — implementation model stops and asks user)
1. Install Python 3.12 x64 from python.org — check "Add to PATH". Verify: `python --version`.
2. Install Git for Windows. Verify: `git --version`.
3. Install Ollama for Windows (ollama.com installer). Verify: `ollama --version`.
4. Download NSSM 2.24 (nssm.cc), place `nssm.exe` in `C:\tools\nssm\`, add to PATH.

## 2. Project setup
```powershell
git clone <repo> C:\cryptotrader
cd C:\cryptotrader
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-dev.txt
copy .env.example .env        # user fills secrets later; paper mode works empty
copy config\config.example.yaml config\config.yaml
alembic upgrade head
```

## 3. Ollama configuration
System env vars (System Properties → Environment Variables), then restart Ollama:
- `OLLAMA_MAX_LOADED_MODELS=1`
- `OLLAMA_KEEP_ALIVE=30m`
Pull models per AILayer.md §1. Verify: `ollama run llama3.2:3b "say ok"`.

## 4. Install services (scripts/install_service.ps1 — authoritative content)
```powershell
nssm install tradecore "C:\cryptotrader\.venv\Scripts\python.exe" "-m tradecore"
nssm set tradecore AppDirectory C:\cryptotrader
nssm set tradecore AppStdout C:\cryptotrader\data\logs\service-out.log
nssm set tradecore AppStderr C:\cryptotrader\data\logs\service-err.log
nssm set tradecore AppRotateFiles 1
nssm set tradecore AppRotateBytes 10485760
nssm set tradecore AppExit Default Restart
nssm set tradecore AppRestartDelay 5000
nssm set tradecore Start SERVICE_AUTO_START
nssm start tradecore
```
(Ollama's installer already registers itself to run at login; if running as a true
service is desired, mirror the nssm pattern for `ollama serve`.)

## 5. Ops runbook
| Task | Command |
|------|---------|
| Status / logs | `nssm status tradecore`; tail files in data\logs\ |
| Restart after config edit | `nssm restart tradecore` |
| Update code | `git pull; pip install -r requirements.txt; alembic upgrade head; nssm restart tradecore` |
| Dashboard | http://127.0.0.1:8080 |

## 6. Windows-specific pitfalls (implementation model must handle)
- Use `pathlib` everywhere; never hardcode `/` paths.
- asyncio on Windows: set `WindowsSelectorEventLoopPolicy` if any lib requires it; test at M1.
- Long path support: keep repo at C:\cryptotrader (short root).
- Firewall: dashboard on 127.0.0.1 needs no rule; document the rule needed if user opts into LAN.
