# Hugging Face Space Deployment Guide

## ✅ Fixed Issues (2025-10-07)

### Problem 1: Local HF Model Loading
**Error**: `ValueError: Using device_map requires accelerate`
**Cause**: System was trying to load `defog/sqlcoder-7b-2` (local Hugging Face model) which requires heavy dependencies (`torch`, `transformers`, `accelerate`)
**Fix**: Disabled local HF models in `sqlgen.py` by setting `USE_HF_MODELS = False`

### Problem 2: Wrong SDK Configuration
**Error**: Gradio SDK specified but Flask app deployed
**Fix**: Changed `README.md` YAML header to use `sdk: docker` with `app_port: 7860`

### Problem 3: Dependency Conflicts
**Error**: `resolution-too-deep` during pip install
**Fix**: Removed heavy dependencies (`torch`, `transformers`, `accelerate`) and fixed all package versions

## 🎯 Model Architecture

### Natural Language SQL Generation
```
User Query → App Enhanced (app_enhanced.py)
    ↓
    ├─ 1️⃣ PRIMARY: AWS Bedrock Claude Models
    │   └─ bedrock_integration.py → _generate_with_bedrock()
    │       └─ Retrieves schema from Pinecone/ChromaDB
    │       └─ Builds enhanced prompt with actual schema
    │       └─ Calls Claude 3.5 Sonnet/Haiku/Opus via AWS API
    │
    ├─ 2️⃣ FALLBACK: OpenAI GPT-4o-mini
    │   └─ sqlgen.py → generate_sql_from_text_semantic()
    │       └─ Uses OpenAI API (no local models)
    │
    └─ 3️⃣ VALIDATION: Direct Schema Validation
        └─ app_enhanced.py → validate_direct_sql()
            └─ Strategy 1: Semantic search in Pinecone
            └─ Strategy 2: Direct table fetch by ID
            └─ Strategy 3: Column extraction and semantic search
            └─ Strategy 4: Direct column fetch by ID (NEW)
```

### Environment Variables Required

**For Bedrock (Primary)**:
- `AWS_ACCESS_KEY_ID` - Your AWS access key
- `AWS_SECRET_ACCESS_KEY` - Your AWS secret key
- `AWS_BEDROCK_REGION` - AWS region (e.g., `us-east-1`, `ca-central-1`)

**For OpenAI (Fallback)**:
- `OPENAI_API_KEY` - Your OpenAI API key

**For Pinecone (Schema)**:
- `PINECONE_API_KEY` - Your Pinecone API key
- `PINECONE_ENVIRONMENT` - Your Pinecone environment
- `PINECONE_INDEX_NAME` - Your Pinecone index name

## 🚀 Deployment Steps

### 1. Set Environment Variables in HF Space
Go to your Space settings → Repository secrets and add:
```
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_BEDROCK_REGION=us-east-1
OPENAI_API_KEY=your_openai_key
PINECONE_API_KEY=your_pinecone_key
PINECONE_ENVIRONMENT=your_pinecone_env
PINECONE_INDEX_NAME=sqlgen-schema-docs
```

### 2. Push to HF Space
```powershell
.\push_both.ps1 -CommitMessage "Fix: Enable Docker SDK and disable local HF models"
```

### 3. Verify Deployment
- Space should rebuild with Docker
- Check logs for "Bedrock initialized successfully"
- Test with example query: "List all unpaid invoices"

## 📊 Model Selection Logic

The system **automatically selects the best model**:

| Query Complexity | Model Used | Why |
|-----------------|------------|-----|
| Simple | Claude Haiku | Fast, cost-effective |
| Medium | Claude Sonnet | Balanced performance |
| Complex | Claude Sonnet | High accuracy needed |
| Bedrock Down | GPT-4o-mini | Reliable fallback |

## 🐛 Troubleshooting

### Issue: "No AI models available"
- Check AWS credentials are set correctly
- Verify AWS Bedrock has model access enabled in AWS Console
- Check OpenAI API key as fallback

### Issue: "SQL Not Validated"
- This is expected for hallucinations
- System will retry with enhanced schema
- Check that Pinecone index is populated

### Issue: Docker build fails
- Check `Dockerfile` is present
- Verify `requirements.txt` has no conflicting versions
- Check logs for specific error

## 📝 Key Files

| File | Purpose |
|------|---------|
| `Dockerfile` | Docker configuration for HF Spaces |
| `app_enhanced.py` | Main Flask application |
| `bedrock_integration.py` | AWS Bedrock client and SQL generation |
| `sqlgen.py` | Original system + Pinecone schema retrieval |
| `requirements.txt` | Python dependencies (API-only, no local models) |
| `README.md` | HF Space configuration (YAML header) |

## ✅ Verification Checklist

- [ ] Dockerfile created
- [ ] requirements.txt simplified (no torch/transformers)
- [ ] USE_HF_MODELS = False in sqlgen.py
- [ ] README.md has correct YAML (sdk: docker)
- [ ] Environment variables set in HF Space
- [ ] Push completed successfully
- [ ] Space builds without errors
- [ ] Bedrock models work for SQL generation
- [ ] Excel export works
- [ ] Validation catches hallucinations

