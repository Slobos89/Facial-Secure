@echo off
title facIAL Secure - Iniciador del Sistema
color 0A
echo =======================================================
echo          INICIANDO SERVIDORES DE FACIAL SECURE
echo =======================================================
echo.

echo [1/2] Verificando / Iniciando PostgreSQL...
if exist "C:\Program Files\PostgreSQL\17\bin\pg_ctl.exe" (
    if exist "C:\PostgreSQL_Data\data" (
        "C:\Program Files\PostgreSQL\17\bin\pg_ctl.exe" -D "C:\PostgreSQL_Data\data" -l "C:\PostgreSQL_Data\pg.log" start >nul 2>&1
    )
)
if exist "C:\Program Files\PostgreSQL\16\bin\pg_ctl.exe" (
    if exist "C:\PostgreSQL_Data\data" (
        "C:\Program Files\PostgreSQL\16\bin\pg_ctl.exe" -D "C:\PostgreSQL_Data\data" -l "C:\PostgreSQL_Data\pg.log" start >nul 2>&1
    )
)
echo Base de datos lista.
echo.

echo [2/2] Iniciando servidor web de Django...
echo URL Local: http://127.0.0.1:8000
echo.
python manage.py runserver 0.0.0.0:8000

pause
