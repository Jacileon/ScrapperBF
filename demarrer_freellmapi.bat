@echo off
REM demarrer_freellmapi.bat
REM Lance FreeLLMAPI en arrière-plan (fenêtre minimisée persistante)
REM GARDE la fenêtre ouverte — NE PAS FERMER cette fenêtre pendant l'extraction !

cd /d "C:\Users\DANIEL\Documents\freellmapi"

echo ============================================================
echo   FreeLLMAPI — Démarrage du serveur proxy LLM
echo   Port : http://127.0.0.1:3001
echo   Dashboard : http://localhost:3001 (créer un compte)
echo   Clé proxy : freellmapi-c21bc5d80eee46e05e4ff134a1e7c66deea77b79c246f0c8
echo ============================================================
echo.
echo NE PAS FERMER CETTE FENETRE pendant l'extraction !
echo.

set ENCRYPTION_KEY=81177bc66ef963724176bfa43fe94edaf9daeb60cf51ed262e5682a39fe96aed
set PORT=3001

node_modules\.bin\tsx.cmd watch server\src\index.ts
