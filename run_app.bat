@echo off
REM Start Flask app in a new command window and open browser to login page
start "FlaskApp" cmd /k "python app.py"
timeout /t 2 /nobreak >nul
start "" "http://localhost:5000/login"
exit /b 0
