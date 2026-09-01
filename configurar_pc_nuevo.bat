@echo off
title facIAL Secure - Configurador de PC Nuevo
color 0B
echo =======================================================
echo     FACIAL SECURE - INSTALADOR / CONFIGURADOR
echo =======================================================
echo.
echo Este asistente preparara el entorno para ejecutar
echo el sistema en esta computadora.
echo.
pause

echo.
echo [1/4] Verificando instalacion de Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    color 0C
    echo [ERROR] No se detecto Python instalado o no esta en el PATH.
    echo Por favor instala Python 3.10 o superior y marca la casilla "Add Python to PATH".
    echo.
    pause
    exit /b
)
echo Python detectado correctamente.
echo.

echo [2/4] Instalando librerias y dependencias necesarias...
python -m pip install --upgrade pip
pip install -r requeriments.txt
if %errorlevel% neq 0 (
    echo.
    echo [ADVERTENCIA] Ocurrio un inconveniente al instalar algunas librerias.
    echo Verifica tu conexion a internet e intenta nuevamente.
    echo.
) else (
    echo Librerias instaladas exitosamente.
)
echo.

echo [3/4] Creando carpetas de almacenamiento y seguridad...
if not exist "media" mkdir "media"
if not exist "media\rostros" mkdir "media\rostros"
if not exist "media\rostros_recortados" mkdir "media\rostros_recortados"
if not exist "media\secure" mkdir "media\secure"
if not exist "modelo" mkdir "modelo"
echo Carpetas verificadas.
echo.

echo [4/4] Aplicando migraciones y configurando la Base de Datos...
python manage.py migrate
if %errorlevel% neq 0 (
    echo.
    echo [AVISO] No se pudo conectar a PostgreSQL con la configuracion por defecto.
    echo Si instalaste PostgreSQL con otra contrasena o puerto, ajustala en facial_secure/settings.py.
    echo.
) else (
    echo Base de datos sincronizada correctamente.
)
echo.

echo =======================================================
echo               CONFIGURACION COMPLETADA
echo =======================================================
echo.
echo Deseas crear un usuario Administrador ahora? (S/N)
set /p crear_admin="Respuesta: "
if /i "%crear_admin%"=="S" (
    echo.
    python manage.py createsuperuser
)

echo.
echo =======================================================
echo Todo listo. Para iniciar el sistema en el futuro,
echo simplemente haz doble clic en: iniciar_sistema.bat
echo =======================================================
echo.
pause
