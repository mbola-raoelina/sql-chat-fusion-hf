@echo off
REM Batch script for pushing to both HF Space and GitHub

if "%~1"=="" (
    echo Usage: push_both.bat "Your commit message"
    exit /b 1
)

set COMMIT_MESSAGE=%~1

echo ========================================
echo   Deploy Bedrock Enhanced to HF + GitHub
echo ========================================
echo.

echo [1/3] Adding all changes...
git add .

echo.
echo [2/3] Committing changes...
git commit -m "%COMMIT_MESSAGE%"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [INFO] No changes to commit
    goto :end
)

echo.
echo [3/3] Pushing to both repositories...

echo   -^> Pushing to Hugging Face Spaces...
git push origin main -f

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Hugging Face push failed!
    goto :end
)

echo   [OK] HF Space updated!
echo.
echo   -^> Pushing to GitHub...
git push github main -f

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] GitHub push failed!
    goto :end
)

echo   [OK] GitHub updated!
echo.
echo ========================================
echo   DEPLOYMENT SUCCESSFUL!
echo ========================================
echo.
echo Live URLs:
echo   - HF Space: https://huggingface.co/spaces/Mbola/sql-generation-oracle-fusion
echo   - GitHub: https://github.com/mbola-raoelina/sql-chat-fusion-hf
echo.

:end
echo.

