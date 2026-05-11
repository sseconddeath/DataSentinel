@echo off
chcp 65001 >nul
echo ============================================
echo   DataSentinel — Сборка установщика
echo ============================================
echo.

:: 1. Очистка старой сборки
echo [1/4] Очистка...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist installer_output rmdir /s /q installer_output
echo       Готово.
echo.

:: 2. Встраиваем Groq-ключ из secrets.local в ai_assistant.py
echo [2/4] Встраиваем секреты...
.venv\Scripts\python.exe build_inject.py inject
if errorlevel 1 (
    echo.
    echo ОШИБКА: не удалось встроить ключ. Проверьте secrets.local
    pause
    exit /b 1
)
echo.

:: 3. PyInstaller — собираем .exe со встроенным ключом
echo [3/4] PyInstaller...
.venv\Scripts\pyinstaller.exe DataSentinel.spec
set "PYI_ERR=%errorlevel%"

:: ВАЖНО: stub возвращается ВСЕГДА, даже если PyInstaller упал,
:: иначе ключ останется в исходниках на диске.
echo.
echo [restore] Возврат stub в ai_assistant.py...
.venv\Scripts\python.exe build_inject.py restore
echo.

if not "%PYI_ERR%"=="0" (
    echo ОШИБКА: PyInstaller завершился с кодом %PYI_ERR%.
    pause
    exit /b 1
)
echo       Готово.
echo.

:: 4. Сборка установщика (Inno Setup)
where iscc >nul 2>&1
if errorlevel 1 (
    if exist "C:\Program Files\Inno Setup 7\ISCC.exe" (
        set "ISCC=C:\Program Files\Inno Setup 7\ISCC.exe"
    ) else if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (
        set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    ) else if exist "C:\Program Files\Inno Setup 6\ISCC.exe" (
        set "ISCC=C:\Program Files\Inno Setup 6\ISCC.exe"
    ) else (
        echo.
        echo [!] Inno Setup не найден. Установите: https://jrsoftware.org/isdl.php
        echo     Приложение собрано в dist\DataSentinel\
        echo     Можно запустить dist\DataSentinel\DataSentinel.exe
        pause
        exit /b 0
    )
) else (
    set "ISCC=iscc"
)

echo [4/4] Inno Setup...
"%ISCC%" installer.iss
if errorlevel 1 (
    echo.
    echo ОШИБКА: Inno Setup завершился с ошибкой.
    pause
    exit /b 1
)
echo.

echo ============================================
echo   Готово!
echo   Установщик: installer_output\DataSentinel_Setup_1.0.0.exe
echo ============================================
pause
