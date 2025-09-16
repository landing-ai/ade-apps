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
git clone https://github.com/landing-ai/ade-apps/tree/main/mcp_ade_server
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

## Implementation Details

The source code is thoroughly documented with comprehensive comments explaining:
- Each tool's purpose and use cases
- Input/output formats with examples
- Error handling and validation logic
- Best practices and common issues

Please refer to `mcp_ade_server.py` for detailed implementation documentation.

## Troubleshooting

### Common Issues

1. **"Missing required environment variable: VISION_AGENT_API_KEY"**
   - Ensure `.env` file exists with your API key
   - Check the key is valid
   
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
