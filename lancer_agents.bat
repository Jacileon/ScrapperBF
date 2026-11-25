@echo off
REM lancer_agents.bat — Lance les 3 agents (2025, 2026, vérificateur) en parallèle
REM Prérequis : FreeLLMAPI sur port 3001 OU DEEPSEEK_API_KEY dans .env
REM             Python 3.13 dans le PATH

cd /d "c:\Users\DANIEL\Documents\Mes projets\ScrapperBF"

echo ============================================================
echo   LANCEMENT DES 3 AGENTS EXTRACTIONS + VERIFICATEUR
echo ============================================================
echo.

REM Agent 2025 — 8 workers parallèles
start "Agent-2025" cmd /k "python agent_extraction_md.py --annee 2025 --workers 8"

REM Agent 2026 — 6 workers parallèles (moins de PDFs)
start "Agent-2026" cmd /k "python agent_extraction_md.py --annee 2026 --workers 6"

REM Vérificateur live (démarre 10s après pour laisser les premiers inserts arriver)
timeout /t 10 /nobreak >nul
start "Verificateur-Live" cmd /k "python agent_verificateur_live.py --intervalle 20 --batch 30"

echo.
echo Agents lancés dans 3 fenêtres séparées.
echo Logs : logs_agent_extraction_*.log  et  logs_verificateur_live.log
echo Audit : audit_log.jsonl
echo.
pause
