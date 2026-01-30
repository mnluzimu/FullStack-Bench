import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import (
    ReadFileTool, 
    ListDirectoryTool, 
    GlobTool,
    GrepTool,
    ReadManyFilesTool,
    BackendTestTool,
)
from agent_utils import llm_generation


def get_backend_compression_prompt() -> str:
    return """You are a technical log compressor. Your task is to process the output from a backend testing tool by performing a lossy compression that **strictly preserves factual data** while removing redundant noise.

**Your directive is to TRANSFORM the text, not SUMMARIZE it.**

### **CRITICAL RULES:**
1.  **Preserve:** All error codes, status messages, unique identifiers, file paths, URLs, key css styles, and any non-repetitive text.
2.  **Remove:** repetitive errors or warnings, and large blocks of minified code.
3.  **Condense:** Replace long, repetitive internal state objects (e.g., `self.__next_f.push([1, ...]`) with a clear placeholder like `<!-- [NEXT INTERNAL STATE...] -->` or `[Turbopack dev scripts truncated]`.
4.  **Do NOT** add external analysis, "Actionable" items, or guesses. Only reflect the content that is present in the output.
5.  The final output should be a shortened, yet still technical, version of the original text.

**Now, compress the following output:**

{output_text}"""


def compress_backend_output(output: str, model: str) -> str:
    prompt = get_backend_compression_prompt().format(output_text=output)
    messages = [{"role": "system", "content": "You are an expert at compressing text."}, {"role": "user", "content": prompt}]
    response = llm_generation(messages, model=model)
    compressed_output = response.get("content", "")

    return compressed_output.strip()


def compress_output(output: str, model: str, tool_name: str) -> str:
    if tool_name == BackendTestTool.Name and len(output) > 10000:
            return compress_backend_output(output, model)
    return output

