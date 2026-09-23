@echo off
setlocal
"%~dp0NorthstarDeskServer.exe" serve --data-root "%ProgramData%\NorthstarDesk" 1>>"%ProgramData%\NorthstarDesk\server.out.log" 2>>"%ProgramData%\NorthstarDesk\server.err.log"
