"""
Pinecone integration for sqlgen.py - replaces local ChromaDB for Streamlit Cloud deployment.
"""

import os
import json
import logging
from typing import List, Dict, Any, Optional
import pinecone
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

# Global caches
_pinecone_index_cache = None
_embed_model_cache = None

def get_pinecone_index():
    """Get cached Pinecone index or create it once"""
    global _pinecone_index_cache
    
    if _pinecone_index_cache is None:
        try:
            # Load configuration from environment variables
            api_key = os.getenv("PINECONE_API_KEY")
            environment = os.getenv("PINECONE_ENVIRONMENT")
            index_name = os.getenv("PINECONE_INDEX_NAME")
            
            if not all([api_key, environment, index_name]):
                raise ValueError("Missing Pinecone environment variables: PINECONE_API_KEY, PINECONE_ENVIRONMENT, PINECONE_INDEX_NAME")
            
            # Initialize Pinecone client (v3.0.0 API)
            try:
                pc = pinecone.Pinecone(api_key=api_key)
                logger.info(f"Pinecone client initialized successfully")
            except Exception as init_error:
                logger.error(f"Failed to initialize Pinecone client: {init_error}")
                raise init_error
            
            # Get index
            try:
                index = pc.Index(index_name)
                logger.info(f"Pinecone index '{index_name}' retrieved successfully")
            except Exception as index_error:
                logger.error(f"Failed to get Pinecone index '{index_name}': {index_error}")
                raise index_error
            if index is None:
                raise ValueError(f"Failed to get Pinecone index '{index_name}' - index not found or inaccessible")
            
            _pinecone_index_cache = index
            logger.info("Pinecone index connected and cached")
            
        except Exception as e:
            logger.error(f"Failed to connect to Pinecone: {e}")
            raise e
    
    return _pinecone_index_cache

def get_embed_model():
    """Get cached embedding model or load it once"""
    global _embed_model_cache
    
    if _embed_model_cache is None:
        try:
            logger.info("Loading embedding model: thenlper/gte-base")
            _embed_model_cache = SentenceTransformer(
                'thenlper/gte-base',
                device='cpu',
                trust_remote_code=True
            )
            logger.info("Embedding model loaded and cached")
        except Exception as e:
            logger.warning(f"Failed to load thenlper/gte-base, trying fallback: {e}")
            try:
                _embed_model_cache = SentenceTransformer('all-MiniLM-L6-v2', device='cpu')
                logger.info("Fallback embedding model loaded: all-MiniLM-L6-v2")
            except Exception as fallback_error:
                logger.error(f"Failed to load fallback model: {fallback_error}")
                raise fallback_error
    
    return _embed_model_cache

