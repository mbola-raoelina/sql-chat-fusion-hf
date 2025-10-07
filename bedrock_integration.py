#!/usr/bin/env python3
"""
AWS Bedrock Integration for Oracle SQL Generation
Provides enhanced SQL generation capabilities using Claude models while maintaining
backward compatibility with the original system.
"""

import os
import json
import logging
import time
import boto3
from typing import Dict, Any, Optional, List
from botocore.exceptions import ClientError, BotoCoreError
import requests
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BedrockClient:
    """AWS Bedrock client for Claude model integration"""
    
    def __init__(self, region_name: str = None, access_key_id: str = None, secret_access_key: str = None):
        """
        Initialize Bedrock client
        
        Args:
            region_name: AWS region for Bedrock
            access_key_id: AWS access key (optional, can use environment/default)
            secret_access_key: AWS secret key (optional, can use environment/default)
        """
        self.region_name = region_name or os.getenv('AWS_BEDROCK_REGION', 'us-east-1')
        
        # Initialize boto3 client with credentials
        try:
            if access_key_id and secret_access_key:
                self.client = boto3.client(
                    'bedrock-runtime',
                    region_name=self.region_name,
                    aws_access_key_id=access_key_id,
                    aws_secret_access_key=secret_access_key
                )
            else:
                # Use default credential chain (environment, IAM role, etc.)
                self.client = boto3.client(
                    'bedrock-runtime',
                    region_name=self.region_name
                )
            
            logger.info(f"Bedrock client initialized for region: {self.region_name}")
            
        except Exception as e:
            logger.error(f"Failed to initialize Bedrock client: {e}")
            self.client = None
    
    def get_available_models(self) -> List[str]:
        """Get list of available Claude models in Bedrock"""
        return [
            "anthropic.claude-3-haiku-20240307-v1:0",
            "anthropic.claude-3-sonnet-20240229-v1:0",
            "anthropic.claude-3-opus-20240229-v1:0"
        ]
    
    def call_claude_haiku(self, prompt: str, max_tokens: int = 4000) -> Dict[str, Any]:
        """Call Claude 3 Haiku model - fast and cost-effective for simple queries"""
        return self._call_claude_model(
            model_id="anthropic.claude-3-haiku-20240307-v1:0",
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=0.1
        )
    
    def call_claude_sonnet(self, prompt: str, max_tokens: int = 4000) -> Dict[str, Any]:
        """Call Claude 3 Sonnet model - balanced performance for complex queries"""
        return self._call_claude_model(
            model_id="anthropic.claude-3-sonnet-20240229-v1:0",
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=0.1
        )
    
    def call_claude_opus(self, prompt: str, max_tokens: int = 4000) -> Dict[str, Any]:
        """Call Claude 3 Opus model - most capable for analytical queries"""
        return self._call_claude_model(
            model_id="anthropic.claude-3-opus-20240229-v1:0",
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=0.1
        )
    
    def _call_claude_model(self, model_id: str, prompt: str, max_tokens: int = 4000, temperature: float = 0.1) -> Dict[str, Any]:
        """
        Generic method to call any Claude model
        
        Args:
            model_id: The Bedrock model ID
            prompt: The input prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            
        Returns:
            Dict containing response and metadata
        """
        if not self.client:
            return {
                "success": False,
                "error": "Bedrock client not initialized",
                "model": model_id
            }
        
        try:
            # Prepare the request body for Claude
            body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            }
            
            logger.info(f"Calling Bedrock model: {model_id}")
            start_time = time.time()
            
            # Make the API call
            response = self.client.invoke_model(
                modelId=model_id,
                body=json.dumps(body),
                contentType="application/json"
            )
            
            # Parse the response
            response_body = json.loads(response['body'].read())
            response_time = time.time() - start_time
            
            # Extract the content
            content = response_body.get('content', [])
            if content and len(content) > 0:
                generated_text = content[0].get('text', '')
            else:
                generated_text = ""
            
            logger.info(f"Bedrock response received in {response_time:.2f}s")
            
            return {
                "success": True,
                "content": generated_text,
                "model": model_id,
                "response_time": response_time,
                "usage": response_body.get('usage', {}),
                "metadata": {
                    "region": self.region_name,
                    "timestamp": datetime.now().isoformat()
                }
            }
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            logger.error(f"Bedrock ClientError: {error_code} - {error_message}")
            return {
                "success": False,
                "error": f"Bedrock API error: {error_code} - {error_message}",
                "model": model_id,
                "error_code": error_code
            }
            
        except BotoCoreError as e:
            logger.error(f"Bedrock BotoCoreError: {e}")
            return {
                "success": False,
                "error": f"Bedrock connection error: {str(e)}",
                "model": model_id
            }
            
        except Exception as e:
            logger.error(f"Unexpected error calling Bedrock: {e}")
            return {
                "success": False,
                "error": f"Unexpected error: {str(e)}",
                "model": model_id
            }

