@echo off
chcp 65001 >nul
cd /d "%~dp0"
where ollama >nul 2>nul || (echo Ollama install nahi. https://ollama.com varun install kara. & pause & exit /b)
echo Models tapasat aahe (pahilyanda download honar, internet lagel)...
for /f %%m in ('python granthsagar.py --print-model') do (echo Model: %%m & ollama pull %%m)
ollama pull bge-m3
if not exist granth mkdir granth
python granthsagar.py
pause
