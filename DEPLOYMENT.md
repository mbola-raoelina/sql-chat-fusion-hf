# 🚀 Deployment Guide

This project is connected to **two Git remotes**:
- **Hugging Face Spaces** (origin) - Live demo deployment
- **GitHub** (github) - Code backup

## Quick Deploy

### Option 1: PowerShell (Recommended)
```powershell
.\push_both.ps1 "Your commit message"
```

### Option 2: Batch (CMD)
```cmd
push_both.bat "Your commit message"
```

## What happens?
1. ✅ Adds all changes (`git add .`)
2. ✅ Commits with your message (`git commit -m "..."`)
3. ✅ Pushes to HF Space (live deployment)
4. ✅ Pushes to GitHub (backup)

## Important Notes

⚠️ **This uses force push (`-f`)** to ensure clean deployment

🔑 **First time setup** (already done):
```bash
git init
git remote add origin https://huggingface.co/spaces/Mbola/sql-generation-oracle-fusion
git remote add github https://github.com/mbola-raoelina/sql-chat-fusion-hf.git
```

📍 **Live URLs**:
- HF Space: https://huggingface.co/spaces/Mbola/sql-generation-oracle-fusion
- GitHub: https://github.com/mbola-raoelina/sql-chat-fusion-hf

## Project Structure

```
oracle-sql-bedrock-enhanced/  (THIS FOLDER - Bedrock version)
├── app_enhanced.py           ← Main Flask app with Bedrock
├── bedrock_integration.py    ← AWS Bedrock LLM integration
├── sqlgen*.py                ← SQL generation + Pinecone
├── excel_generator.py        ← Excel export logic
├── push_both.ps1/bat         ← Deploy scripts
└── ...

sql-generation-oracle-fusion/  (OLD FOLDER - Legacy OpenAI only)
└── (kept for reference only)
```

## Workflow

1. **Develop** in `oracle-sql-bedrock-enhanced/`
2. **Test locally**: `python app_enhanced.py`
3. **Deploy**: `.\push_both.ps1 "description of changes"`
4. **Verify**: Check HF Space URL

That's it! 🎉

