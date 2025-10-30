@echo off
echo Clearing Windows Icon Cache...
echo.

REM Delete icon cache
taskkill /f /im explorer.exe >nul 2>&1
timeout /t 2 /nobreak >nul

REM Delete IconCache.db files
del /f /s /q /a "%localappdata%\IconCache.db" >nul 2>&1
del /f /s /q /a "%localappdata%\Microsoft\Windows\Explorer\iconcache*" >nul 2>&1

echo Icon cache cleared!
echo Restarting Windows Explorer...
start explorer.exe

echo.
echo Done! Your icon should now appear correctly.
echo Please check the LeagueModRepather.exe file.
pause

