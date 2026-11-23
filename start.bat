@echo off
chcp 65001 >nul
cd /d "%~dp0"
"C:\Users\misha\AppData\Local\Programs\Python\Python310\python.exe" ask.py %*
pause