class ModelRouter:
    """Intelligent model selection based on query complexity and requirements"""
    
    def __init__(self, bedrock_client: BedrockClient = None):
        self.bedrock_client = bedrock_client or BedrockClient()
        
    def analyze_query_complexity(self, query: str) -> Dict[str, Any]:
        """
        Analyze query complexity to determine optimal model
        
        Args:
            query: Natural language query
            
        Returns:
            Dict with complexity analysis
        """
        complexity_indicators = {
            'simple_keywords': ['show', 'list', 'get', 'find', 'select'],
            'complex_keywords': ['analyze', 'compare', 'calculate', 'aggregate', 'join', 'relationship'],
            'analytical_keywords': ['trend', 'pattern', 'correlation', 'statistical', 'forecast', 'insight'],
            'multi_table_indicators': ['between', 'across', 'related', 'associated', 'linked'],
            'temporal_indicators': ['over time', 'historical', 'trend', 'period', 'quarter', 'year'],
            'aggregation_indicators': ['total', 'sum', 'average', 'count', 'maximum', 'minimum', 'group']
        }
        
        query_lower = query.lower()
        complexity_score = 0.0
        
        # Simple queries (0.0 - 0.3)
        simple_count = sum(1 for keyword in complexity_indicators['simple_keywords'] if keyword in query_lower)
        if simple_count > 0 and len(query.split()) < 15:
            complexity_score += 0.1
        
        # Complex queries (0.3 - 0.7)
        complex_count = sum(1 for keyword in complexity_indicators['complex_keywords'] if keyword in query_lower)
        if complex_count > 0:
            complexity_score += 0.3
            
        multi_table_count = sum(1 for keyword in complexity_indicators['multi_table_indicators'] if keyword in query_lower)
        if multi_table_count > 0:
            complexity_score += 0.2
            
        aggregation_count = sum(1 for keyword in complexity_indicators['aggregation_indicators'] if keyword in query_lower)
        if aggregation_count > 0:
            complexity_score += 0.2
        
        # Analytical queries (0.7 - 1.0)
        analytical_count = sum(1 for keyword in complexity_indicators['analytical_keywords'] if keyword in query_lower)
        if analytical_count > 0:
            complexity_score += 0.4
            
        temporal_count = sum(1 for keyword in complexity_indicators['temporal_indicators'] if keyword in query_lower)
        if temporal_count > 0:
            complexity_score += 0.3
        
        # Adjust based on query length and complexity
        word_count = len(query.split())
        if word_count > 20:
            complexity_score += 0.1
        if word_count > 40:
            complexity_score += 0.2
            
        # Cap the score
        complexity_score = min(complexity_score, 1.0)
        
        return {
            'score': complexity_score,
            'category': self._categorize_complexity(complexity_score),
            'indicators': {
                'simple_keywords': simple_count,
                'complex_keywords': complex_count,
                'analytical_keywords': analytical_count,
                'multi_table_indicators': multi_table_count,
                'aggregation_indicators': aggregation_count,
                'temporal_indicators': temporal_count,
                'word_count': word_count
            }
        }
    
    def _categorize_complexity(self, score: float) -> str:
        """Categorize complexity score"""
        if score < 0.3:
            return 'simple'
        elif score < 0.7:
            return 'complex'
        else:
            return 'analytical'
    
    def select_optimal_model(self, query: str, available_models: List[str] = None) -> Dict[str, Any]:
        """
        Select the optimal model based on query analysis
        
        Args:
            query: Natural language query
            available_models: List of available models (optional)
            
        Returns:
            Dict with model selection and reasoning
        """
        if not available_models:
            available_models = ['claude-haiku', 'claude-sonnet', 'claude-opus', 'gpt-4o-mini']
        
        analysis = self.analyze_query_complexity(query)
        complexity_score = analysis['score']
        category = analysis['category']
        
        # Model selection logic
        if complexity_score < 0.3:
            selected_model = 'claude-haiku'
            reasoning = "Simple query - using fast and cost-effective Claude Haiku"
        elif complexity_score < 0.7:
            selected_model = 'claude-sonnet'
            reasoning = "Complex query - using balanced Claude 3.5 Sonnet"
        else:
            selected_model = 'claude-opus'
            reasoning = "Analytical query - using most capable Claude Opus"
        
        return {
            'selected_model': selected_model,
            'reasoning': reasoning,
            'complexity_analysis': analysis,
            'available_models': available_models,
            'selection_timestamp': datetime.now().isoformat()
        }

