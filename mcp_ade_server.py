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
    """A context manager to suppress stdout and stderr."""
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
    """Helper function to format the raw chunk extraction response."""
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
    """Loads environment variables from a .env file."""
    load_dotenv()
    if not os.getenv("VISION_AGENT_API_KEY"):
        raise ValueError("Missing required environment variable: VISION_AGENT_API_KEY")

@dataclass
class AppContext:
    pass

@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    yield AppContext()

mcp = FastMCP("ade-server", lifespan=app_lifespan)

@mcp.tool()
async def ade_extract_raw_chunks(ctx: Context, pdf_base64: str) -> str:
    """
    Performs basic extraction of all raw text chunks and their metadata from a document.
    """
    try:
        with SuppressOutput():
            results = await asyncio.to_thread(parse, base64.b64decode(pdf_base64))
        if not results: return "❌ No results returned"
        response = _format_raw_response(results[0])
        return json.dumps(response, indent=2)
    except Exception as e:
        return f"Error during raw extraction: {str(e)}"

@mcp.tool()
async def ade_extract_from_path(ctx: Context, path: str) -> str:
    """
    Extracts raw chunks from a single local file path (PDF, image, etc.).
    """
    try:
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
    """
    Extracts data using a Pydantic model defined in a Python code string.
    The last defined Pydantic BaseModel will be used as the extraction model.
    """
    try:
        # Prepare the code for execution with necessary imports
        full_code = f"from pydantic import BaseModel, Field\nfrom typing import List, Optional\n\n{pydantic_model_code}"
        
        local_scope = {}
        exec(full_code, globals(), local_scope)
        
        # Find the last defined Pydantic model in the executed code
        extraction_model = None
        for var in reversed(local_scope.values()):
            if isinstance(var, type) and issubclass(var, BaseModel) and var is not BaseModel:
                extraction_model = var
                break
        
        if not extraction_model:
            return "❌ No Pydantic BaseModel class found in the provided code."

        config_obj = ParseConfig(extraction_model=extraction_model)
        with SuppressOutput():
            results = await asyncio.to_thread(parse, base64.b64decode(pdf_base64), config=config_obj)
        if not results: return "❌ No results returned from parsing."
        
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
    """
    Validates a JSON schema against the rules from the ADE troubleshooting guide.
    """
    errors = []
    if schema.get("type") != "object":
        errors.append("Rule Broken: Top-level 'type' must be 'object'.")

    prohibited_keywords = {'allOf', 'not', 'dependentRequired', 'dependentSchemas', 'if', 'then', 'else'}

    def traverse(obj, path, depth):
        if depth > 5:
            errors.append(f"Rule Broken: Schema depth exceeds 5 at path '{path}'.")
            return

        if isinstance(obj, dict):
            for key, value in obj.items():
                new_path = f"{path}.{key}"
                if key in prohibited_keywords:
                    errors.append(f"Rule Broken: Prohibited keyword '{key}' found at path '{new_path}'.")
                
                if key == "type" and isinstance(value, list) and any(t in value for t in ["object", "array"]):
                    errors.append(f"Rule Broken: Type array at path '{new_path}' cannot contain 'object' or 'array'. Use 'anyOf' instead.")

                if obj.get("type") == "object" and "properties" not in obj:
                     errors.append(f"Rule Broken: Object at path '{path}' must have a 'properties' field.")
                
                if obj.get("type") == "array" and "items" not in obj:
                     errors.append(f"Rule Broken: Array at path '{path}' must have an 'items' field.")
                
                traverse(value, new_path, depth + 1)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                traverse(item, f"{path}[{i}]", depth + 1)

    traverse(schema, "root", 1)
    
    if not errors:
        return "✅ Schema is valid according to ADE documentation rules."
    else:
        error_list = "\n".join(f"- {e}" for e in set(errors))
        return f"❌ Schema validation failed:\n{error_list}"

@mcp.tool()
async def ade_extract_with_json_schema(ctx: Context, pdf_base64: str, schema: Dict[str, Any]) -> str:
    """
    Extracts specific fields from a document based on a provided JSON schema.
    It is recommended to validate the schema with 'ade_validate_json_schema' first.
    """
    try:
        # Quick validation before sending
        validation_result = await ade_validate_json_schema(ctx, schema)
        if "❌" in validation_result:
            return f"Schema validation failed. Please fix the schema before extraction.\n{validation_result}"

        config_obj = ParseConfig(extraction_schema=schema)
        with SuppressOutput():
            results = await asyncio.to_thread(parse, base64.b64decode(pdf_base64), config=config_obj)
        if not results: return "❌ No results returned."
        
        result = results[0]
        response = {
            "extraction_error": result.extraction_error,
            "extracted_data": result.extraction,
            "field_details": {
                field: {
                    "confidence": meta.confidence, "raw_text": meta.raw_text, "chunk_references": meta.chunk_references
                } for field, meta in result.extraction_metadata.items() if meta
            } if result.extraction_metadata else {}
        }
        return json.dumps(response, indent=2)
    except Exception as e:
        return f"Error during JSON schema extraction: {str(e)}"

if __name__ == "__main__":
    load_environment_variables()
    mcp.run(transport='stdio')