@echo off
REM lancer_agents_complet.bat
REM Lance FreeLLMAPI + 2 agents extraction + 1 vérificateur
REM PRÉREQUIS : FreeLLMAPI doit être démarré d'abord via demarrer_freellmapi.bat

cd /d "c:\Users\DANIEL\Documents\Mes projets\ScrapperBF"

echo ============================================================
echo   ETAPE 1 : Vérification FreeLLMAPI (port 3001)
echo ============================================================

REM Tester si FreeLLMAPI répond
curl -s -o nul -w "%%{http_code}" --connect-timeout 3 http://127.0.0.1:3001/v1/models 2>nul > .freellm_status.tmp
set /p STATUS=<.freellm_status.tmp
del .freellm_status.tmp 2>nul

if "%STATUS%"=="200" (
    echo   FreeLLMAPI UP [status %STATUS%] - OK
) else (
    echo.
    echo   ATTENTION : FreeLLMAPI n'est pas accessible sur port 3001 !
    echo.
    echo   Solutions :
    echo     A) Lancer demarrer_freellmapi.bat dans une autre fenetre
    echo     B) Ouvrir l'appli FreeLLMAPI Desktop
    echo.
    echo   Si FreeLLMAPI n'est pas pret, les agents utiliseront Codelink.
    echo   ATTENTION : La cle Codelink actuelle est epuisee (429).
    echo   Il faut soit une nouvelle cle, soit FreeLLMAPI.
    echo.
    pause
)

echo.
echo ============================================================
echo   ETAPE 2 : Lancement des 3 agents
echo ============================================================

REM Agent 2025 — 8 workers parallèles
start "Extraction-2025" cmd /k "cd /d "c:\Users\DANIEL\Documents\Mes projets\ScrapperBF" && python agent_extraction_md.py --annee 2025 --workers 8"

REM Pause 3s entre les deux agents
timeout /t 3 /nobreak >nul

REM Agent 2026 — 6 workers parallèles
start "Extraction-2026" cmd /k "cd /d "c:\Users\DANIEL\Documents\Mes projets\ScrapperBF" && python agent_extraction_md.py --annee 2026 --workers 6"

REM Vérificateur live (démarre 15s après pour laisser les premiers inserts arriver)
timeout /t 15 /nobreak >nul
start "Verificateur-Live" cmd /k "cd /d "c:\Users\DANIEL\Documents\Mes projets\ScrapperBF" && python agent_verificateur_live.py --intervalle 20 --batch 30"

echo.
echo   3 agents lancés dans des fenêtres séparées.
echo   Logs : logs_agent_extraction_*.log  et  logs_verificateur_live.log
echo   Audit : audit_log.jsonl
echo.
pause
