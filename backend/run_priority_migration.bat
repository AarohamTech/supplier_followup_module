@echo off
REM One-shot: normalize legacy P0-P3 task/mail priorities on the configured DB.
REM DATABASE_URL comes from backend\.env (currently points at production Supabase).
cd /d "%~dp0"
echo === DRY RUN (counts only, no changes) ===
.venv\Scripts\python.exe -m scripts.migrate_task_priorities
echo.
echo === APPLYING (P0/P1-^>HIGH, P2-^>MEDIUM, P3-^>LOW) ===
.venv\Scripts\python.exe -m scripts.migrate_task_priorities --yes
echo.
pause
