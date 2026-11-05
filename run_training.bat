@echo off
REM One-click training on Windows: cleans data, builds features, trains all 4 models, makes charts.
cd /d "%~dp0"
if not exist .venv\Scripts\activate.bat (
  echo Creating virtual environment and installing libraries - first time only...
  python -m venv .venv || goto :error
  call .venv\Scripts\activate.bat
  pip install -r requirements.txt -r requirements-boosting.txt || goto :error
) else (
  call .venv\Scripts\activate.bat
)
set PYTHONPATH=src
set PYTHONIOENCODING=utf-8
chcp 65001 >nul
echo.
echo [1/3] Cleaning data and building features...
python -m securelytics.prepare || goto :error
echo.
echo [2/3] Training and comparing the 4 models (10-20 min)...
python -m securelytics.train || goto :error
echo.
echo [3/3] EDA charts...
python -m securelytics.eda || goto :error
echo.
echo DONE. Results: reports\model_comparison.md
type reports\model_comparison.md
pause
exit /b 0
:error
echo.
echo FAILED - copy the error above and send it to Claude.
pause
exit /b 1
