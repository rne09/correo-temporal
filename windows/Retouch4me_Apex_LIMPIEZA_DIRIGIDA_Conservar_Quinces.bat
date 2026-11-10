@echo off
setlocal EnableExtensions
set "MODO_AUTO="
if /I "%~1"=="/AUTO" set "MODO_AUTO=1"
if /I "%~1"=="--auto" set "MODO_AUTO=1"
title Retouch4me Apex - limpiar cuenta e historial conservando presets

echo ============================================================
echo  Retouch4me Apex - limpieza dirigida y segura
echo ============================================================
echo.
echo Este BAT trabaja SOLO con estas claves:
echo   HKCU\Software\Retouch4me Apex
echo   HKCU\Software\Retouch4me Cloud Retouching
echo.
echo Va a:
echo   1. Respaldar ambas claves completas.
echo   2. Guardar aparte los valores de presets.
echo   3. Borrar SOLO email y session de Apex.
echo   4. Borrar SOLO retouch4me_last_job_id_01 a _10.
echo   5. Verificar que el preset Quinces siga registrado.
echo.
echo NO borra preset_0, preset_0_name, reluindex, licencia,
echo creditos, configuracion de modelos ni otros plugins.
echo.

tasklist /FI "IMAGENAME eq Retouch4me Apex.exe" 2>NUL | find /I "Retouch4me Apex.exe" >NUL
if not errorlevel 1 (
    echo [STOP] Retouch4me Apex esta abierto.
    echo Cierra la aplicacion por completo y vuelve a ejecutar este BAT.
    echo.
    if not defined MODO_AUTO pause
    exit /b 2
)

set "BK=%USERPROFILE%\Desktop\Retouch4me_Apex_BACKUP_ANTES_DE_LIMPIAR"
if not exist "%BK%" mkdir "%BK%"

echo [1/5] Creando respaldos completos...
reg export "HKCU\Software\Retouch4me Apex" "%BK%\Retouch4me_Apex_COMPLETO.reg" /y >NUL 2>&1
if errorlevel 1 (
    echo [STOP] No pude respaldar HKCU\Software\Retouch4me Apex
    echo No se borrara nada.
    if not defined MODO_AUTO pause
    exit /b 3
)

reg export "HKCU\Software\Retouch4me Cloud Retouching" "%BK%\Retouch4me_Cloud_Retouching_COMPLETO.reg" /y >NUL 2>&1
if errorlevel 1 (
    echo [STOP] No pude respaldar HKCU\Software\Retouch4me Cloud Retouching
    echo No se borrara nada.
    if not defined MODO_AUTO pause
    exit /b 3
)

echo [2/5] Guardando evidencia de presets...
reg query "HKCU\Software\Retouch4me Apex" /v "preset_0_name" > "%BK%\PRESET_QUINCES_VERIFICACION.txt" 2>&1
reg query "HKCU\Software\Retouch4me Apex" /v "preset_0" >> "%BK%\PRESET_QUINCES_VERIFICACION.txt" 2>&1
reg query "HKCU\Software\Retouch4me Apex" /v "preset_1_name" >> "%BK%\PRESET_QUINCES_VERIFICACION.txt" 2>&1
reg query "HKCU\Software\Retouch4me Apex" /v "preset_1" >> "%BK%\PRESET_QUINCES_VERIFICACION.txt" 2>&1
reg query "HKCU\Software\Retouch4me Apex" /v "reluindex" >> "%BK%\PRESET_QUINCES_VERIFICACION.txt" 2>&1

reg query "HKCU\Software\Retouch4me Apex" /v "preset_0_name" 2>NUL | find /I "Quinces" >NUL
if errorlevel 1 (
    echo [STOP] No pude verificar el preset Quinces antes de limpiar.
    echo No se borrara nada.
    echo Revisa: "%BK%\PRESET_QUINCES_VERIFICACION.txt"
    if not defined MODO_AUTO pause
    exit /b 4
)

echo [OK] Preset Quinces verificado antes de la limpieza.
echo.
echo IMPORTANTE:
echo Se eliminara la sesion local y el correo guardado en Apex.
echo Tambien se limpiara la lista local de trabajos recientes.
echo Los presets NO se tocaran.
echo.
if defined MODO_AUTO (
    echo [AUTO] Limpieza iniciada desde Correo Temporal.
    goto :CONFIRMADO
)
set "CONF="
set /P "CONF=Escribe LIMPIAR para continuar: "
if /I not "%CONF%"=="LIMPIAR" (
    echo.
    echo Cancelado. No se modifico nada.
    echo El respaldo quedo en:
    echo "%BK%"
    if not defined MODO_AUTO pause
    exit /b 0
)

:CONFIRMADO
echo.
echo [3/5] Quitando correo y sesion local de Apex...
reg delete "HKCU\Software\Retouch4me Apex" /v "email" /f >NUL 2>&1
reg delete "HKCU\Software\Retouch4me Apex" /v "session" /f >NUL 2>&1

echo [4/5] Limpiando historial local de trabajos...
for /L %%N in (1,1,9) do (
    reg delete "HKCU\Software\Retouch4me Cloud Retouching" /v "retouch4me_last_job_id_0%%N" /f >NUL 2>&1
)
reg delete "HKCU\Software\Retouch4me Cloud Retouching" /v "retouch4me_last_job_id_10" /f >NUL 2>&1

echo [5/5] Verificando que Quinces siga intacto...
reg query "HKCU\Software\Retouch4me Apex" /v "preset_0_name" 2>NUL | find /I "Quinces" >NUL
if errorlevel 1 (
    echo [AVISO] No pude verificar Quinces despues de la limpieza.
    echo Restaura el respaldo haciendo doble clic en:
    echo "%BK%\Retouch4me_Apex_COMPLETO.reg"
    if not defined MODO_AUTO pause
    exit /b 5
)

echo.
echo ============================================================
echo [OK] LISTO
echo ============================================================
echo.
echo Preset Quinces: CONSERVADO.
echo Correo guardado de Apex: ELIMINADO.
echo Sesion local de Apex: ELIMINADA.
echo Historial local de trabajos: LIMPIADO.
echo.
echo Respaldo completo:
echo "%BK%"
echo.
echo Ahora abre Retouch4me Apex.
echo Si vuelve a aparecer el correo inmediatamente, significa que
echo la app lo esta recuperando desde otra sesion externa y no del
echo registro local que acabamos de limpiar.
echo.
if not defined MODO_AUTO pause
exit /b 0
