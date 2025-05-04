@echo off
echo Restarting API server...

REM Change to the discordbot directory
cd /d %~dp0

REM Check for running API server processes
echo Checking for running API server processes...
tasklist /fi "imagename eq python.exe" /v | findstr "api_server"

REM Start the API server
echo Starting API server...
start python run_unified_api.py

echo API server restart complete.
