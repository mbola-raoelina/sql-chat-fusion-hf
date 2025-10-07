#!/usr/bin/env python3
"""
Enhanced Flask Application for Oracle SQL Assistant with AWS Bedrock Integration
Preserves all original functionality while adding advanced AI capabilities through Claude models.
"""

from flask import Flask, request, render_template_string, jsonify, session, Response
import os
import time
import logging
from datetime import datetime
from dotenv import load_dotenv
import io

# Load environment variables
load_dotenv()

# Import enhanced Bedrock integration
from bedrock_integration import create_bedrock_client, create_enhanced_generator, generate_sql_with_bedrock

# Import original system components for fallback
try:
    from sqlgen import generate_sql_from_text_semantic, validate_sql_against_schema
    from excel_generator import excel_generator
    ORIGINAL_SYSTEM_AVAILABLE = True
except ImportError as e:
    logging.warning(f"Original system components not available: {e}")
    ORIGINAL_SYSTEM_AVAILABLE = False

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-here')

# Initialize enhanced components
bedrock_client = None
enhanced_generator = None

def initialize_bedrock():
    """Initialize Bedrock client and enhanced generator"""
    global bedrock_client, enhanced_generator
    
    try:
        # Check for AWS credentials
        aws_access_key = os.getenv('AWS_ACCESS_KEY_ID')
        aws_secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
        aws_region = os.getenv('AWS_BEDROCK_REGION', 'us-east-1')
        
        if aws_access_key and aws_secret_key:
            bedrock_client = create_bedrock_client(
                region=aws_region,
                access_key=aws_access_key,
                secret_key=aws_secret_key
            )
        else:
            # Try with default credential chain
            bedrock_client = create_bedrock_client(region=aws_region)
        
        enhanced_generator = create_enhanced_generator(bedrock_client)
        
        # Test Bedrock connection
        test_result = bedrock_client.get_available_models()
        logger.info(f"Bedrock initialized successfully. Available models: {test_result}")
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to initialize Bedrock: {e}")
        bedrock_client = None
        enhanced_generator = None
        return False

# Initialize Bedrock on startup
BEDROCK_AVAILABLE = initialize_bedrock()

