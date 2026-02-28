@echo off
REM Extract the current tunnel URL from the log and print it
findstr /C:"trycloudflare.com" "%USERPROFILE%\cloudflared-tunnel.log" 2>nul | findstr "https"
