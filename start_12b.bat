@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem Granthsagar - motha model (gemma3:12b). 16 GB RAM lagte.
where ollama >nul 2>nul || (echo Ollama install nahi. https://ollama.com varun install kara. & pause & exit /b)
echo gemma3:12b tapasat aahe (pahilyanda ~8 GB download, internet lagel)...
ollama pull gemma3:12b
ollama pull bge-m3
if not exist granth mkdir granth
set GS_CHAT_MODEL=gemma3:12b
python granthsagar.py
pause
