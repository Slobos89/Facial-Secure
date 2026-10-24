@echo off
title facIAL Secure - Configurador de PC Nuevo
color 0B
echo =======================================================
echo     FACIAL SECURE - INSTALADOR / CONFIGURADOR
echo =======================================================
echo.
echo Este asistente preparara el entorno completo para ejecutar
echo facIAL Secure en esta computadora (Deep Learning + Base de Datos).
echo.
pause

echo.
echo [1/3] Verificando instalacion de Python...
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

echo [2/3] Instalando librerias y dependencias necesarias...
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

echo [3/3] Ejecutando diagnostico, creacion de BD, modelos y migraciones...
python setup_env.py
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
