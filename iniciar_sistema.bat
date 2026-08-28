@echo off
title facIAL Secure - Iniciador de Servidores
color 0A
echo =======================================================
echo          INICIANDO SERVIDORES DE FACIAL SECURE
echo =======================================================
echo.

echo [1/2] Iniciando base de datos PostgreSQL...
"C:\Program Files\PostgreSQL\17\bin\pg_ctl.exe" -D "C:\PostgreSQL_Data\data" -l "C:\PostgreSQL_Data\pg.log" start
echo.

echo [2/2] Iniciando servidor web de Django...
python manage.py runserver 0.0.0.0:8000

pause
