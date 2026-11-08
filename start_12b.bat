@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem Granthsagar - motha model (gemma3:12b). 16 GB RAM lagte.
where ollama >nul 2>nul || (echo Ollama install nahi. https://ollama.com varun install kara. & pause & exit /b)
echo gemma3:12b tapasat aahe (pahilyanda ~8 GB download, internet lagel)...
ollama pull gemma3:12b
ollama pull bge-m3
echo Python packages tapasat aahe...
python -m pip install --quiet --disable-pip-version-check pypdfium2 pillow numpy
set TESS=
where tesseract >nul 2>nul && set TESS=1
if exist "C:\Program Files\Tesseract-OCR\tesseract.exe" set TESS=1
if not defined TESS (
  echo PDF OCR sathi Tesseract install karat aahe - ekdach...
  winget install -e --id UB-Mannheim.TesseractOCR --accept-package-agreements --accept-source-agreements || echo Tesseract install zala nahi - PDF jodnyasathi https://github.com/UB-Mannheim/tesseract/wiki varun install kara.
)
if not exist granth mkdir granth
if not exist pdf_inbox mkdir pdf_inbox
set GS_CHAT_MODEL=gemma3:12b
python granthsagar.py
pause
