@echo off
setlocal
"%~dp0Caddy\caddy.exe" run --config "%ProgramData%\NorthstarDesk\Caddyfile" --adapter caddyfile 1>>"%ProgramData%\NorthstarDesk\caddy.out.log" 2>>"%ProgramData%\NorthstarDesk\caddy.err.log"
