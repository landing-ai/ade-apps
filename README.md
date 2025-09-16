# MCP ADE Server

A Model Context Protocol (MCP) server that provides document extraction capabilities using LandingAI's Agentic Document Extraction (ADE) API. This server allows ADE to extract structured data from PDFs and images using various extraction methods.

## Features

- **Raw chunk extraction**: Extract all text chunks with metadata from documents
- **File path extraction**: Process local PDF/image files directly
- **Pydantic model extraction**: Extract structured data using custom Pydantic models
- **JSON schema extraction**: Extract data based on JSON schema definitions
- **Schema validation**: Validate JSON schemas against ADE requirements

## Prerequisites

- Python 3.11 or higher
- LandingAI's API key
- uv (Python package manager) - [Install uv](https://github.com/astral-sh/uv)

## Quick Start

### 1. Clone the Repository

```bash
git clone <your-github-repo-url>
cd mcp-ade-server
```

### 2. Set Up Environment

Create a `.env` file in the project root:

```bash
VISION_AGENT_API_KEY=your_LandingAI_api_key_here
```

### 3. Install Dependencies

```bash
# Install uv if you haven't already
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create virtual environment and install dependencies
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uv pip install -e .
```

### 4. Configure Claude Desktop

Add the server to your Claude Desktop configuration:

**On macOS**: Edit `~/Library/Application Support/Claude/claude_desktop_config.json`
**On Windows**: Edit `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "ade-server": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/mcp-ade-server",
        "run",
        "mcp-ade-server"
      ],
      "env": {
        "VISION_AGENT_API_KEY": "your_LandingAI_api_key_here"
      }
    }
  }
}
```

Replace `/path/to/mcp-ade-server` with the actual path to your cloned repository.

### 5. Restart Claude Desktop

After saving the configuration, restart Claude Desktop to load the MCP server.

## Usage Examples

Once configured, you can use these tools in Claude:

### Extract Raw Chunks
```
Use ade_extract_raw_chunks with a base64-encoded PDF to extract all text chunks
```

### Extract from Local File
```
Use ade_extract_from_path with path "/path/to/document.pdf"
```

### Extract with Pydantic Model
```python
# Define your model
class Invoice(BaseModel):
    invoice_number: str
    total_amount: float
    date: str

# Use ade_extract_with_pydantic with the model code and PDF or image files.
```

### Validate JSON Schema
```json
# Example schema to validate
{
  "type": "object",
  "properties": {
    "invoice": {
      "type": "object",
      "properties": {
        "number": {"type": "string"},
        "items": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "description": {"type": "string"},
              "amount": {"type": "number"}
            }
          }
        }
      }
    }
  }
}

# Use ade_validate_json_schema with the schema above
# Returns: ✅ Schema is valid according to ADE documentation rules.

# Example of invalid schema
{
  "type": "object",
  "allOf": [{"properties": {"name": {"type": "string"}}}]
}

# Returns: ❌ Schema validation failed:
# - Rule Broken: Prohibited keyword 'allOf' found at path 'root.allOf'.
```

### Extract with JSON Schema
```json
{
  "type": "object",
  "properties": {
    "invoice_number": {"type": "string"},
    "total": {"type": "number"}
  }
}
```

## Code Structure Breakdown

### 1. **Imports and Setup**
```python
# Standard imports for typing, async operations, and environment
from typing import Any, AsyncIterator, Optional, Dict, List, Union
from mcp.server.fastmcp import FastMCP, Context
# ... other imports

# Critical: Suppress stdout from agentic-doc to prevent config output
# This prevents unwanted output from interfering with MCP communication
```

### 2. **Output Suppression Helper**
```python
class SuppressOutput:
    """Context manager to suppress stdout/stderr from agentic-doc library"""
    # Temporarily redirects output to /dev/null
    # Prevents library output from breaking MCP protocol
```

### 3. **Response Formatting Helper**
```python
def _format_raw_response(result: ParsedDocument) -> Dict[str, Any]:
    """Formats extraction results into structured JSON response"""
    # Converts ParsedDocument to dictionary with:
    # - markdown: Full extracted text
    # - chunks: List of text chunks with metadata (type, content, page, bounding box)
```

### 4. **Environment Setup**
```python
def load_environment_variables() -> None:
    """Loads API key from .env file"""
    # Checks for required VISION_AGENT_API_KEY
    # Raises error if missing
```

### 5. **MCP Server Initialization**
```python
# Sets up FastMCP server with lifecycle management
mcp = FastMCP("ade-server", lifespan=app_lifespan)
```

### 6. **Tool: Raw Chunk Extraction**
```python
@mcp.tool()
async def ade_extract_raw_chunks(ctx: Context, pdf_base64: str) -> str:
    """Basic extraction of all text chunks from document"""
    # Input: Base64-encoded PDF
    # Output: JSON with markdown and chunk details
    # Use case: When you need all document content without structure
```

### 7. **Tool: File Path Extraction**
```python
@mcp.tool()
async def ade_extract_from_path(ctx: Context, path: str) -> str:
    """Extract chunks from local file"""
    # Input: File system path to PDF/image
    # Output: Same as raw chunks but from local file
    # Use case: Processing local documents without encoding
```

### 8. **Tool: Pydantic Model Extraction**
```python
@mcp.tool()
async def ade_extract_with_pydantic(ctx: Context, pdf_base64: str, pydantic_model_code: str) -> str:
    """Extract structured data using Pydantic model"""
    # Input: PDF + Python code defining Pydantic model
    # Process: Executes model code, uses for extraction
    # Output: Structured data matching model + confidence scores
    # Use case: Type-safe extraction with validation
```

### 9. **Tool: JSON Schema Validation**
```python
@mcp.tool()
async def ade_validate_json_schema(ctx: Context, schema: Dict[str, Any]) -> str:
    """Validate JSON schema against ADE rules"""
    # Checks for:
    # - Top-level must be object
    # - No prohibited keywords (allOf, not, if/then/else)
    # - Max depth of 5
    # - Required fields for objects/arrays
    # Use case: Pre-validate schemas before extraction
```

### 10. **Tool: JSON Schema Extraction**
```python
@mcp.tool()
async def ade_extract_with_json_schema(ctx: Context, pdf_base64: str, schema: Dict[str, Any]) -> str:
    """Extract data based on JSON schema"""
    # Input: PDF + JSON schema defining structure
    # Process: Validates schema, then extracts matching data
    # Output: JSON data conforming to schema
    # Use case: Flexible extraction without Python models
```

### 11. **Main Entry Point**
```python
if __name__ == "__main__":
    load_environment_variables()  # Load API key
    mcp.run(transport='stdio')    # Start MCP server on stdio
```

## Troubleshooting

### Common Issues

1. **"Missing required environment variable: VISION_AGENT_API_KEY"**
   - Ensure `.env` file exists with your API key
   - Check the key is valid and has Vision Agent access

2. **Server not appearing in Claude**
   - Verify the path in `claude_desktop_config.json` is correct
   - Restart Claude Desktop after config changes
   - Check Claude's MCP server logs for errors

3. **Extraction errors**
   - Ensure PDFs are properly base64-encoded
   - Check file paths are absolute, not relative
   - Validate JSON schemas before use

4. **MCP server not attaching to Claude**
   - Check the directory of uv using `which uv`
   - Ensure in the Claude config file the uv command path matches the output from `which uv`

5. **MCP server not starting**
   - Ensure both `agentic-doc` and `mcp` packages are installed
   - `agentic-doc` is required for LandingAI's ADE functionality
   - `mcp` is required for the MCP server framework

## License

[Add your license here]

## Contributing

[Add contribution guidelines if needed]