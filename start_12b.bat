@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Granthsagar
where python >nul 2>nul || (echo [X] Python nahi. https://python.org varun install kara ^(install kartana "Add Python to PATH" tick kara^). & pause & exit /b)
where ollama >nul 2>nul || (echo [X] Ollama nahi. https://ollama.com varun install kara. & pause & exit /b)

echo.
echo ===== [1/3] PDF sathi sadhane =====
echo pypdfium2, pillow, numpy install/tapasat aahe...
python -m pip install --disable-pip-version-check -q pypdfium2 pillow numpy
python granthsagar.py --check-setup
if %errorlevel%==0 goto tools_ok
set "TESS=C:\Program Files\Tesseract-OCR\tesseract.exe"
if exist "%TESS%" goto tools_recheck
where winget >nul 2>nul || goto no_winget
echo.
echo Tesseract OCR install karat aahe (ekdach, 1-2 minute; Windows "Yes" vicharu shakto)...
winget install -e --id UB-Mannheim.TesseractOCR --accept-package-agreements --accept-source-agreements
goto tools_recheck
:no_winget
echo [!] winget nahi. Tesseract https://github.com/UB-Mannheim/tesseract/wiki varun install kara (Next-Next).
:tools_recheck
python granthsagar.py --check-setup
if not %errorlevel%==0 (
  echo.
  echo [!] PDF sadhane apurna aahet. Granthsagar chalel, pan PDF jodta yenar nahit.
  echo     Tesseract install kelyavar hi file punha chalva.
  pause
)
:tools_ok

echo.
echo ===== [2/3] AI models (pahilyanda ~8 GB download, internet lagel) =====
ollama pull gemma3:12b
ollama pull bge-m3
set GS_CHAT_MODEL=gemma3:12b

if not exist granth mkdir granth
if not exist pdf_inbox mkdir pdf_inbox
echo.
echo ===== [3/3] Granthsagar suru =====
echo PDF chi pragati ithe ani browser madhe varti disel. Hi kali khidki band karu naka.
python granthsagar.py
pause
