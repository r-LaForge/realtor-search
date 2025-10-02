"""
AI-BASED SCRAPER VERSION (BACKUP)
This file contains the original AI-based scraping approach using Claude with web search.
Note: This approach hits token output limits for large datasets (1700+ records).
Kept for reference or small-scale scraping tasks.
"""

import os
import time
import json
import csv
from typing import Dict, List
from pathlib import Path
from anthropic import Anthropic, RateLimitError
from dotenv import load_dotenv
import datetime

load_dotenv()


class RealtorScraperOrchestrator_AI:
    """
    AI-based multi-agent orchestrator using Claude with web search.
    WARNING: Limited to small batches due to model output token limits.
    """

    def __init__(self):
        self.client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.model = "claude-sonnet-4-20250514"
        self.last_request_time = 0
        self.min_request_interval = 3  # seconds

        # Create output directories
        Path("../scraper-found").mkdir(exist_ok=True)

    def _throttle_request(self):
        """Enforce rate limiting between API requests."""
        current_time = time.time()
        time_since_last_request = current_time - self.last_request_time
        if time_since_last_request < self.min_request_interval:
            time.sleep(self.min_request_interval - time_since_last_request)
        self.last_request_time = time.time()

    def _make_api_request(self, messages: List[Dict], max_tokens: int = 5000, tools: List[Dict] = None):
        """Make API request with exponential backoff for rate limits."""
        max_retries = 3
        base_delay = 10

        for attempt in range(max_retries):
            try:
                self._throttle_request()

                kwargs = {
                    "model": self.model,
                    "max_tokens": max_tokens,
                    "messages": messages
                }

                if tools:
                    kwargs["tools"] = tools

                response = self.client.messages.create(**kwargs)
                return response

            except RateLimitError:
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)
                    print(f"Rate limited. Waiting {delay} seconds before retry...")
                    time.sleep(delay)
                else:
                    raise

    def _process_with_tools(self, messages: List[Dict], max_tokens: int = 5000, max_tool_uses: int = 3):
        """Process messages with tool support, handling tool use loops."""
        tools = [{
            "type": "web_search_20250305"
        }]

        tool_use_count = 0

        while tool_use_count < max_tool_uses:
            response = self._make_api_request(messages, max_tokens, tools)

            # Check if we need to continue the tool loop
            has_tool_use = any(block.type == "tool_use" for block in response.content)

            if not has_tool_use:
                # No more tool uses, return final response
                return response

            # Build tool results for next iteration
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    tool_use_count += 1
                    # Tool results are automatically provided by Claude
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": "Search completed"
                    })

            # Add assistant response and tool results to conversation
            messages.append({
                "role": "assistant",
                "content": response.content
            })

            if tool_use_count >= max_tool_uses:
                # Force completion
                messages.append({
                    "role": "user",
                    "content": "Please provide your final answer based on the information gathered."
                })
                response = self._make_api_request(messages, max_tokens)
                return response

        return response

    def _extract_text_content(self, response) -> str:
        """Extract text content from Claude response."""
        text_parts = []
        for block in response.content:
            if hasattr(block, "text"):
                text_parts.append(block.text)
        return "\n".join(text_parts)

    def agent_1_scraper(self) -> str:
        """
        Agent 1: AI Scraper Agent (Web Search Based)
        WARNING: Limited by output token constraints.
        """
        print("\n=== Agent 1: AI Scraper Agent ===")
        print("Using AI with web search to scrape realtor listings...")

        prompt = """You are a web scraping agent tasked with gathering realtor contact information from Saskatchewan, Canada.

Your task:
1. Scrape realtor listings from https://www.realtor.ca/realtor-search-results#province=7
2. Extract up to 50 realtor records (limited by output constraints)
3. Look for batch API endpoints like https://www.realtor.ca/Services/ControlFetcher.asmx/GetRealtorResults
4. Extract the following fields for each realtor:
   - name: Look for elements like <span class="realtorCardName">
   - phone: Look for elements like <span class="TelephoneNumber">
   - website: Look for <a class="realtorCardWebsite"> and extract the href
   - email: Extract if visible, otherwise leave blank

5. Use web search to understand the site structure and API endpoints
6. Provide extracted data in CSV format with columns: name,phone,email,website

Important:
- Limit to 50 records due to output token constraints
- Only output data you directly observe - no hallucinations
- Format output as valid CSV

Begin your research and data extraction now."""

        messages = [{
            "role": "user",
            "content": prompt
        }]

        response = self._process_with_tools(messages, max_tokens=7500, max_tool_uses=5)
        result = self._extract_text_content(response)

        # Save raw result
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        with open(f"scraper-found/agent1_ai_raw_{timestamp}.txt", "w") as f:
            f.write(result)

        print(f"✓ AI Scraper agent completed. Raw output saved.")
        return result


def main():
    """Main entry point for AI-based scraper."""
    print("=" * 60)
    print("AI-BASED SCRAPER (LIMITED TO ~50 RECORDS)")
    print("=" * 60)
    orchestrator = RealtorScraperOrchestrator_AI()
    orchestrator.agent_1_scraper()


if __name__ == "__main__":
    main()