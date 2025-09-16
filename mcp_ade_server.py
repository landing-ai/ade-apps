"""MCP ADE Server - Model Context Protocol server for LandingAI's Agentic Document Extraction API.

This server provides MCP tools for extracting structured and unstructured data from PDFs and images
using LandingAI's ADE API. It supports multiple extraction methods including raw text chunks,
Pydantic models, and JSON schemas.

Key Features:
- Extract all text chunks with metadata from documents (bounding boxes, page numbers)
- Process local PDF/image files directly without base64 encoding
- Extract structured data using custom Pydantic models with type validation
- Extract data based on JSON schema definitions with field-level confidence scores
- Validate JSON schemas against ADE's documented requirements

Environment Requirements:
- VISION_AGENT_API_KEY: Required API key from LandingAI for ADE access
"""

from typing import Any, AsyncIterator, Optional, Dict, List, Union
from mcp.server.fastmcp import FastMCP, Context
from dotenv import load_dotenv
import os
import json
import base64
from dataclasses import dataclass
from contextlib import asynccontextmanager
import sys
import asyncio
from pydantic import BaseModel, Field

# CRITICAL: Import agentic-doc with stdout suppressed to prevent config output
# The agentic-doc library outputs configuration data to stdout on import which
# breaks MCP protocol communication. We temporarily redirect stdout to /dev/null
# during the import to prevent this interference.
old_stdout = sys.stdout
sys.stdout = open(os.devnull, 'w')
try:
    from agentic_doc.parse import parse
    from agentic_doc.common import ParsedDocument
    from agentic_doc.config import ParseConfig
finally:
    sys.stdout.close()
    sys.stdout = old_stdout

class SuppressOutput:
    """Context manager to suppress stdout and stderr output from the agentic-doc library.
    
    The agentic-doc library produces various status outputs during document processing
    that can interfere with MCP's stdio-based communication protocol. This context
    manager temporarily redirects both stdout and stderr to /dev/null to ensure
    clean MCP communication while preserving the ability to return structured data.
    
    Usage:
        with SuppressOutput():
            results = await asyncio.to_thread(parse, document_data)
    """
    def __enter__(self):
        self.old_stdout = sys.stdout
        self.old_stderr = sys.stderr
        sys.stdout = open(os.devnull, 'w')
        sys.stderr = open(os.devnull, 'w')

    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.stdout.close()
        sys.stderr.close()
        sys.stdout = self.old_stdout
        sys.stderr = self.old_stderr

def _format_raw_response(result: ParsedDocument) -> Dict[str, Any]:
    """Formats raw extraction results from ParsedDocument into a structured JSON response.
    
    This helper function transforms the ADE ParsedDocument object into a more readable
    and structured format suitable for MCP tool responses. It extracts both the full
    markdown representation and individual chunks with their metadata.
    
    Args:
        result: ParsedDocument object from agentic-doc containing extraction results
        
    Returns:
        Dictionary containing:
        - markdown: Complete extracted text in markdown format
        - chunks: List of text chunks with:
            - type: Chunk type (e.g., 'text', 'table', 'header')
            - content: The actual text content of the chunk
            - page: Page number where chunk appears
            - chunk_id: Unique identifier for the chunk
            - grounding: List of bounding box coordinates and page numbers
                - bbox: Dictionary with left, top, right, bottom coordinates
                - page: Page number for this bounding box
    """
    return {
        "markdown": result.markdown,
        "chunks": [
            {
                "type": chunk.chunk_type.value if hasattr(chunk, 'chunk_type') and hasattr(chunk.chunk_type, 'value') else str(chunk.chunk_type),
                "content": chunk.text,
                "page": chunk.grounding[0].page if chunk.grounding else None,
                "chunk_id": chunk.chunk_id,
                "grounding": [{"bbox": {"l": g.box.l, "t": g.box.t, "r": g.box.r, "b": g.box.b}, "page": g.page} for g in chunk.grounding] if chunk.grounding else []
            } for chunk in result.chunks
        ]
    }

def load_environment_variables() -> None:
    """Loads and validates required environment variables from .env file.
    
    This function loads environment variables from a .env file in the project root
    and validates that the required VISION_AGENT_API_KEY is present. This key is
    necessary for authenticating with LandingAI's ADE API.
    
    Raises:
        ValueError: If VISION_AGENT_API_KEY environment variable is not set
        
    Note:
        The .env file should be in the project root directory and contain:
        VISION_AGENT_API_KEY=your_api_key_here
    """
    load_dotenv()
    if not os.getenv("VISION_AGENT_API_KEY"):
        raise ValueError("Missing required environment variable: VISION_AGENT_API_KEY")

