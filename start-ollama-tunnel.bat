@echo off
REM Start Cloudflare quick tunnel for Ollama (port 11434)
REM This gives a random trycloudflare.com URL each time.
REM Run once after boot, then update EC2 Prisma AI Settings base_url with the new URL.
REM The URL is logged to: %USERPROFILE%\cloudflared-tunnel.log

start "" /B "C:\Program Files (x86)\cloudflared\cloudflared.exe" ^
  tunnel --url http://localhost:11434 --no-autoupdate ^
  > "%USERPROFILE%\cloudflared-tunnel.log" 2>&1
