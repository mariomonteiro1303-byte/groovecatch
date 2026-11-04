@echo off
setlocal
REM Detecta Python 3.12 se existir; caso contrário usa a versão padrão do Launcher (ex.: 3.14).
REM Cria o ambiente virtual local, instala dependências e inicia o servidor Flask.
cd /d "%~dp0"

set "PYTHON_CMD="

REM Tenta primeiro a versão recomendada, caso esteja instalada no Python Launcher.
where py >nul 2>nul
if not errorlevel 1 (
  py -3.12 -c "import sys; print(sys.version)" >nul 2>nul && set "PYTHON_CMD=py -3.12"
  if not defined PYTHON_CMD py -3 -c "import sys; print(sys.version)" >nul 2>nul && set "PYTHON_CMD=py -3"
)

REM Se o launcher não estiver disponível, tenta o comando python no PATH.
if not defined PYTHON_CMD (
  where python >nul 2>nul
  if not errorlevel 1 python -c "import sys; print(sys.version)" >nul 2>nul && set "PYTHON_CMD=python"
)

if not defined PYTHON_CMD (
  echo Nao encontrei uma instalacao funcional do Python.
  echo Verifique os comandos abaixo no Prompt de Comando:
  echo   py -0p
  echo   python --version
  echo Se o comando python abrir a Microsoft Store, desative os aliases de execucao em Configuracoes do Windows ^> Aplicativos ^> Configuracoes avancadas de aplicativos ^> Aliases de execucao de aplicativo.
  pause
  exit /b 1
)

echo Python selecionado: %PYTHON_CMD%
echo O ambiente virtual sera criado nesta pasta: %CD%
if not exist ".venv\Scripts\python.exe" (
  echo Criando ambiente virtual...
  %PYTHON_CMD% -m venv .venv
  if errorlevel 1 (
    echo Nao foi possivel criar o ambiente virtual usando %PYTHON_CMD%.
    echo Confira a instalacao do Python e tente novamente.
    pause
    exit /b 1
  )
)

echo Atualizando pip e instalando dependencias...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 (
  echo Falha ao atualizar pip. Verifique a conexao e tente novamente.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo Falha ao instalar dependencias. Confira a conexao e o arquivo requirements.txt.
  pause
  exit /b 1
)

echo Iniciando GrooveCatch Web em http://127.0.0.1:5000
start "GrooveCatch Web" /D "%~dp0" "%~dp0.venv\Scripts\python.exe" "%~dp0run.py"
timeout /t 2 >nul
start "" http://127.0.0.1:5000
endlocal
