@echo off
chcp 65001 >nul
cd /d "%~dp0"
where ollama >nul 2>nul || (echo Ollama install nahi. https://ollama.com varun install kara. & pause & exit /b)
echo Models tapasat aahe (pahilyanda download honar, internet lagel)...
ollama pull qwen2.5:7b
ollama pull bge-m3
if not exist granth mkdir granth
python granthsagar.py
pause
