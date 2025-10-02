# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python-based startup idea research and analysis tool that uses Claude AI's multi-agent orchestration with built-in web search capabilities. The system employs three specialized agents that work in sequence to generate, critique, and summarize startup ideas.

## Environment Setup

- Python 3.11+ with virtual environment in `.venv`
- Required environment variable: `ANTHROPIC_API_KEY` (stored in `.env`)
- Dependencies: `anthropic`, `python-dotenv` (install with `pip install anthropic python-dotenv`)

## Running the Application

```bash
# Activate virtual environment
source .venv/bin/activate

# Run the main script
python scraper.py
```

The script will prompt for a topic or use the default "small team startup ideas".

## Architecture

### Multi-Agent System (scraper.py)

The `StartupIdeaOrchestrator` class coordinates three sequential agents:

1. **Research Agent** (`research_agent`): Generates 3-5 startup ideas using web search for market intelligence
2. **Devil's Advocate Agent** (`devils_advocate_agent`): Analyzes challenges and risks for each idea
3. **Summary Agent** (`summary_agent`): Synthesizes findings into a ranked report

### Key Components

- **Rate Limiting**: `_throttle_request()` enforces 3-second intervals between API calls
- **Error Handling**: `_make_api_request()` implements exponential backoff for rate limits (10s, 20s, 40s) with max 3 retries
- **Tool Processing**: `_process_with_tools()` manages Claude API interactions with built-in web search tool (max 3 uses per agent)

### Output

Results are saved to timestamped files:
- `results_{timestamp}.txt`: Final summary report
- `research_results_{timestamp}.txt`: Raw research output
- `critique_results_{timestamp}.txt`: Critical analysis output

## Configuration

- Default model: `claude-sonnet-4-20250514`
- Token limits: 5000 (research/critique), 7500 (summary)
- Rate limiting: 3 seconds between requests
- Web search: Max 3 uses per agent call