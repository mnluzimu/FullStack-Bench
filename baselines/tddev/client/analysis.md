# TDDev (Test Driven Development) Project Overview

## Project Structure

The project is a Flask web application with the following structure:

```
D:\research\TDDev\client\
├───app.py - Main Flask application
├───bots.py - LLM integration wrapper
├───prompts.py - All prompt templates
├───data\ - Sample data files (images and JSONL)
└───templates\ - HTML templates (tool.html)
    └───tool.html - Main frontend interface
```

## Functionality

This is an AI-powered web development and testing platform that:

1. **Generates web applications** based on text prompts
2. **Creates test cases** for generated applications
3. **Validates applications** by running automated tests
4. **Uses AI agents** to perform end-to-end testing

The process works in three main steps:
1. Requirements generation (from text/image prompts)
2. Web application generation (from requirements)
3. Validation/Testing (automated browser-based testing)

## Models Supported

The project supports multiple LLM providers:

1. **OpenAI** - GPT-4.1 model
2. **Anthropic** - Claude-Sonnet-4-20250514 model
3. **Together AI** - Qwen/Qwen2.5-VL-72B-Instruct and Deepseek-ai/DeepSeek-V3.1
4. **OpenAI-like** - Custom API endpoints

## Test Agent Models

The test agents (validation agents) that run automated browser testing use a **fixed model**: **Claude-Sonnet-4-20250514** from Anthropic.

There are multiple places where test agents are configured:
1. **Global test agent**: Defined as a global `llm` variable using `ChatAnthropic(model="claude-sonnet-4-20250514")`
2. **Individual test agents**: Each parallel validation agent creates its own `ChatAnthropic(model="claude-sonnet-4-20250514")` instance
3. **Screenshot validation**: Uses `OpenAILLM` with Anthropic API settings and the same Claude model
4. The model for test agents is hardcoded and cannot be changed through the UI

## Configuration

### API Keys and Base URLs

The application loads API keys from environment variables:

- `OPENAI_API_KEY` - For OpenAI models
- `ANTHROPIC_API_KEY` - For Anthropic models (used by both main pipeline and test agents)
- `TOGETHER_API_KEY` - For Together AI models
- `OPENAI_LIKE_API_KEY` and `OPENAI_LIKE_API_BASE_URL` - For custom OpenAI-compatible endpoints

The base URLs are:
- **OpenAI**: None (uses default OpenAI endpoint)
- **Anthropic**: `https://api.anthropic.com/v1/`
- **Together**: `https://api.together.xyz/v1`

### Environment Configuration

The API keys are loaded from `D:\research\TDDev\bolt.diy\.env.local` file:

```python
ENV_PATH = Path(__file__).resolve().parents[1] / "bolt.diy" / ".env.local"
if ENV_PATH.exists():
    env_map = dotenv_values(ENV_PATH)
    for key_name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "TOGETHER_API_KEY"):
        value = env_map.get(key_name)
        if value and not os.getenv(key_name):
            os.environ[key_name] = value
```

### Test Agent Model Configuration

Since test agents use the Claude model exclusively, you **must have `ANTHROPIC_API_KEY` set** in your environment for the validation/testing functionality to work properly. The test agent model is hardcoded to use `claude-sonnet-4-20250514` and cannot be configured through the UI or API parameters.

## How to Use

1. **Start the server**:
   ```bash
   python app.py
   ```
   The application runs on `http://127.0.0.1:8000`

2. **Access the tool** in your browser at the above URL

3. **Select a model** from the dropdown (OpenAI, Claude, Qwen, or Deepseek)

4. **Enter a prompt** describing the web application you want to create

5. **Optionally upload an image** to guide the design

6. **Click "Generate"** to start the requirements generation process

7. **Use "Generate Directly (Legacy)"** for the older textgen v1 flow

## Key Features

- **Multi-model support**: Can use different LLMs for different parts of the pipeline
- **Visual testing**: Can compare screenshots to design mockups
- **Parallel validation**: Runs multiple test agents in parallel
- **Configuration controls**: Adjustable parallel count, round limits, and max wait time
- **Real-time status**: Shows testing progress with visual indicators
- **Caching**: Caches prompts and requirements to speed up iteration
- **Image support**: Handles visual input for design requirements

## Technical Implementation

- Uses Flask for web interface
- Uses OpenAI Python client for LLM calls
- Uses browser-use library for automated browser testing
- Uses Playwright for screenshot capture
- Uses PM2 for managing multiple web application instances during testing
- Uses asyncio for concurrent agent execution

The project is designed to create a test-driven development pipeline where AI generates web applications and then automatically tests them using browser automation.