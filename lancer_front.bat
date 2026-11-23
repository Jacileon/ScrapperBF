@echo off
title Veille BF - Serveur Front & API Marches Publics
echo ======================================================================
echo  DEMARRAGE DU SERVEUR VEILLE BF (FASTAPI + SQLite)
echo ======================================================================
echo  1. Synchronisation de la base de donnees...
python export_db_to_front.py
echo.
echo  2. Lancement du serveur Web et API REST...
echo  Plateforme accessible sur : http://127.0.0.1:8000
echo ======================================================================
start http://127.0.0.1:8000/dashboard.html
python server_front.py
pause
