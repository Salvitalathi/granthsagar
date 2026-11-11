@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Granthsagar - chukichi chitre saaf kara
echo Granthsagar band asel tarach he chalva (kali khidki band kara).
echo.
echo ===== [1/2] Tapasani (kahihi badalat nahi) =====
python scripts\fix_figures.py
echo.
choice /C YN /M "Durusti karaychi ka? (Y = ho, N = nahi)"
if errorlevel 2 goto end
echo.
echo ===== [2/2] Durusti =====
python scripts\fix_figures.py --apply
echo.
echo Aata start.bat chalva - fakt ti pane punha OCR hotil.
:end
pause
