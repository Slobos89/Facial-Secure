@echo off
title facIAL Secure - Iniciador del Sistema
color 0A
echo =======================================================
echo          INICIANDO SERVIDORES DE FACIAL SECURE
echo =======================================================
echo.

echo [1/2] Verificando / Iniciando PostgreSQL...
rem Intentar iniciar servicio estándar de Windows
net start postgresql-x64-17 >nul 2>&1
net start postgresql-x64-16 >nul 2>&1
net start postgresql-x64-15 >nul 2>&1

rem Intentar arranque manual por carpeta de datos si aplica
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
echo.
echo =======================================================
echo  facIAL Secure listo en: http://127.0.0.1:8000
echo =======================================================
echo.
python manage.py runserver 0.0.0.0:8000

pause