class EnhancedSQLGenerator:
    """Enhanced SQL generator using AWS Bedrock with fallback to original system"""
    
    def __init__(self, bedrock_client: BedrockClient = None, model_router: ModelRouter = None):
        self.bedrock_client = bedrock_client or BedrockClient()
        self.model_router = model_router or ModelRouter(self.bedrock_client)
        
        # Import original system components for fallback
        try:
            from sqlgen import generate_sql_from_text_semantic as original_generate
            self.original_generate = original_generate
            self.original_available = True
            logger.info("Original SQL generation system available for fallback")
        except ImportError as e:
            logger.warning(f"Original system not available: {e}")
            self.original_available = False
    
    def generate_sql_enhanced(self, query: str, model_preference: str = None, use_fallback: bool = True) -> Dict[str, Any]:
        """
        Generate SQL using enhanced Bedrock integration with intelligent model selection
        
        Args:
            query: Natural language query
            model_preference: Preferred model (optional)
            use_fallback: Whether to use original system as fallback
            
        Returns:
            Dict with generated SQL and metadata
        """
        start_time = time.time()
        
        try:
            # Step 1: Model Selection
            if model_preference:
                selected_model = model_preference
                model_selection = {
                    'selected_model': model_preference,
                    'reasoning': f"User specified preference: {model_preference}",
                    'complexity_analysis': self.model_router.analyze_query_complexity(query)
                }
            else:
                model_selection = self.model_router.select_optimal_model(query)
                selected_model = model_selection['selected_model']
            
            logger.info(f"Selected model: {selected_model} - {model_selection['reasoning']}")
            
            # Step 2: Generate SQL with selected model
            if selected_model.startswith('claude'):
                sql_result = self._generate_with_bedrock(query, selected_model)
            else:
                # Use original system for non-Bedrock models
                sql_result = self._generate_with_original(query, selected_model)
            
            # Step 3: Process results
            generation_time = time.time() - start_time
            
            if sql_result.get('success', False):
                return {
                    'success': True,
                    'sql': sql_result.get('content', ''),
                    'model_used': selected_model,
                    'model_selection': model_selection,
                    'generation_time': generation_time,
                    'enhanced_features': {
                        'bedrock_integration': True,
                        'intelligent_routing': True,
                        'complexity_analysis': model_selection['complexity_analysis']
                    },
                    'metadata': sql_result.get('metadata', {}),
                    'usage': sql_result.get('usage', {})
                }
            else:
                # Handle failure with fallback
                if use_fallback and self.original_available and selected_model.startswith('claude'):
                    logger.warning(f"Bedrock model {selected_model} failed, trying fallback")
                    return self._generate_with_original(query, 'gpt-4o-mini')
                else:
                    return {
                        'success': False,
                        'error': sql_result.get('error', 'Unknown error'),
                        'model_used': selected_model,
                        'model_selection': model_selection,
                        'generation_time': generation_time
                    }
                    
        except Exception as e:
            logger.error(f"Enhanced SQL generation failed: {e}")
            
            # Emergency fallback to original system
            if use_fallback and self.original_available:
                logger.info("Using emergency fallback to original system")
                return self._generate_with_original(query, 'gpt-4o-mini')
            else:
                return {
                    'success': False,
                    'error': f"Enhanced generation failed: {str(e)}",
                    'generation_time': time.time() - start_time
                }
    
    def _generate_with_bedrock(self, query: str, model: str) -> Dict[str, Any]:
        """Generate SQL using Bedrock Claude models with Pinecone schema retrieval"""
        
        # CRITICAL FIX: Retrieve schema from Pinecone BEFORE generating SQL
        # This prevents hallucinations by providing actual column information
        try:
            from sqlgen import retrieve_docs_semantic
            from sqlgen_pinecone import retrieve_docs_semantic_pinecone
            
            # Try Pinecone first, fallback to ChromaDB
            try:
                schema_result = retrieve_docs_semantic_pinecone(query, k=150)
                if schema_result.get('success', False) and schema_result.get('docs'):
                    docs = schema_result['docs']
                    logger.info(f"Retrieved {len(docs)} schema documents from Pinecone for SQL generation")
                else:
                    logger.warning("Pinecone retrieval failed, trying ChromaDB fallback")
                    schema_result = retrieve_docs_semantic(query, k=150)
                    docs = schema_result.get('docs', [])
            except Exception as pinecone_error:
                logger.warning(f"Pinecone retrieval failed: {pinecone_error}, using ChromaDB fallback")
                schema_result = retrieve_docs_semantic(query, k=150)
                docs = schema_result.get('docs', [])
            
            if not docs:
                logger.warning("No schema documents retrieved, using basic prompt")
                enhanced_prompt = self._create_enhanced_prompt(query)
            else:
                # Build enhanced prompt with actual schema from Pinecone
                enhanced_prompt = self._create_enhanced_prompt_with_schema(query, docs)
                
        except Exception as schema_error:
            logger.error(f"Schema retrieval failed: {schema_error}, using basic prompt")
            enhanced_prompt = self._create_enhanced_prompt(query)
        
        try:
            if model == 'claude-haiku':
                result = self.bedrock_client.call_claude_haiku(enhanced_prompt)
            elif model == 'claude-sonnet':
                result = self.bedrock_client.call_claude_sonnet(enhanced_prompt)
            elif model == 'claude-opus':
                result = self.bedrock_client.call_claude_opus(enhanced_prompt)
            else:
                raise ValueError(f"Unknown Bedrock model: {model}")
            
            if result.get('success', False):
                # Extract SQL from response
                content = result.get('content', '')
                sql = self._extract_sql_from_response(content)
                
                return {
                    'success': True,
                    'content': sql,
                    'metadata': result.get('metadata', {}),
                    'usage': result.get('usage', {}),
                    'raw_response': content
                }
            else:
                return result
                
        except Exception as e:
            logger.error(f"Bedrock generation failed: {e}")
            return {
                'success': False,
                'error': f"Bedrock generation error: {str(e)}",
                'model': model
            }
    
    def _generate_with_original(self, query: str, model: str) -> Dict[str, Any]:
        """Generate SQL using original system"""
        try:
            result = self.original_generate(query, model=model)
            
            # Adapt original result format to enhanced format
            if 'llm_sql' in result:
                return {
                    'success': True,
                    'content': result['llm_sql'],
                    'metadata': {'system': 'original'},
                    'raw_response': result
                }
            elif 'error' in result:
                return {
                    'success': False,
                    'error': result['error']
                }
            else:
                return {
                    'success': False,
                    'error': 'Unknown response format from original system'
                }
                
        except Exception as e:
            logger.error(f"Original system generation failed: {e}")
            return {
                'success': False,
                'error': f"Original system error: {str(e)}"
            }
    
    def _create_enhanced_prompt_with_schema(self, query: str, docs: List[Dict]) -> str:
        """Create enhanced prompt with actual schema from Pinecone/ChromaDB"""
        
        # Extract schema information from documents
        from sqlgen import summarize_relevant_tables
        
        tables_summary = summarize_relevant_tables(docs, query)
        
        # Build schema section with actual columns
        schema_section = "\n\nAVAILABLE SCHEMA (Use ONLY these tables and columns):\n\n"
        
        for table, info in tables_summary.items():
            columns = list(info['columns'])[:50]  # Limit to prevent prompt overflow
            table_comment = info.get('table_comment', '')
            
            schema_section += f"TABLE: {table}\n"
            if table_comment:
                schema_section += f"DESCRIPTION: {table_comment}\n"
            schema_section += f"COLUMNS: {', '.join(columns)}\n\n"
        
        prompt = f"""You are an expert Oracle SQL developer specializing in Oracle Fusion Applications. Your task is to convert natural language queries into accurate Oracle SQL statements.

CRITICAL RULES:
1. Generate ONLY the SQL query - no explanations or additional text
2. Use ONLY tables and columns from the AVAILABLE SCHEMA below
3. NEVER invent or hallucinate column names - if a column doesn't exist in the schema, DON'T use it
4. Use proper Oracle syntax and functions
5. Include appropriate table aliases for readability
6. Use proper JOIN syntax for related tables
7. Handle dates with TO_DATE() function
8. Use appropriate WHERE clauses for filtering
{schema_section}
USER QUERY: {query}

Generate the Oracle SQL query:"""

        return prompt
    
    def _create_enhanced_prompt(self, query: str) -> str:
        """Create basic prompt when schema retrieval fails"""
        
        prompt = f"""You are an expert Oracle SQL developer specializing in Oracle Fusion Applications. Your task is to convert natural language queries into accurate Oracle SQL statements.

IMPORTANT GUIDELINES:
1. Generate ONLY the SQL query - no explanations or additional text
2. Use proper Oracle syntax and functions
3. Include appropriate table aliases for readability
4. Use proper JOIN syntax for related tables
5. Handle dates with TO_DATE() function
6. Use appropriate WHERE clauses for filtering
7. Include proper column selections based on the query intent

COMMON ORACLE FUSION TABLES:
- AP_INVOICES_ALL (Accounts Payable invoices)
- AP_INVOICE_DISTRIBUTIONS_ALL (Invoice line items)
- AP_SUPPLIERS (Supplier information)
- AR_CASH_RECEIPTS_ALL (Customer receipts)
- AR_CUSTOMERS (Customer information)
- GL_JE_HEADERS (Journal entry headers)
- GL_JE_LINES (Journal entry lines)
- GL_CODE_COMBINATIONS (Chart of accounts)

USER QUERY: {query}

Generate the Oracle SQL query:"""

        return prompt
    
    def _extract_sql_from_response(self, response: str) -> str:
        """Extract SQL query from Claude response"""
        
        # Remove any markdown formatting
        sql = response.strip()
        
        # Remove code block markers
        if sql.startswith('```sql'):
            sql = sql[6:]
        elif sql.startswith('```'):
            sql = sql[3:]
        
        if sql.endswith('```'):
            sql = sql[:-3]
        
        sql = sql.strip()
        
        # Ensure it starts with SELECT
        if not sql.upper().startswith('SELECT'):
            # Try to find SELECT in the response
            lines = sql.split('\n')
            for i, line in enumerate(lines):
                if line.strip().upper().startswith('SELECT'):
                    sql = '\n'.join(lines[i:])
                    break
        
        return sql

# Convenience functions for easy integration
def create_bedrock_client(region: str = None, access_key: str = None, secret_key: str = None) -> BedrockClient:
    """Create and return a configured Bedrock client"""
    return BedrockClient(region_name=region, access_key_id=access_key, secret_access_key=secret_key)

def create_enhanced_generator(bedrock_client: BedrockClient = None) -> EnhancedSQLGenerator:
    """Create and return an enhanced SQL generator"""
    return EnhancedSQLGenerator(bedrock_client=bedrock_client)

def generate_sql_with_bedrock(query: str, model: str = None, bedrock_client: BedrockClient = None) -> Dict[str, Any]:
    """Convenience function for generating SQL with Bedrock"""
    generator = create_enhanced_generator(bedrock_client)
    return generator.generate_sql_enhanced(query, model_preference=model)
