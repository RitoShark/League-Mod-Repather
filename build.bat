@echo off
echo ========================================
echo   League Mod Repather - Build Script
echo ========================================
echo.

REM Clean previous builds
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

REM Build the exe
echo Building EXE...
pyinstaller --clean build.spec

if %errorlevel% equ 0 (
    echo.
    echo ========================================
    echo   Build Complete!
    echo   EXE: dist\LeagueModRepather.exe
    echo ========================================
) else (
    echo.
    echo ========================================
    echo   Build Failed!
    echo ========================================
)

pause