@dataclass
class AppContext:
    """Application context for managing server state and resources.
    
    Currently empty but provides a structure for future extensions such as:
    - Connection pooling for API clients
    - Caching mechanisms
    - Shared state between tool invocations
    """
    pass

@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    """Manages the lifecycle of the MCP server application.
    
    This async context manager handles server initialization and cleanup.
    It yields an AppContext that can be used to share state across tool invocations.
    
    Args:
        server: FastMCP server instance
        
    Yields:
        AppContext: Application context for the server session
    """
    # Server initialization logic would go here
    yield AppContext()
    # Server cleanup logic would go here

# Initialize the FastMCP server with the ADE server name and lifecycle manager
# This creates the MCP server instance that will handle tool registrations and requests
mcp = FastMCP("ade-server", lifespan=app_lifespan)

@mcp.tool()
async def ade_extract_raw_chunks(ctx: Context, pdf_base64: str) -> str:
    """Extracts all raw text chunks and their metadata from a base64-encoded document.
    
    This tool performs comprehensive text extraction from documents without any
    structure requirements. It returns all detected text chunks along with their
    locations, types, and page information. This is useful for:
    - Initial document exploration
    - Full-text search applications
    - When you need all content without specific structure
    
    Args:
        ctx: MCP context object (provided by framework)
        pdf_base64: Base64-encoded PDF or image file content
        
    Returns:
        JSON string containing:
        - markdown: Complete document text in markdown format
        - chunks: Array of text chunks with type, content, page, and bounding box info
        
    Example Response:
        {
          "markdown": "# Document Title\n\nContent here...",
          "chunks": [
            {
              "type": "header",
              "content": "Document Title",
              "page": 1,
              "chunk_id": "chunk_001",
              "grounding": [{"bbox": {"l": 10, "t": 10, "r": 200, "b": 30}, "page": 1}]
            }
          ]
        }
    """
    try:
        # Decode base64 and parse document with output suppressed
        with SuppressOutput():
            results = await asyncio.to_thread(parse, base64.b64decode(pdf_base64))
        if not results: return "❌ No results returned"
        response = _format_raw_response(results[0])
        return json.dumps(response, indent=2)
    except Exception as e:
        return f"Error during raw extraction: {str(e)}"

@mcp.tool()
async def ade_extract_from_path(ctx: Context, path: str) -> str:
    """Extracts raw text chunks from a local file (PDF, image, etc.) using its file path.
    
    This tool is a convenience method for processing local files without needing
    to base64-encode them first. It supports the same document types as the API:
    - PDF files
    - Images (PNG, JPG, JPEG, etc.)
    - Other document formats supported by ADE
    
    Args:
        ctx: MCP context object (provided by framework)
        path: Absolute or relative file path to the document
        
    Returns:
        JSON string containing:
        - file_path: The processed file path
        - extraction_result: Same format as ade_extract_raw_chunks
            - markdown: Complete document text
            - chunks: Array of text chunks with metadata
            
    Error Returns:
        - "❌ File not found: [path]" if file doesn't exist
        - Error message string if extraction fails
        
    Example Usage:
        path = "/Users/john/Documents/invoice.pdf"
        result = await ade_extract_from_path(ctx, path)
    """
    try:
        # Parse document directly from file path
        with SuppressOutput():
            results = await asyncio.to_thread(parse, path)
        if not results: return "❌ No results returned"
        
        result = results[0]
        response = {
            "file_path": getattr(result, 'source', path),
            "extraction_result": _format_raw_response(result)
        }
        return json.dumps(response, indent=2)
    except FileNotFoundError:
        return f"❌ File not found: {path}"
    except Exception as e:
        return f"Error during file path extraction: {str(e)}"