def retrieve_docs_semantic_pinecone(user_query: str, k: int = 10) -> Dict[str, Any]:
    """
    Retrieve semantically relevant documents from Pinecone.
    Replaces the ChromaDB-based retrieval for Streamlit Cloud deployment.
    Now includes primary table candidates filtering for better table selection.
    """
    try:
        # Get embedding model and Pinecone index
        embed_model = get_embed_model()
        index = get_pinecone_index()
        
        # ENHANCED: Get primary table candidates for better filtering
        try:
            from sqlgen import get_primary_table_candidates
            primary_candidates = get_primary_table_candidates(user_query)
            logger.info(f"Identified {len(primary_candidates)} primary table candidates: {primary_candidates[:5]}...")
        except ImportError:
            logger.warning("Could not import get_primary_table_candidates, proceeding without filtering")
            primary_candidates = []
        
        # Generate query embedding
        query_embedding = embed_model.encode([user_query])[0].tolist()
        logger.info(f"Generated query embedding for: '{user_query}'")
        
        # Search Pinecone with higher k to allow for filtering
        search_k = k * 3 if primary_candidates else k  # Get more results if we need to filter
        
        search_results = index.query(
            vector=query_embedding,
            top_k=search_k,
            include_metadata=True
        )
        
        logger.info(f"Pinecone returned {len(search_results.matches)} matches for query: '{user_query}'")
        
        # ENHANCED: Filter results by primary table candidates if available
        filtered_matches = []
        if primary_candidates:
            logger.info(f"Filtering results by {len(primary_candidates)} primary table candidates")
            primary_candidates_upper = [table.upper() for table in primary_candidates]
            
            # CRITICAL FIX: Also include audit table variants (tables with trailing underscore)
            # because they contain the same column metadata
            primary_candidates_with_audit = set(primary_candidates_upper)
            for table in primary_candidates_upper:
                primary_candidates_with_audit.add(f"{table}_")  # Add audit variant
            
            for match in search_results.matches:
                if match.metadata and match.metadata.get('table'):
                    table_name = match.metadata['table'].upper()
                    
                    # Check if table matches primary candidates OR their audit variants
                    is_match = (table_name in primary_candidates_with_audit)
                    
                    # Also check if table without trailing underscore is in candidates
                    if table_name.endswith('_'):
                        base_table = table_name[:-1]
                        if base_table in primary_candidates_upper:
                            is_match = True
                    
                    if is_match:
                        filtered_matches.append(match)
                        logger.debug(f"✅ Match included: {table_name} (score={match.score:.3f})")
                    else:
                        logger.debug(f"❌ Match filtered out: {table_name} (not in primary candidates)")
                else:
                    # Include matches without table metadata to avoid losing important documents
                    filtered_matches.append(match)
                    logger.debug(f"⚠️ Match included (no table metadata): score={match.score:.3f}")
            
            logger.info(f"Filtered from {len(search_results.matches)} to {len(filtered_matches)} matches using primary candidates")
            
            # If we have too few results after filtering, include some high-scoring non-candidate matches
            if len(filtered_matches) < k and len(search_results.matches) > len(filtered_matches):
                remaining_matches = [m for m in search_results.matches if m not in filtered_matches]
                # Sort by score and take top matches to reach target k
                remaining_matches.sort(key=lambda x: x.score, reverse=True)
                needed = k - len(filtered_matches)
                filtered_matches.extend(remaining_matches[:needed])
                logger.info(f"Added {needed} high-scoring non-candidate matches to reach target k={k}")
        else:
            filtered_matches = search_results.matches
            logger.info("No primary candidates available, using all matches")
        
        # Extract documents and metadata in ChromaDB-compatible format
        docs = []
        skipped_matches = 0
        
        for i, match in enumerate(filtered_matches):
            if match.metadata and "document" in match.metadata:
                # Create ChromaDB-compatible document format
                doc = {
                    "text": match.metadata["document"],
                    "meta": match.metadata
                }
                docs.append(doc)
                logger.debug(f"Match {i+1}: score={match.score:.3f}, table={match.metadata.get('table', 'unknown')}")
            else:
                skipped_matches += 1
                logger.warning(f"Match {i+1}: Skipped - missing metadata or document field. Metadata keys: {list(match.metadata.keys()) if match.metadata else 'None'}")
        
        if skipped_matches > 0:
            logger.warning(f"Skipped {skipped_matches} matches due to missing metadata/document fields")
        
        if len(docs) == 0:
            logger.error(f"No valid documents retrieved from Pinecone for query: '{user_query}'")
            # Try a broader search with different query terms
            logger.info("Attempting broader search with simplified query terms...")
            
            # Extract key terms from the query
            import re
            key_terms = re.findall(r'\b\w+\b', user_query.lower())
            simplified_query = " ".join(key_terms[:3])  # Use first 3 terms
            
            if simplified_query != user_query.lower():
                logger.info(f"Trying simplified query: '{simplified_query}'")
                simplified_embedding = embed_model.encode([simplified_query])[0].tolist()
                simplified_results = index.query(
                    vector=simplified_embedding,
                    top_k=k*2,  # Try more results
                    include_metadata=True
                )
                
                for match in simplified_results.matches:
                    if match.metadata and "document" in match.metadata:
                        doc = {
                            "text": match.metadata["document"],
                            "meta": match.metadata
                        }
                        docs.append(doc)
                
                logger.info(f"Broader search found {len(docs)} additional documents")
        
        logger.info(f"Final result: Retrieved {len(docs)} documents from Pinecone")
        
        return {
            "docs": docs,
            "success": True,
            "query": user_query,
            "total_matches": len(search_results.matches),
            "valid_documents": len(docs)
        }
        
    except Exception as e:
        logger.error(f"Pinecone retrieval failed: {e}")
        return {
            "docs": [],
            "metadatas": [],
            "distances": [],
            "success": False,
            "error": str(e),
            "query": user_query
        }

