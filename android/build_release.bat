@echo off
setlocal
chcp 65001 >nul
set "ANDROID_DIR=%~dp0"
set "PROJECT_ROOT=%~dp0.."
set "LINK=C:\hsj-android"

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python is required to generate icons.
    exit /b 1
)

if not exist "%ANDROID_DIR%keystore\keystore.properties" (
    echo [ERROR] Missing keystore\keystore.properties
    exit /b 1
)
if not exist "%ANDROID_DIR%keystore\hsj-release.jks" (
    echo [ERROR] Missing keystore\hsj-release.jks
    exit /b 1
)

set "JAVA_HOME="
for /d %%D in ("%ANDROID_DIR%.toolchain\jdk21\jdk-*") do set "JAVA_HOME=%%~fD"
if not defined JAVA_HOME (
    echo [ERROR] Missing local JDK 21 under android\.toolchain\jdk21
    exit /b 1
)

if not exist "%LINK%\.%" (
    mklink /J "%LINK%" "%ANDROID_DIR%." >nul
    if errorlevel 1 (
        echo [ERROR] Could not create junction %LINK%
        exit /b 1
    )
)

echo Generating icon assets...
python "%PROJECT_ROOT%\tools\make_icons.py"
if errorlevel 1 exit /b 1
python "%ANDROID_DIR%tools\make_android_icons.py"
if errorlevel 1 exit /b 1

cd /d "%LINK%"
if exist "gradle\wrapper\gradle-wrapper.jar" (
    call gradlew.bat :app:assembleRelease
) else (
    where gradle >nul 2>nul
    if errorlevel 1 (
        echo [ERROR] Gradle 8.14.5 not found. Install it or run: gradle wrapper
        exit /b 1
    )
    call gradle :app:assembleRelease
)
if errorlevel 1 exit /b 1

if not exist "%PROJECT_ROOT%\dist-android" mkdir "%PROJECT_ROOT%\dist-android"
copy /y "%LINK%\app\build\outputs\apk\release\app-release.apk" ^
    "%PROJECT_ROOT%\dist-android\HSJConverter-Android-1.0.0.apk" >nul
if errorlevel 1 exit /b 1

echo.
echo APK: %PROJECT_ROOT%\dist-android\HSJConverter-Android-1.0.0.apk
endlocal