@mcp.tool()
async def ade_extract_with_pydantic(ctx: Context, pdf_base64: str, pydantic_model_code: str) -> str:
    """Extracts structured data from documents using a custom Pydantic model definition.
    
    This tool allows you to define a Pydantic BaseModel as Python code, which will be
    used to extract structured, type-validated data from the document. The ADE API
    will attempt to find and extract data matching your model's schema.
    
    Key Features:
    - Type validation using Pydantic's type system
    - Field-level confidence scores for extracted values
    - Raw text references showing where data was found
    - Support for nested models and complex types
    
    Args:
        ctx: MCP context object (provided by framework)
        pdf_base64: Base64-encoded PDF or image file content
        pydantic_model_code: Python code defining a Pydantic BaseModel class
        
    Returns:
        JSON string containing:
        - extraction_error: Any errors during extraction (null if successful)
        - extracted_data: Dictionary of extracted data matching the model
        - field_details: Per-field metadata including:
            - confidence: Confidence score (0-1) for the extraction
            - raw_text: Actual text found in the document
            - chunk_references: IDs of chunks where data was found
            
    Example Model Code:
        class Invoice(BaseModel):
            invoice_number: str = Field(description="Invoice or receipt number")
            total_amount: float = Field(description="Total amount due")
            date: str = Field(description="Invoice date")
            line_items: List[dict] = Field(description="List of items")
            
    Notes:
    - The last BaseModel defined in the code will be used
    - Standard Pydantic imports are automatically added
    - Field descriptions help improve extraction accuracy
    """
    try:
        # Prepare the code for execution with necessary imports
        # These imports are automatically added to support common Pydantic patterns
        full_code = f"from pydantic import BaseModel, Field\nfrom typing import List, Optional\n\n{pydantic_model_code}"
        
        # Execute the model code in an isolated scope
        local_scope = {}
        exec(full_code, globals(), local_scope)
        
        # Find the last defined Pydantic model in the executed code
        # This allows users to define helper models before the main extraction model
        extraction_model = None
        for var in reversed(local_scope.values()):
            if isinstance(var, type) and issubclass(var, BaseModel) and var is not BaseModel:
                extraction_model = var
                break
        
        if not extraction_model:
            return "❌ No Pydantic BaseModel class found in the provided code."

        # Configure and execute extraction with the Pydantic model
        config_obj = ParseConfig(extraction_model=extraction_model)
        with SuppressOutput():
            results = await asyncio.to_thread(parse, base64.b64decode(pdf_base64), config=config_obj)
        if not results: return "❌ No results returned from parsing."
        
        # Format response with extracted data and metadata
        result = results[0]
        response = {
            "extraction_error": result.extraction_error,
            "extracted_data": result.extraction.dict() if result.extraction else None,
            "field_details": {
                field: {
                    "confidence": meta.confidence,
                    "raw_text": meta.raw_text,
                    "chunk_references": meta.chunk_references
                } for field, meta in result.extraction_metadata.items() if meta
            } if result.extraction_metadata else {}
        }
        return json.dumps(response, indent=2)

    except Exception as e:
        return f"Error during Pydantic-based extraction: {str(e)}"

@mcp.tool()
async def ade_validate_json_schema(ctx: Context, schema: Dict[str, Any]) -> str:
    """Validates a JSON schema against ADE's documented requirements and limitations.
    
    The ADE API has specific requirements for JSON schemas to ensure reliable
    extraction. This tool checks your schema against all documented rules before
    you attempt extraction, helping avoid runtime errors.
    
    Validation Rules:
    1. Top-level type must be 'object' (not array or primitive)
    2. No prohibited keywords: allOf, not, dependentRequired, dependentSchemas, if/then/else
    3. Maximum nesting depth of 5 levels
    4. Objects must have 'properties' field defined
    5. Arrays must have 'items' field defined
    6. Type arrays cannot mix 'object' or 'array' with primitives (use anyOf instead)
    
    Args:
        ctx: MCP context object (provided by framework)
        schema: JSON schema dictionary to validate
        
    Returns:
        Success: "✅ Schema is valid according to ADE documentation rules."
        Failure: "❌ Schema validation failed:" followed by list of violations
        
    Example Valid Schema:
        {
          "type": "object",
          "properties": {
            "invoice_number": {"type": "string"},
            "items": {
              "type": "array",
              "items": {
                "type": "object",
                "properties": {
                  "name": {"type": "string"},
                  "price": {"type": "number"}
                }
              }
            }
          }
        }
        
    Common Issues:
    - Using 'allOf' for composition (use nested properties instead)
    - Missing 'properties' in object definitions
    - Exceeding 5 levels of nesting
    - Using type arrays with mixed complex/primitive types
    """
    errors = []
    
    # Check top-level type requirement
    if schema.get("type") != "object":
        errors.append("Rule Broken: Top-level 'type' must be 'object'.")

    # Define keywords that ADE doesn't support
    prohibited_keywords = {'allOf', 'not', 'dependentRequired', 'dependentSchemas', 'if', 'then', 'else'}

    def traverse(obj, path, depth):
        """Recursively traverse schema to check for violations."""
        # Check depth limit
        if depth > 5:
            errors.append(f"Rule Broken: Schema depth exceeds 5 at path '{path}'.")
            return

        if isinstance(obj, dict):
            for key, value in obj.items():
                new_path = f"{path}.{key}"
                
                # Check for prohibited keywords
                if key in prohibited_keywords:
                    errors.append(f"Rule Broken: Prohibited keyword '{key}' found at path '{new_path}'.")
                
                # Check for invalid type arrays
                if key == "type" and isinstance(value, list) and any(t in value for t in ["object", "array"]):
                    errors.append(f"Rule Broken: Type array at path '{new_path}' cannot contain 'object' or 'array'. Use 'anyOf' instead.")

                # Check object has properties
                if obj.get("type") == "object" and "properties" not in obj:
                     errors.append(f"Rule Broken: Object at path '{path}' must have a 'properties' field.")
                
                # Check array has items
                if obj.get("type") == "array" and "items" not in obj:
                     errors.append(f"Rule Broken: Array at path '{path}' must have an 'items' field.")
                
                # Recurse into nested structures
                traverse(value, new_path, depth + 1)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                traverse(item, f"{path}[{i}]", depth + 1)

    # Start traversal from root
    traverse(schema, "root", 1)
    
    # Return validation results
    if not errors:
        return "✅ Schema is valid according to ADE documentation rules."
    else:
        # Remove duplicates and format error list
        error_list = "\n".join(f"- {e}" for e in set(errors))
        return f"❌ Schema validation failed:\n{error_list}"