def validate_direct_sql(sql_query: str, original_query: str = None) -> tuple[bool, str]:
    """Validate a directly entered SQL query using the same sophisticated validation as natural language."""
    try:
        logger.info(f"Validating direct SQL: {sql_query}")
        
        # Import the sophisticated validation function from sqlgen
        from sqlgen import validate_sql_against_schema
        
        # Basic SQL validation first - ONLY check the actual SQL query, not the original_query context
        sql_upper = sql_query.upper().strip()
        
        # Check for basic SQL structure
        if not sql_upper.startswith('SELECT'):
            return False, "Query must start with SELECT"
        
        if 'FROM' not in sql_upper:
            return False, "Query must contain FROM clause"
        
        # Check for potentially dangerous operations (only as standalone SQL commands)
        dangerous_keywords = ['DROP', 'DELETE', 'UPDATE', 'INSERT', 'ALTER', 'CREATE', 'TRUNCATE']
        for keyword in dangerous_keywords:
            # Use word boundaries to avoid false positives in column descriptions
            import re
            pattern = r'\b' + re.escape(keyword) + r'\b'
            if re.search(pattern, sql_upper) and not re.search(r'--.*' + re.escape(keyword), sql_upper):
                # Additional check: ensure it's not in a comment or column description
                if not re.search(r'\([^)]*' + re.escape(keyword) + r'[^)]*\)', sql_upper):
                    return False, f"Query contains dangerous keyword: {keyword}"
        
        # First, do basic syntax validation to catch obvious errors
        import re
        
        # Check for spaces in table/column names (common syntax errors)
        # Exclude SQL keywords and valid constructs like "A WHERE A", "TABLE A JOIN B", etc.
        sql_keywords = {'SELECT', 'FROM', 'WHERE', 'AND', 'OR', 'JOIN', 'INNER', 'LEFT', 'RIGHT', 'OUTER', 'ON', 'GROUP', 'BY', 'HAVING', 'ORDER', 'ASC', 'DESC', 'UNION', 'ALL', 'DISTINCT', 'AS', 'IN', 'NOT', 'EXISTS', 'BETWEEN', 'LIKE', 'IS', 'NULL', 'CASE', 'WHEN', 'THEN', 'ELSE', 'END', 'TO_DATE', 'TO_CHAR', 'TO_NUMBER', 'SUM', 'COUNT', 'AVG', 'MAX', 'MIN'}
        
        # Find potential invalid identifiers with spaces, but exclude common SQL patterns
        space_in_identifier = re.search(r'\b[A-Z]+\s+[A-Z]+\s+[A-Z]+(?:\s+[A-Z]+)*\b', sql_upper)
        if space_in_identifier:
            matched_text = space_in_identifier.group()
            words = matched_text.split()
            
            # Check if this is a valid SQL construct (contains SQL keywords)
            contains_sql_keyword = any(word in sql_keywords for word in words)
            
            # Check if this looks like a valid alias pattern (single letter + keyword + single letter)
            is_alias_pattern = (len(words) == 3 and 
                              len(words[0]) == 1 and len(words[2]) == 1 and 
                              words[1] in sql_keywords)
            
            # Only flag as invalid if it doesn't contain SQL keywords and isn't an alias pattern
            if not contains_sql_keyword and not is_alias_pattern:
                return False, f"Invalid identifier with spaces: '{matched_text}'. Use underscores instead (e.g., AR_CASH_RECEIPTS_ALL, RECEIPT_DATE)"
        
        # Check for missing commas in SELECT clause
        if 'SELECT' in sql_upper and 'FROM' in sql_upper:
            select_part = sql_upper.split('FROM')[0].replace('SELECT', '').strip()
            if re.search(r'\b[A-Z]+\s+FROM\s+[A-Z]+\b', select_part):
                return False, "Missing comma in SELECT clause. Use commas to separate columns (e.g., SELECT COL1, COL2 FROM table)"
        
        # Get schema information for validation using Pinecone ONLY
        try:
            from sqlgen_pinecone import retrieve_docs_semantic_pinecone
            
            # Force Pinecone usage - no ChromaDB fallback
            logger.info("Forcing Pinecone usage for direct SQL validation")
            
            # Extract table names from SQL query for targeted schema retrieval
            import re
            table_names = []
            
            # Find all table references in the SQL (FROM, JOIN clauses)
            from_pattern = r'FROM\s+([A-Z_][A-Z0-9_]*)'
            join_pattern = r'JOIN\s+([A-Z_][A-Z0-9_]*)'
            
            from_matches = re.findall(from_pattern, sql_upper)
            join_matches = re.findall(join_pattern, sql_upper)
            
            table_names.extend(from_matches)
            table_names.extend(join_matches)
            table_names = list(set(table_names))  # Remove duplicates
            
            logger.info(f"Extracted table names from SQL: {table_names}")
            
            # Use multiple search strategies for comprehensive schema retrieval
            all_docs = []
            
            # ENHANCED: Use original query context for better schema retrieval
            if original_query:
                logger.info(f"Using original query context for enhanced schema retrieval: {original_query}")
                
                # Strategy 1: Use original query for semantic search (most relevant)
                result1 = retrieve_docs_semantic_pinecone(original_query, k=50)
                if result1.get('docs'):
                    all_docs.extend(result1['docs'])
                
                # Strategy 2: Combine original query with table names for targeted search
                for table_name in table_names:
                    enhanced_searches = [
                        f"{original_query} {table_name} columns schema",
                        f"{original_query} {table_name} table definition",
                        f"{table_name} table definition",
                        f"{table_name} columns schema"
                    ]
                    
                    for search_query in enhanced_searches:
                        result2 = retrieve_docs_semantic_pinecone(search_query, k=30)
                        if result2.get('docs'):
                            all_docs.extend(result2['docs'])
            
            # Strategy 3: Direct table searches for each table in the SQL
            # ENHANCED: Use better semantic queries that match Pinecone document structure
            for table_name in table_names:
                semantic_searches = [
                    f"TABLE {table_name} COLUMN",  # Matches "TABLE: X\nCOLUMN: Y" format
                    f"{table_name} table structure columns",
                    f"{table_name} Oracle Fusion table definition",
                    f"{table_name} table schema columns",
                    f"{table_name} all columns definition",  # More comprehensive
                    f"{table_name} column names types"  # Targets column metadata
                ]
                
                for semantic_query in semantic_searches:
                    result3 = retrieve_docs_semantic_pinecone(semantic_query, k=100)  # Much higher k to get more columns
                    if result3.get('docs'):
                        all_docs.extend(result3['docs'])
            
            # Remove duplicates based on document content
            seen_docs = set()
            unique_docs = []
            for doc in all_docs:
                doc_key = (doc.get('text', ''), doc.get('meta', {}).get('table', ''), doc.get('meta', {}).get('column', ''))
                if doc_key not in seen_docs:
                    seen_docs.add(doc_key)
                    unique_docs.append(doc)
            
            docs = unique_docs
            logger.info(f"Retrieved {len(docs)} unique documents for validation via semantic search")
            
            # NEW STRATEGY 4: Extract column references from the SQL and fetch them DIRECTLY by ID
            # This is more reliable than semantic search which may miss columns
            logger.info("Strategy 4: Extracting column references from SQL for direct Pinecone fetch")
            
            try:
                from pinecone import Pinecone
                import re
                
                # Extract all column references from SQL (format: table_alias.COLUMN or just COLUMN)
                column_refs = re.findall(r'\b([A-Z_][A-Z0-9_]*)\s*\.\s*([A-Z_][A-Z0-9_]+)', sql_upper)
                standalone_columns = re.findall(r'\bSELECT\s+(.+?)\s+FROM', sql_upper, re.DOTALL)
                
                # Get column names mentioned in SQL
                mentioned_columns = set()
                for _, col in column_refs:
                    mentioned_columns.add(col)
                
                # For each table in the SQL, try to fetch its columns directly from Pinecone
                pc = Pinecone(api_key=os.getenv('PINECONE_API_KEY'))
                index = pc.Index(os.getenv('PINECONE_INDEX_NAME', 'sqlgen-schema-docs'))
                
                for table_name in table_names:
                    # Construct IDs for columns we need to check
                    ids_to_fetch = []
                    
                    # Fetch mentioned columns first
                    for col in mentioned_columns:
                        ids_to_fetch.append(f"column::{table_name}.{col}")
                        ids_to_fetch.append(f"column::{table_name}_.{col}")  # Also check audit table
                    
                    if ids_to_fetch:
                        logger.info(f"Fetching {len(ids_to_fetch)} specific column IDs for {table_name}")
                        
                        # Pinecone fetch has a limit, so batch the requests
                        batch_size = 100
                        for i in range(0, len(ids_to_fetch), batch_size):
                            batch_ids = ids_to_fetch[i:i+batch_size]
                            try:
                                fetch_result = index.fetch(ids=batch_ids)
                                if fetch_result.vectors:
                                    logger.info(f"Direct fetch found {len(fetch_result.vectors)} columns for {table_name}")
                                    # Convert fetched vectors to doc format
                                    for vec_id, vec_data in fetch_result.vectors.items():
                                        if vec_data.metadata:
                                            doc = {
                                                "text": vec_data.metadata.get('document', ''),
                                                "meta": vec_data.metadata
                                            }
                                            docs.append(doc)
                            except Exception as fetch_error:
                                logger.warning(f"Direct fetch failed for batch: {fetch_error}")
                
                logger.info(f"After direct fetch: {len(docs)} total documents")
                
            except Exception as direct_fetch_error:
                logger.warning(f"Direct column fetch strategy failed: {direct_fetch_error}")
            
            # Build available columns dictionary (same format as natural language)
            # Enhanced column extraction from Pinecone documents
            available_columns = {}
            for doc in docs:
                meta = doc.get('meta', {})
                table_name = meta.get('table')
                column = meta.get('column')
                doc_type = meta.get('doc_type')
                txt = doc.get('text', '')
                
                if table_name:
                    # CRITICAL FIX: Normalize audit table names (remove trailing underscore)
                    # AP_INVOICES_ALL_ (audit) → AP_INVOICES_ALL (main)
                    # This ensures columns from audit tables are available for main table validation
                    normalized_table_name = table_name.rstrip('_') if table_name.endswith('_') else table_name
                    
                    if normalized_table_name not in available_columns:
                        available_columns[normalized_table_name] = []
                    
                    # Also keep original table name if different (for backward compatibility)
                    if table_name != normalized_table_name and table_name not in available_columns:
                        available_columns[table_name] = []
                    
                    # Method 1: Add column if it's a column document
                    if doc_type == "column" or column:
                        if column:
                            # Add to normalized table name
                            if column not in available_columns[normalized_table_name]:
                                available_columns[normalized_table_name].append(column)
                            # Also add to original table name
                            if table_name != normalized_table_name and column not in available_columns[table_name]:
                                available_columns[table_name].append(column)
                    
                    # Method 2: Extract columns from document text with multiple patterns
                    if txt:
                        # Pattern 1: "COLUMNS:" prefix
                        for line in txt.splitlines():
                            if line.strip().upper().startswith("COLUMNS:"):
                                cols = line.split(":",1)[1].strip()
                                for c in cols.split(","):
                                    col = c.strip()
                                    if col and col not in available_columns[table_name]:
                                        available_columns[table_name].append(col)
                        
                        # Pattern 2: Look for column definitions in comments
                        # Format: "COLUMN: COLUMN_NAME TYPE: VARCHAR2(255) DESCRIPTION: ..."
                        import re
                        column_pattern = r'COLUMN:\s*([A-Z_][A-Z0-9_]*)'
                        column_matches = re.findall(column_pattern, txt.upper())
                        for col in column_matches:
                            if col and col not in available_columns[table_name]:
                                available_columns[table_name].append(col)
                        
                        # Pattern 3: Look for table structure definitions
                        # Format: "CREATE TABLE ... (COLUMN1 TYPE, COLUMN2 TYPE, ...)"
                        create_table_pattern = r'CREATE\s+TABLE\s+\w+\s*\(([^)]+)\)'
                        create_matches = re.findall(create_table_pattern, txt.upper())
                        for match in create_matches:
                            # Extract column names from the parentheses
                            col_defs = [col.strip().split()[0] for col in match.split(',') if col.strip()]
                            for col in col_defs:
                                if col and col not in available_columns[table_name] and not col.startswith('CONSTRAINT'):
                                    available_columns[table_name].append(col)
                        
                        # Pattern 4: Look for column lists in table descriptions
                        # Format: "Table contains: COLUMN1, COLUMN2, COLUMN3"
                        table_contains_pattern = r'TABLE\s+CONTAINS?:\s*([^.\n]+)'
                        table_matches = re.findall(table_contains_pattern, txt.upper())
                        for match in table_matches:
                            cols = [col.strip() for col in match.split(',')]
                            for col in cols:
                                if col and col not in available_columns[table_name]:
                                    available_columns[table_name].append(col)
            
            # Debug logging
            logger.info(f"Built available_columns dictionary with {len(available_columns)} tables")
            logger.debug(f"Available tables: {list(available_columns.keys())}")
            for table, columns in available_columns.items():
                logger.debug(f"Table {table}: {len(columns)} columns")
            
            # For direct SQL, use STRICT validation - no automatic corrections
            # Check if table names exist exactly as written
            import re
            
            # Extract table names from FROM clause
            from_matches = re.findall(r'FROM\s+([A-Z_][A-Z0-9_]*)', sql_upper)
            logger.info(f"Extracted table names from SQL: {from_matches}")
            
            for table_name in from_matches:
                if table_name not in available_columns:
                    # Check for similar table names
                    similar_tables = [t for t in available_columns.keys() if table_name in t or t in table_name]
                    if similar_tables:
                        return False, f"Table '{table_name}' not found. Did you mean: {', '.join(similar_tables[:3])}?"
                    else:
                        return False, f"Table '{table_name}' not found in schema. Available tables: {', '.join(list(available_columns.keys())[:5])}..."
            
            # Use the SAME sophisticated validation as natural language
            validation_result = validate_sql_against_schema(sql_query, available_columns)
            
            if validation_result["ok"]:
                logger.info("Direct SQL validation successful using Pinecone schema validation")
                return True, "SQL is valid"
            else:
                error_msg = "; ".join(validation_result["errors"])
                if validation_result["suggestions"]:
                    error_msg += "\n\nSUGGESTIONS:\n" + "\n".join(validation_result["suggestions"])
                return False, error_msg
                
        except Exception as schema_error:
            logger.error(f"Pinecone schema validation failed: {schema_error}")
            
            # NO FALLBACK - if Pinecone fails, validation fails
            return False, f"Schema validation failed: {schema_error}. Please ensure Pinecone is properly configured."
        
    except Exception as e:
        logger.error(f"Error validating direct SQL: {e}")
        return False, f"Validation error: {str(e)}"