def test_pinecone_connection() -> bool:
    """Test Pinecone connection and return status"""
    try:
        index = get_pinecone_index()
        if index is None:
            logger.error("Failed to get Pinecone index")
            return False
            
        stats = index.describe_index_stats()
        logger.info(f"Pinecone connection successful. Index stats: {stats}")
        return True
    except Exception as e:
        logger.error(f"Pinecone connection failed: {e}")
        return False

def diagnose_pinecone_issues(user_query: str = "supplier invoice") -> Dict[str, Any]:
    """
    Comprehensive diagnostic function to identify Pinecone issues.
    """
    diagnosis = {
        "connection_ok": False,
        "index_stats": None,
        "embedding_model_ok": False,
        "sample_query_results": None,
        "metadata_format_ok": False,
        "total_documents": 0,
        "issues": []
    }
    
    index = None
    test_embedding = None
    
    try:
        # 1. Test connection
        logger.info("Testing Pinecone connection...")
        index = get_pinecone_index()
        if index is None:
            diagnosis["issues"].append("Failed to get Pinecone index - client initialization failed")
            return diagnosis
            
        logger.info("Getting index stats...")
        stats = index.describe_index_stats()
        diagnosis["connection_ok"] = True
        diagnosis["index_stats"] = stats
        diagnosis["total_documents"] = stats.get("total_vector_count", 0)
        
        if diagnosis["total_documents"] == 0:
            diagnosis["issues"].append("Pinecone index is empty - no documents found")
            return diagnosis
            
    except Exception as e:
        logger.error(f"Pinecone connection test failed: {e}")
        diagnosis["issues"].append(f"Connection failed: {e}")
        return diagnosis
    
    try:
        # 2. Test embedding model
        embed_model = get_embed_model()
        test_embedding = embed_model.encode([user_query])[0].tolist()
        diagnosis["embedding_model_ok"] = True
        
    except Exception as e:
        diagnosis["issues"].append(f"Embedding model failed: {e}")
        return diagnosis
    
    try:
        # 3. Test sample query (only if we have both index and embedding)
        if index is not None and test_embedding is not None:
            search_results = index.query(
                vector=test_embedding,
                top_k=5,
                include_metadata=True
            )
            
            diagnosis["sample_query_results"] = {
                "matches_found": len(search_results.matches),
                "matches": []
            }
            
            for i, match in enumerate(search_results.matches[:3]):  # Show first 3 matches
                match_info = {
                    "score": match.score,
                    "metadata_keys": list(match.metadata.keys()) if match.metadata else [],
                    "has_document": "document" in (match.metadata or {}),
                    "document_preview": match.metadata.get("document", "")[:100] if match.metadata and "document" in match.metadata else "No document field"
                }
                diagnosis["sample_query_results"]["matches"].append(match_info)
            
            if len(search_results.matches) == 0:
                diagnosis["issues"].append("No matches found for sample query - embedding or index content issue")
            else:
                # Check metadata format
                sample_match = search_results.matches[0]
                if sample_match.metadata and "document" in sample_match.metadata:
                    diagnosis["metadata_format_ok"] = True
                else:
                    diagnosis["issues"].append("Metadata format incorrect - missing 'document' field")
        else:
            diagnosis["issues"].append("Cannot perform sample query - missing index or embedding")
                
    except Exception as e:
        diagnosis["issues"].append(f"Sample query failed: {e}")
    
    return diagnosis

# Environment variable setup for Streamlit Cloud
def setup_pinecone_from_env():
    """Setup Pinecone using environment variables (for Streamlit Cloud)"""
    try:
        api_key = os.getenv("PINECONE_API_KEY")
        index_name = os.getenv("PINECONE_INDEX_NAME", "sqlgen-schema-docs")
        environment = os.getenv("PINECONE_ENVIRONMENT", "us-east-1-aws")
        
        if not api_key:
            logger.error("PINECONE_API_KEY environment variable not set")
            return False
        
        # Create config file from environment variables
        config = {
            "pinecone_api_key": api_key,
            "pinecone_index_name": index_name,
            "pinecone_environment": environment
        }
        
        with open("pinecone_config.json", "w") as f:
            json.dump(config, f, indent=2)
        
        logger.info("Pinecone configuration created from environment variables")
        return True
        
    except Exception as e:
        logger.error(f"Failed to setup Pinecone from environment: {e}")
        return False
