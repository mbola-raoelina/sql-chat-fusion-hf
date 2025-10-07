# PowerShell script for pushing to both HF Space and GitHub
param(
    [Parameter(Mandatory=$true)]
    [string]$CommitMessage
)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Deploy Bedrock Enhanced to HF + GitHub" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "[1/3] Adding all changes..." -ForegroundColor Yellow
git add .

Write-Host ""
Write-Host "[2/3] Committing changes..." -ForegroundColor Yellow
git commit -m $CommitMessage

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "[3/3] Pushing to both repositories..." -ForegroundColor Yellow
    
    Write-Host "  -> Pushing to Hugging Face Spaces..." -ForegroundColor Cyan
    git push origin main -f
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  [OK] HF Space updated!" -ForegroundColor Green
        
        Write-Host ""
        Write-Host "  -> Pushing to GitHub..." -ForegroundColor Cyan
        git push github main -f
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  [OK] GitHub updated!" -ForegroundColor Green
            Write-Host ""
            Write-Host "========================================" -ForegroundColor Green
            Write-Host "  DEPLOYMENT SUCCESSFUL!" -ForegroundColor Green
            Write-Host "========================================" -ForegroundColor Green
            Write-Host ""
            Write-Host "Live URLs:" -ForegroundColor Blue
            Write-Host "   - HF Space: https://huggingface.co/spaces/Mbola/sql-generation-oracle-fusion" -ForegroundColor Blue
            Write-Host "   - GitHub: https://github.com/mbola-raoelina/sql-chat-fusion-hf" -ForegroundColor Blue
            Write-Host ""
        } else {
            Write-Host ""
            Write-Host "[ERROR] GitHub push failed!" -ForegroundColor Red
        }
    } else {
        Write-Host ""
        Write-Host "[ERROR] Hugging Face push failed!" -ForegroundColor Red
    }
} else {
    Write-Host ""
    Write-Host "[INFO] No changes to commit" -ForegroundColor Yellow
}

Write-Host ""