# Enhanced HTML template with Bedrock integration
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Oracle SQL Assistant - AWS Bedrock Enhanced</title>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
        }
        .container {
            background: white;
            border-radius: 15px;
            padding: 30px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
        }
        .header {
            text-align: center;
            margin-bottom: 30px;
        }
        .header h1 {
            color: #333;
            margin-bottom: 10px;
        }
        .header p {
            color: #666;
            margin-bottom: 5px;
        }
        .enhancement-badge {
            background: linear-gradient(90deg, #ff6b6b, #ee5a24);
            color: white;
            padding: 5px 15px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: bold;
            display: inline-block;
            margin-left: 10px;
        }
        .form-group {
            margin-bottom: 20px;
        }
        label {
            display: block;
            margin-bottom: 8px;
            font-weight: bold;
            color: #333;
        }
        input, select, textarea {
            width: 100%;
            padding: 12px;
            border: 2px solid #ddd;
            border-radius: 8px;
            font-size: 16px;
            box-sizing: border-box;
        }
        textarea {
            height: 120px;
            resize: vertical;
        }
        button {
            background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 15px 30px;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            cursor: pointer;
            transition: transform 0.2s;
        }
        button:hover {
            transform: translateY(-2px);
        }
        button:disabled {
            background: #6c757d;
            cursor: not-allowed;
            transform: none;
        }
        .model-info {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
            border-left: 4px solid #667eea;
        }
        .model-info h4 {
            margin: 0 0 10px 0;
            color: #333;
        }
        .model-info p {
            margin: 5px 0;
            color: #666;
            font-size: 14px;
        }
        .bedrock-status {
            display: inline-block;
            padding: 3px 8px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: bold;
        }
        .bedrock-status.available {
            background: #d4edda;
            color: #155724;
        }
        .bedrock-status.unavailable {
            background: #f8d7da;
            color: #721c24;
        }
        .loading {
            position: relative;
        }
        .loading::after {
            content: '';
            position: absolute;
            width: 16px;
            height: 16px;
            margin: auto;
            border: 2px solid transparent;
            border-top-color: #ffffff;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            right: 10px;
            top: 50%;
            transform: translateY(-50%);
        }
        @keyframes spin {
            0% { transform: translateY(-50%) rotate(0deg); }
            100% { transform: translateY(-50%) rotate(360deg); }
        }
        .progress-container {
            display: none;
            margin-top: 20px;
            padding: 20px;
            background: #f8f9fa;
            border-radius: 8px;
            border-left: 4px solid #667eea;
        }
        .progress-bar {
            width: 100%;
            height: 20px;
            background: #e9ecef;
            border-radius: 10px;
            overflow: hidden;
        }
        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
            width: 0%;
            transition: width 0.3s ease;
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0% { opacity: 1; }
            50% { opacity: 0.7; }
            100% { opacity: 1; }
        }
        .status-message {
            margin-top: 10px;
            padding: 10px;
            border-radius: 5px;
            font-weight: bold;
        }
        .status-message.processing {
            background: #d1ecf1;
            color: #0c5460;
            border: 1px solid #bee5eb;
        }
        .result {
            margin-top: 30px;
            padding: 20px;
            background: #f8f9fa;
            border-radius: 8px;
            border-left: 4px solid #667eea;
        }
        .sql-code {
            background: #2d3748;
            color: #e2e8f0;
            padding: 20px;
            border-radius: 8px;
            font-family: 'Courier New', monospace;
            white-space: pre-wrap;
            overflow-x: auto;
        }
        .status {
            padding: 10px;
            border-radius: 5px;
            margin-bottom: 15px;
        }
        .status.success {
            background: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }
        .status.error {
            background: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }
        .enhancement-info {
            background: #e7f3ff;
            padding: 10px;
            border-radius: 5px;
            margin-top: 10px;
            font-size: 12px;
            color: #004085;
        }
        .examples {
            margin-top: 20px;
        }
        .example {
            background: #f8f9fa;
            padding: 10px;
            margin: 5px 0;
            border-radius: 5px;
            cursor: pointer;
            border-left: 3px solid #667eea;
        }
        .example:hover {
            background: #e9ecef;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔍 Oracle SQL Assistant 
                <span class="enhancement-badge">AWS Bedrock Enhanced</span>
            </h1>
            <p>Advanced SQL generation with Claude AI models and Excel export capabilities</p>
            <p><strong>Enhanced with AWS Bedrock Claude Models</strong></p>
            
            <!-- Bedrock Status -->
            <div class="model-info">
                <h4>🤖 AI Model Status</h4>
                <p><strong>AWS Bedrock:</strong> 
                    <span class="bedrock-status {{ 'available' if bedrock_available else 'unavailable' }}">
                        {{ 'Available' if bedrock_available else 'Unavailable' }}
                    </span>
                </p>
                <p><strong>Original System:</strong> 
                    <span class="bedrock-status {{ 'available' if original_system_available else 'unavailable' }}">
                        {{ 'Available' if original_system_available else 'Unavailable' }}
                    </span>
                </p>
                {% if bedrock_available %}
                <p><em>✅ Enhanced with Claude 3 Haiku, Claude 3.5 Sonnet, and Claude 3 Opus</em></p>
                {% else %}
                <p><em>⚠️ Using fallback to original system</em></p>
                {% endif %}
            </div>
        </div>

        <form method="POST" action="/generate">
            <div class="form-group">
                <label for="model">LLM Model:</label>
                <select id="model" name="model">
                    {% if bedrock_available %}
                    <option value="claude-haiku">Claude 3 Haiku (AWS Bedrock - Fast & Cost-Effective)</option>
                    <option value="claude-sonnet" selected>Claude 3.5 Sonnet (AWS Bedrock - Balanced Performance)</option>
                    <option value="claude-opus">Claude 3 Opus (AWS Bedrock - Maximum Capability)</option>
                    <option value="auto">Auto-Select (Intelligent Model Selection)</option>
                    {% endif %}
                    {% if original_system_available %}
                    <option value="gpt-4o-mini">GPT-4o-mini (OpenAI - Fallback)</option>
                    {% endif %}
                </select>
            </div>

            <div class="form-group">
                <label for="mode">Input Mode:</label>
                <select id="mode" name="mode" onchange="toggleInputMode()">
                    <option value="natural" selected>Natural Language Query</option>
                    <option value="direct">Direct SQL Input</option>
                </select>
            </div>

            <div class="form-group" id="natural-group">
                <label for="query">Enter your natural language query:</label>
                <textarea id="query" name="query" placeholder="e.g., Show me all unpaid invoices due in August 2025"></textarea>
            </div>

            <div class="form-group" id="direct-group" style="display: none;">
                <label for="direct_sql">Enter your SQL query directly:</label>
                <textarea id="direct_sql" name="direct_sql" placeholder="e.g., SELECT INVOICE_ID, INVOICE_NUM, INVOICE_AMOUNT FROM AP_INVOICES_ALL WHERE INVOICE_DATE >= TO_DATE('2025-01-01', 'YYYY-MM-DD')"></textarea>
            </div>

            <button type="submit" id="generateBtn">🚀 Generate SQL</button>
        </form>

        <!-- Progress Container -->
        <div class="progress-container" id="progressContainer">
            <div class="status-message processing">
                🔄 Processing your request...
            </div>
            <div class="progress-bar">
                <div class="progress-fill" id="progressFill"></div>
            </div>
            <div id="statusText" style="margin-top: 10px; font-size: 14px; color: #666;">
                Initializing enhanced SQL generation...
            </div>
        </div>

        <div class="examples">
            <h3>💡 Example Queries:</h3>
            <div class="example" onclick="setNaturalQuery('List all unpaid invoices due in August 2025')">
                List all unpaid invoices due in August 2025
            </div>
            <div class="example" onclick="setNaturalQuery('Show total receipts per customer in Q2 2025')">
                Show total receipts per customer in Q2 2025
            </div>
            <div class="example" onclick="setNaturalQuery('For each ledger, show the last journal entry posted and its total debit amount')">
                For each ledger, show the last journal entry posted and its total debit amount
            </div>
            <div class="example" onclick="setNaturalQuery('Analyze payment trends over the last 6 months by supplier category')">
                Analyze payment trends over the last 6 months by supplier category
            </div>
            
            <h4>🔧 Direct SQL Examples:</h4>
            <div class="example" onclick="setDirectSQL('SELECT INVOICE_ID, INVOICE_NUM, INVOICE_AMOUNT FROM AP_INVOICES_ALL WHERE INVOICE_DATE >= TO_DATE(\\'2025-01-01\\', \\'YYYY-MM-DD\\')')">
                SELECT INVOICE_ID, INVOICE_NUM, INVOICE_AMOUNT FROM AP_INVOICES_ALL WHERE INVOICE_DATE >= TO_DATE('2025-01-01', 'YYYY-MM-DD')
            </div>
        </div>

        {% if result %}
        <div class="result">
            {% if result.status == 'success' %}
            <div class="status success">
                ✅ {% if result.message %}{{ result.message }}{% else %}SQL generated successfully{% endif %} in {{ result.time }}s
                <br><small>Model used: {{ result.model|default('Claude 3.5 Sonnet') }} | Mode: {{ result.mode|default('Natural Language') }}</small>
                {% if result.enhancement_info %}
                <div class="enhancement-info">
                    🤖 <strong>Enhanced Features:</strong> {{ result.enhancement_info }}
                </div>
                {% endif %}
            </div>
            <h3>📊 {% if result.message %}Validated SQL:{% else %}Generated SQL:{% endif %}</h3>
            <div class="sql-code">{{ result.sql }}</div>
            
            <!-- Excel Export Section -->
            <div style="margin-top: 20px;">
                <form method="POST" action="/export_excel" style="display: inline;" id="excelForm">
                    <input type="hidden" name="sql_query" value="{{ result.sql }}">
                    <input type="hidden" name="filename" value="sql_results">
                    {% if result.mode and 'Natural Language' in result.mode %}
                    <input type="hidden" name="original_query" value="{{ request.form.get('query', '') }}">
                    {% endif %}
                    <button type="submit" style="background: #28a745; margin-top: 10px;" id="excelBtn">
                        📊 Generate Excel File
                    </button>
                </form>
                <div id="excelMessage" style="display: none; margin-top: 10px; padding: 10px; background: #d4edda; border: 1px solid #c3e6cb; border-radius: 5px; color: #155724;">
                    ✅ Excel file generated successfully! Check your download folder for the file.
                </div>
                {% if session.last_download %}
                <div style="margin-top: 15px; padding: 10px; background: #e7f3ff; border: 1px solid #b3d9ff; border-radius: 5px; color: #004085;">
                    <strong>📥 Last Download:</strong> {{ session.last_download.filename }} 
                    <br><small>Generated: {{ session.last_download.timestamp[:19] }}</small>
                    <br><small>Query: {{ session.last_download.sql_query }}</small>
                </div>
                {% endif %}
            </div>
            {% else %}
            <div class="status error">
                ❌ {{ result.error }}
            </div>
            {% endif %}
        </div>
        {% endif %}
    </div>
    
    <script>
        function toggleInputMode() {
            const mode = document.getElementById('mode').value;
            const naturalGroup = document.getElementById('natural-group');
            const directGroup = document.getElementById('direct-group');
            const generateBtn = document.getElementById('generateBtn');
            
            if (mode === 'natural') {
                naturalGroup.style.display = 'block';
                directGroup.style.display = 'none';
                generateBtn.innerHTML = '🚀 Generate SQL';
            } else {
                naturalGroup.style.display = 'none';
                directGroup.style.display = 'block';
                generateBtn.innerHTML = '✅ Validate SQL';
            }
        }
        
        function setNaturalQuery(query) {
            document.getElementById('mode').value = 'natural';
            toggleInputMode();
            document.getElementById('query').value = query;
        }
        
        function setDirectSQL(sql) {
            document.getElementById('mode').value = 'direct';
            toggleInputMode();
            document.getElementById('direct_sql').value = sql;
        }
        
        // Handle form submission with loading states
        document.addEventListener('DOMContentLoaded', function() {
            const mainForm = document.querySelector('form[action="/generate"]');
            const generateBtn = document.getElementById('generateBtn');
            const progressContainer = document.getElementById('progressContainer');
            const progressFill = document.getElementById('progressFill');
            const statusText = document.getElementById('statusText');
            
            if (mainForm) {
                mainForm.addEventListener('submit', function(e) {
                    const currentMode = document.getElementById('mode').value;
                    if (currentMode === 'natural') {
                        generateBtn.innerHTML = '⏳ Generating SQL...';
                    } else {
                        generateBtn.innerHTML = '⏳ Validating SQL...';
                    }
                    generateBtn.disabled = true;
                    generateBtn.classList.add('loading');
                    
                    progressContainer.style.display = 'block';
                    
                    let progress = 0;
                    let steps;
                    if (currentMode === 'natural') {
                        steps = [
                            { progress: 15, text: 'Analyzing query complexity...' },
                            { progress: 30, text: 'Selecting optimal AI model...' },
                            { progress: 45, text: 'Retrieving schema information...' },
                            { progress: 65, text: 'Generating SQL with Claude AI...' },
                            { progress: 85, text: 'Validating and optimizing...' },
                            { progress: 95, text: 'Finalizing results...' }
                        ];
                    } else {
                        steps = [
                            { progress: 20, text: 'Parsing SQL syntax...' },
                            { progress: 40, text: 'Checking table references...' },
                            { progress: 60, text: 'Validating Oracle syntax...' },
                            { progress: 80, text: 'Performing security checks...' },
                            { progress: 95, text: 'Finalizing validation...' }
                        ];
                    }
                    
                    let currentStep = 0;
                    const progressInterval = setInterval(function() {
                        if (currentStep < steps.length) {
                            const step = steps[currentStep];
                            progressFill.style.width = step.progress + '%';
                            statusText.textContent = step.text;
                            currentStep++;
                        }
                    }, 2000);
                    
                    setTimeout(function() {
                        clearInterval(progressInterval);
                        setTimeout(function() {
                            const resultSection = document.querySelector('.result');
                            if (resultSection) {
                                resultSection.scrollIntoView({ 
                                    behavior: 'smooth', 
                                    block: 'start' 
                                });
                            }
                        }, 1000);
                    }, 15000);
                });
            }
            
            // Auto-scroll to results
            const resultSection = document.querySelector('.result');
            if (resultSection) {
                setTimeout(function() {
                    resultSection.scrollIntoView({ 
                        behavior: 'smooth', 
                        block: 'start' 
                    });
                }, 500);
            }
            
            // Handle Excel export
            const excelForm = document.getElementById('excelForm');
            const excelBtn = document.getElementById('excelBtn');
            const excelMessage = document.getElementById('excelMessage');
            
            if (excelForm) {
                excelForm.addEventListener('submit', function(e) {
                    excelBtn.innerHTML = '⏳ Generating Excel...';
                    excelBtn.disabled = true;
                    excelMessage.style.display = 'none';
                    
                    e.preventDefault();
                    const formData = new FormData(excelForm);
                    
                    fetch('/export_excel', {
                        method: 'POST',
                        body: formData
                    })
                    .then(response => {
                        if (response.ok) {
                            const contentType = response.headers.get('content-type');
                            if (contentType && contentType.includes('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')) {
                                return response.blob().then(blob => {
                                    const url = window.URL.createObjectURL(blob);
                                    const a = document.createElement('a');
                                    a.href = url;
                                    a.download = 'sql_results.xlsx';
                                    document.body.appendChild(a);
                                    a.click();
                                    window.URL.revokeObjectURL(url);
                                    document.body.removeChild(a);
                                    
                                    excelBtn.innerHTML = '📊 Generate Excel File';
                                    excelBtn.disabled = false;
                                    excelMessage.style.display = 'block';
                                    excelMessage.innerHTML = '✅ Excel file downloaded successfully! Check your download folder.';
                                });
                            } else {
                                return response.text().then(text => {
                                    excelBtn.innerHTML = '📊 Generate Excel File';
                                    excelBtn.disabled = false;
                                    excelMessage.innerHTML = '❌ ' + text;
                                    excelMessage.style.display = 'block';
                                });
                            }
                        } else {
                            throw new Error('Network response was not ok');
                        }
                    })
                    .catch(error => {
                        console.error('Error:', error);
                        excelBtn.innerHTML = '📊 Generate Excel File';
                        excelBtn.disabled = false;
                        excelMessage.innerHTML = '❌ Error generating Excel file: ' + error.message;
                        excelMessage.style.display = 'block';
                    });
                });
            }
        });
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    """Main page with enhanced Bedrock integration"""
    return render_template_string(HTML_TEMPLATE, 
                                bedrock_available=BEDROCK_AVAILABLE,
                                original_system_available=ORIGINAL_SYSTEM_AVAILABLE)

@app.route('/generate', methods=['POST'])
def generate_sql():
    """Enhanced SQL generation with Bedrock integration"""
    try:
        mode = request.form.get('mode', 'natural')
        model = request.form.get('model', 'claude-sonnet')
        
        if mode == 'natural':
            # Natural language mode
            query = request.form.get('query', '').strip()
            
            if not query:
                return render_template_string(HTML_TEMPLATE, 
                                            bedrock_available=BEDROCK_AVAILABLE,
                                            original_system_available=ORIGINAL_SYSTEM_AVAILABLE,
                                            result={
                                                'status': 'error',
                                                'error': 'Please enter a natural language query'
                                            })
            
            logger.info(f"Starting enhanced SQL generation for: {query}")
            start_time = time.time()
            
            # Use enhanced generator with Bedrock if available
            if BEDROCK_AVAILABLE and enhanced_generator:
                if model == 'auto':
                    # Use intelligent model selection
                    result = enhanced_generator.generate_sql_enhanced(query)
                else:
                    # Use specified model
                    result = enhanced_generator.generate_sql_enhanced(query, model_preference=model)
                
                generation_time = time.time() - start_time
                
                if result.get('success', False):
                    enhancement_info = "Intelligent model selection, enhanced context understanding"
                    if result.get('enhanced_features', {}).get('complexity_analysis'):
                        analysis = result['enhanced_features']['complexity_analysis']
                        enhancement_info += f", complexity score: {analysis['score']:.2f}"
                    
                    return render_template_string(HTML_TEMPLATE,
                                                bedrock_available=BEDROCK_AVAILABLE,
                                                original_system_available=ORIGINAL_SYSTEM_AVAILABLE,
                                                result={
                                                    'status': 'success',
                                                    'sql': result.get('sql', ''),
                                                    'time': f"{generation_time:.2f}",
                                                    'model': result.get('model_used', model),
                                                    'mode': 'Natural Language (Enhanced)',
                                                    'enhancement_info': enhancement_info
                                                })
                else:
                    # Try fallback to original system
                    if ORIGINAL_SYSTEM_AVAILABLE:
                        logger.warning("Bedrock generation failed, trying original system fallback")
                        fallback_result = generate_sql_from_text_semantic(query, model='gpt-4o-mini')
                        
                        if 'llm_sql' in fallback_result and not fallback_result['llm_sql'].startswith('-- ERROR:'):
                            return render_template_string(HTML_TEMPLATE,
                                                        bedrock_available=BEDROCK_AVAILABLE,
                                                        original_system_available=ORIGINAL_SYSTEM_AVAILABLE,
                                                        result={
                                                            'status': 'success',
                                                            'sql': fallback_result['llm_sql'],
                                                            'time': f"{generation_time:.2f}",
                                                            'model': 'gpt-4o-mini (Fallback)',
                                                            'mode': 'Natural Language (Fallback)',
                                                            'enhancement_info': 'Used fallback due to Bedrock unavailability'
                                                        })
                    
                    return render_template_string(HTML_TEMPLATE,
                                                bedrock_available=BEDROCK_AVAILABLE,
                                                original_system_available=ORIGINAL_SYSTEM_AVAILABLE,
                                                result={
                                                    'status': 'error',
                                                    'error': f"Enhanced generation failed: {result.get('error', 'Unknown error')}"
                                                })
            else:
                # Use original system if Bedrock not available
                if ORIGINAL_SYSTEM_AVAILABLE:
                    result = generate_sql_from_text_semantic(query, model='gpt-4o-mini')
                    generation_time = time.time() - start_time
                    
                    sql = result.get("llm_sql", "")
                    
                    if sql and not sql.startswith("-- ERROR:") and sql.strip():
                        return render_template_string(HTML_TEMPLATE,
                                                    bedrock_available=BEDROCK_AVAILABLE,
                                                    original_system_available=ORIGINAL_SYSTEM_AVAILABLE,
                                                    result={
                                                        'status': 'success',
                                                        'sql': sql,
                                                        'time': f"{generation_time:.2f}",
                                                        'model': 'gpt-4o-mini (Original)',
                                                        'mode': 'Natural Language (Original)',
                                                        'enhancement_info': 'Using original system (Bedrock unavailable)'
                                                    })
                    else:
                        return render_template_string(HTML_TEMPLATE,
                                                    bedrock_available=BEDROCK_AVAILABLE,
                                                    original_system_available=ORIGINAL_SYSTEM_AVAILABLE,
                                                    result={
                                                        'status': 'error',
                                                        'error': f"SQL generation failed: {result.get('error', 'Unknown error')}"
                                                    })
                else:
                    return render_template_string(HTML_TEMPLATE,
                                                bedrock_available=BEDROCK_AVAILABLE,
                                                original_system_available=ORIGINAL_SYSTEM_AVAILABLE,
                                                result={
                                                    'status': 'error',
                                                    'error': 'No AI models available. Please check configuration.'
                                                })
        
        else:
            # Direct SQL mode
            direct_sql = request.form.get('direct_sql', '').strip()
            
            if not direct_sql:
                return render_template_string(HTML_TEMPLATE,
                                            bedrock_available=BEDROCK_AVAILABLE,
                                            original_system_available=ORIGINAL_SYSTEM_AVAILABLE,
                                            result={
                                                'status': 'error',
                                                'error': 'Please enter a SQL query'
                                            })
            
            logger.info(f"Validating direct SQL: {direct_sql}")
            start_time = time.time()
            
            # Validate the direct SQL
            is_valid, validation_message = validate_direct_sql(direct_sql)
            
            validation_time = time.time() - start_time
            
            if is_valid:
                return render_template_string(HTML_TEMPLATE,
                                            bedrock_available=BEDROCK_AVAILABLE,
                                            original_system_available=ORIGINAL_SYSTEM_AVAILABLE,
                                            result={
                                                'status': 'success',
                                                'sql': direct_sql,
                                                'time': f"{validation_time:.2f}",
                                                'message': 'Direct SQL validated successfully',
                                                'model': 'Validation System',
                                                'mode': 'Direct SQL',
                                                'enhancement_info': 'Enhanced validation with schema checking'
                                            })
            else:
                return render_template_string(HTML_TEMPLATE,
                                            bedrock_available=BEDROCK_AVAILABLE,
                                            original_system_available=ORIGINAL_SYSTEM_AVAILABLE,
                                            result={
                                                'status': 'error',
                                                'error': f"SQL validation failed: {validation_message}"
                                            })
            
    except Exception as e:
        logger.error(f"Exception during enhanced SQL processing: {str(e)}")
        return render_template_string(HTML_TEMPLATE,
                                    bedrock_available=BEDROCK_AVAILABLE,
                                    original_system_available=ORIGINAL_SYSTEM_AVAILABLE,
                                    result={
                                        'status': 'error',
                                        'error': f"Exception: {str(e)}"
                                    })

@app.route('/export_excel', methods=['POST'])
def export_excel():
    """Export SQL results to Excel file"""
    try:
        sql_query = request.form.get('sql_query', '').strip()
        filename = request.form.get('filename', 'sql_results')
        
        if not sql_query:
            return render_template_string(HTML_TEMPLATE, 
                                        bedrock_available=BEDROCK_AVAILABLE,
                                        original_system_available=ORIGINAL_SYSTEM_AVAILABLE,
                                        result={
                                            'status': 'error',
                                            'error': 'No SQL query provided for Excel export'
                                        })
        
        logger.info("Generating Excel file from SQL")
        
        # First, validate the SQL query using enhanced validation with original query context
        original_query = request.form.get('original_query', '').strip()
        
        # Use enhanced validation that leverages the original query for better schema retrieval
        is_valid, validation_message = validate_direct_sql(sql_query, original_query=original_query)
        if not is_valid:
            # Check if this is a schema-related validation failure that we can retry
            # Catch all hallucination patterns: undefined aliases, missing tables, missing columns
            hallucination_patterns = [
                "not found in schema",
                "not found in available",
                "undefined table alias",
                "table not found",
                "column not found",
                "invalid table",
                "invalid column"
            ]
            is_hallucination_error = any(pattern in validation_message.lower() for pattern in hallucination_patterns)
            
            if is_hallucination_error:
                logger.info("Schema validation failed, attempting LLM retry with enhanced schema")
                
                # Try to regenerate the SQL with better schema information
                original_query = request.form.get('original_query', '').strip()
                if original_query:
                    try:
                        # Import the SQL generation function
                        from sqlgen import generate_sql_from_text_semantic
                        
                        # Generate SQL again with the original query
                        retry_result = generate_sql_from_text_semantic(original_query)
                        
                        if retry_result.get('llm_sql') and not retry_result['llm_sql'].startswith('-- ERROR:'):
                            new_sql = retry_result['llm_sql']
                            logger.info(f"LLM retry generated new SQL: {new_sql[:100]}...")
                            
                            # Validate the new SQL
                            is_valid_retry, retry_validation_message = validate_direct_sql(new_sql)
                            if is_valid_retry:
                                logger.info("LLM retry SQL validation successful")
                                sql_query = new_sql  # Use the retry SQL
                            else:
                                logger.warning(f"LLM retry SQL still failed validation: {retry_validation_message}")
                        else:
                            logger.warning("LLM retry failed to generate new SQL")
                    except Exception as e:
                        logger.error(f"LLM retry failed with exception: {str(e)}")
                
                # If retry didn't work or wasn't possible, return the original error
                if not is_valid:
                    return render_template_string(HTML_TEMPLATE,
                                                bedrock_available=BEDROCK_AVAILABLE,
                                                original_system_available=ORIGINAL_SYSTEM_AVAILABLE,
                                                result={
                                                    'status': 'error',
                                                    'error': f"❌ SQL Not Validated: {validation_message}. Please fix the SQL query and try again."
                                                })
            else:
                # Non-schema validation error, return immediately
                return render_template_string(HTML_TEMPLATE,
                                            bedrock_available=BEDROCK_AVAILABLE,
                                            original_system_available=ORIGINAL_SYSTEM_AVAILABLE,
                                            result={
                                                'status': 'error',
                                                'error': f"❌ SQL Not Validated: {validation_message}. Please fix the SQL query and try again."
                                            })
        
        # Use our existing excel generator - it works fine for valid SQL
        excel_data, row_count = excel_generator.handle_sql_to_excel(sql_query)
        
        if excel_data and row_count >= 0:
            # Store download info in session for persistence
            session['last_download'] = {
                'filename': f"{filename}.xlsx",
                'timestamp': datetime.now().isoformat(),
                'sql_query': sql_query[:100] + "..." if len(sql_query) > 100 else sql_query,
                'status': 'success'
            }
            
            # Use BytesIO for in-memory file handling (better for HF Spaces)
            from flask import Response
            import io
            
            response = Response(
                excel_data,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                headers={
                    'Content-Disposition': f'attachment; filename="{filename}.xlsx"',
                    'Content-Length': str(len(excel_data))
                }
            )
            
            return response
        else:
            return render_template_string(HTML_TEMPLATE,
                                        bedrock_available=BEDROCK_AVAILABLE,
                                        original_system_available=ORIGINAL_SYSTEM_AVAILABLE,
                                        result={
                                            'status': 'error',
                                            'error': 'Failed to generate Excel file. The SQL query may contain invalid columns or syntax errors.'
                                        })
            
    except Exception as e:
        logger.error(f"Exception during Excel generation: {str(e)}")
        return render_template_string(HTML_TEMPLATE,
                                    bedrock_available=BEDROCK_AVAILABLE,
                                    original_system_available=ORIGINAL_SYSTEM_AVAILABLE,
                                    result={
                                        'status': 'error',
                                        'error': f"Excel generation failed: {str(e)}"
                                    })

@app.route('/health')
def health():
    """Enhanced health check with Bedrock status"""
    health_info = {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "bedrock_available": BEDROCK_AVAILABLE,
        "original_system_available": ORIGINAL_SYSTEM_AVAILABLE,
        "enhanced_features": {
            "intelligent_model_selection": BEDROCK_AVAILABLE,
            "claude_models": BEDROCK_AVAILABLE,
            "fallback_system": ORIGINAL_SYSTEM_AVAILABLE
        }
    }
    
    if BEDROCK_AVAILABLE and bedrock_client:
        try:
            available_models = bedrock_client.get_available_models()
            health_info["available_bedrock_models"] = available_models
        except Exception as e:
            health_info["bedrock_error"] = str(e)
    
    return jsonify(health_info)

@app.route('/diagnose')
def diagnose():
    """Enhanced diagnostic endpoint"""
    try:
        diagnosis = {
            "timestamp": datetime.now().isoformat(),
            "environment": {
                "aws_access_key_set": bool(os.getenv("AWS_ACCESS_KEY_ID")),
                "aws_secret_key_set": bool(os.getenv("AWS_SECRET_ACCESS_KEY")),
                "aws_region": os.getenv("AWS_BEDROCK_REGION", "us-east-1"),
                "openai_api_key_set": bool(os.getenv("OPENAI_API_KEY")),
                "pinecone_api_key_set": bool(os.getenv("PINECONE_API_KEY")),
            },
            "bedrock_status": {
                "available": BEDROCK_AVAILABLE,
                "client_initialized": bedrock_client is not None,
                "enhanced_generator_available": enhanced_generator is not None
            },
            "original_system_status": {
                "available": ORIGINAL_SYSTEM_AVAILABLE
            }
        }
        
        # Test Bedrock connection if available
        if BEDROCK_AVAILABLE and bedrock_client:
            try:
                available_models = bedrock_client.get_available_models()
                diagnosis["bedrock_models"] = available_models
            except Exception as e:
                diagnosis["bedrock_error"] = str(e)
        
        return jsonify(diagnosis)
        
    except Exception as e:
        return jsonify({"error": f"Diagnostic failed: {e}"}), 500

def main():
    """Main function to launch the enhanced Flask app"""
    logger.info("Starting Oracle SQL Assistant - AWS Bedrock Enhanced Edition")
    
    # Check environment variables
    required_vars = ["PINECONE_API_KEY", "PINECONE_ENVIRONMENT", "PINECONE_INDEX_NAME"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.warning(f"Missing environment variables: {missing_vars}")
        logger.info("Make sure to set these in your environment or .env file")
    
    # AWS Bedrock configuration check
    if BEDROCK_AVAILABLE:
        logger.info("✅ AWS Bedrock integration enabled")
        logger.info("Available Claude models: Haiku, Sonnet, Opus")
    else:
        logger.warning("⚠️ AWS Bedrock integration disabled - using fallback")
    
    # Launch application
    app.run(
        host="0.0.0.0",
        port=7860,
        debug=False
    )

if __name__ == "__main__":
    main()
