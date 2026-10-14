@echo off
color 0B
title WIKMAZ IronUSB Immortal V25 - Launcher
cd /d "%~dp0"
if exist "WIKMAZ_IronUSB_Immortal.exe" (
    start "" "WIKMAZ_IronUSB_Immortal.exe"
    exit
)
cd backend
"C:\Program Files\Python314\python.exe" core.py
