# ⚡ Quick Start Guide

## 🚀 Deploy to HF Space + GitHub

```powershell
# PowerShell (Recommended)
.\push_both.ps1 "Your commit message"

# OR Batch (CMD)
push_both.bat "Your commit message"
```

## 🖥️ Run Locally

```powershell
# 1. Activate virtual environment
app_env\Scripts\activate

# 2. Run the app
python app_enhanced.py
```

Then open: **http://localhost:7860**

## 📋 Environment Setup

Create a `.env` file with:

```env
# AWS Bedrock
AWS_ACCESS_KEY_ID=your_key_here
AWS_SECRET_ACCESS_KEY=your_secret_here
AWS_BEDROCK_REGION=ca-central-1

# OpenAI (fallback)
OPENAI_API_KEY=your_openai_key

# Pinecone
PINECONE_API_KEY=your_pinecone_key
PINECONE_INDEX_NAME=sqlgen-schema-docs
PINECONE_ENVIRONMENT=us-east-1-aws
```

## 📍 Live URLs

- **HF Space**: https://huggingface.co/spaces/Mbola/sql-generation-oracle-fusion
- **GitHub**: https://github.com/mbola-raoelina/sql-chat-fusion-hf

## 🔍 Key Features

✅ **AWS Bedrock Integration** - Claude 3 Sonnet, Haiku, Opus  
✅ **OpenAI Fallback** - GPT-4o-mini for validation retry  
✅ **Pinecone Vector Search** - Semantic schema retrieval  
✅ **Direct Column Fetch** - 100% accurate validation  
✅ **Excel Export** - Full BI Publisher integration  
✅ **Zero Regression** - All original features preserved  

## 📚 Full Documentation

See `README.md` for detailed architecture and features.

