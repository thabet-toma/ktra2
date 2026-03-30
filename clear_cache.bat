@echo off
echo Clearing Python cache...
cd /d c:\Users\asus\Desktop\ktra

REM Delete all __pycache__ directories
for /d /r . %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d"

REM Delete all .pyc files
del /s /q *.pyc

echo Cache cleared!
echo.
echo Now restart the Django server:
echo venv\Scripts\python.exe manage.py runserver
pause
