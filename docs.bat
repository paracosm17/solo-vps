@echo off
setlocal
pushd "%~dp0"
if errorlevel 1 exit /b 1
set "NO_MKDOCS_2_WARNING=1"
set "DOCS_ENV_PYTHON=%CD%\.venv-docs\Scripts\python.exe"

if exist "%DOCS_ENV_PYTHON%" goto install
echo Creating the documentation Python environment...
if defined DOCS_PYTHON goto custom_python
py -3 -c "import venv" >nul 2>&1
if not errorlevel 1 goto py_launcher
python -c "import venv" >nul 2>&1
if not errorlevel 1 goto python_path
echo ERROR: Python 3 was not found. Install Python 3.12 or newer from python.org.
echo Enable the Python launcher or add Python to PATH, then run docs.bat again.
echo Alternatively, set DOCS_PYTHON to the full path of an existing python.exe.
goto failed

:custom_python
"%DOCS_PYTHON%" -m venv ".venv-docs"
if errorlevel 1 goto failed
goto install

:py_launcher
py -3 -m venv ".venv-docs"
if errorlevel 1 goto failed
goto install

:python_path
python -m venv ".venv-docs"
if errorlevel 1 goto failed

:install
echo Checking documentation dependencies...
"%DOCS_ENV_PYTHON%" -m pip --disable-pip-version-check install --quiet -r "requirements-docs.txt"
if errorlevel 1 goto failed
if /i "%~1"=="build" goto build
echo.
echo After MkDocs reports that it is serving, open:
echo   http://127.0.0.1:8000/ru/
echo Keep this window open. Press Ctrl+C to stop.
echo.
"%DOCS_ENV_PYTHON%" -m mkdocs serve --dev-addr 127.0.0.1:8000
if errorlevel 1 goto failed
goto success

:build
"%DOCS_ENV_PYTHON%" -m mkdocs build --strict
if errorlevel 1 goto failed

:success
popd
exit /b 0

:failed
echo.
echo Documentation could not start or build. See the error above.
if not defined DOCS_NO_PAUSE pause
popd
exit /b 1
