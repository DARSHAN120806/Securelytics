@echo off
REM Rebuild the model comparison table + charts and EDA charts from already-trained models (~1-2 min).
cd /d "%~dp0"
call .venv\Scripts\activate.bat || goto :error
set PYTHONPATH=src
set PYTHONIOENCODING=utf-8
chcp 65001 >nul
python -m securelytics.report || goto :error
python -m securelytics.eda || goto :error
echo.
echo DONE. See reports\model_comparison.md and the charts in reports\
pause
exit /b 0
:error
echo.
echo FAILED - copy the error above and send it to Claude.
pause
exit /b 1
