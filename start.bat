@echo off
chcp 65001 >nul
cd /d "%~dp0"
where ollama >nul 2>nul || (echo Ollama install nahi. https://ollama.com varun install kara. & pause & exit /b)
echo Models tapasat aahe (pahilyanda download honar, internet lagel)...
for /f %%m in ('python granthsagar.py --print-model') do (echo Model: %%m & ollama pull %%m)
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
python granthsagar.py
pause