@mcp.tool()
async def ade_extract_with_json_schema(ctx: Context, pdf_base64: str, schema: Dict[str, Any]) -> str:
    """Extracts structured data from documents based on a JSON schema definition.
    
    This tool provides schema-based extraction without needing to write Python code.
    The ADE API will analyze the document and extract data matching your schema's
    structure, with automatic type coercion and validation.
    
    Key Features:
    - Define expected data structure using standard JSON Schema
    - Automatic validation against ADE requirements before extraction
    - Field-level confidence scores and source text references
    - Support for nested objects and arrays
    - No code execution required (safer than Pydantic method)
    
    Args:
        ctx: MCP context object (provided by framework)
        pdf_base64: Base64-encoded PDF or image file content
        schema: JSON schema dictionary defining the expected structure
        
    Returns:
        JSON string containing:
        - extraction_error: Any errors during extraction (null if successful)
        - extracted_data: JSON object matching the provided schema
        - field_details: Metadata for each extracted field:
            - confidence: Extraction confidence score (0-1)
            - raw_text: Original text from the document
            - chunk_references: IDs of source chunks
            
    Example Schema:
        {
          "type": "object",
          "properties": {
            "company_name": {
              "type": "string",
              "description": "Name of the company"
            },
            "total_amount": {
              "type": "number",
              "description": "Total amount on the invoice"
            },
            "line_items": {
              "type": "array",
              "items": {
                "type": "object",
                "properties": {
                  "description": {"type": "string"},
                  "quantity": {"type": "number"},
                  "price": {"type": "number"}
                }
              }
            }
          }
        }
        
    Best Practices:
    - Always validate schema first using ade_validate_json_schema
    - Add descriptions to fields to improve extraction accuracy
    - Keep nesting depth under 5 levels
    - Use specific types rather than generic ones
    
    Note: This tool automatically validates the schema before extraction.
    If validation fails, extraction will not proceed.
    """
    try:
        # Always validate schema before attempting extraction
        # This prevents wasted API calls and provides clear error messages
        validation_result = await ade_validate_json_schema(ctx, schema)
        if "❌" in validation_result:
            return f"Schema validation failed. Please fix the schema before extraction.\n{validation_result}"

        # Configure extraction with the validated schema
        config_obj = ParseConfig(extraction_schema=schema)
        with SuppressOutput():
            results = await asyncio.to_thread(parse, base64.b64decode(pdf_base64), config=config_obj)
        if not results: return "❌ No results returned."
        
        # Format the extraction results with metadata
        result = results[0]
        response = {
            "extraction_error": result.extraction_error,
            "extracted_data": result.extraction,
            "field_details": {
                field: {
                    "confidence": meta.confidence, 
                    "raw_text": meta.raw_text, 
                    "chunk_references": meta.chunk_references
                } for field, meta in result.extraction_metadata.items() if meta
            } if result.extraction_metadata else {}
        }
        return json.dumps(response, indent=2)
    except Exception as e:
        return f"Error during JSON schema extraction: {str(e)}"

if __name__ == "__main__":
    """Main entry point for the MCP ADE Server.
    
    This script should be run as an MCP server, typically invoked by Claude Desktop
    or another MCP client. It uses stdio transport for communication, meaning it
    receives JSON-RPC requests via stdin and sends responses via stdout.
    
    The server will:
    1. Load required environment variables (VISION_AGENT_API_KEY)
    2. Initialize the MCP server with registered tools
    3. Listen for and respond to tool invocation requests
    
    Usage:
        Direct execution: python mcp_ade_server.py
        Via uv: uv run mcp-ade-server
        
    Note: This server is designed to be run by MCP clients, not directly by users.
    """
    load_environment_variables()  # Load and validate API key
    mcp.run(transport='stdio')    # Start MCP server on stdio transport