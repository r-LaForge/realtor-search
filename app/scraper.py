import os
import time
import json
import csv
from typing import Dict, List
from pathlib import Path
from anthropic import Anthropic, RateLimitError
from dotenv import load_dotenv
import datetime
from realtor_scraper import RealtorScraper
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

load_dotenv()


class RealtorScraperOrchestrator:
    """
    Multi-agent orchestrator for gathering realtor contact information from Saskatchewan.

    Architecture:
    - Agent 1: Selenium browser automation for realtor.ca (handles JavaScript)
    - Agent 2: powered website enrichment with batching
    - Agent 3: powered web search completion with batching
    """

    def __init__(self):
        self.client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.enrichment_model = "claude-sonnet-4-5-20250929"  # Fast & cheap for enrichment
        self.last_request_time = 0
        self.min_request_interval = 1  # can handle faster requests
        self.batch_size = 20  # Process 20 realtors per API call

        # Create output directories
        Path("scraper-found").mkdir(exist_ok=True)

    def _throttle_request(self):
        """Enforce rate limiting between API requests."""
        current_time = time.time()
        time_since_last_request = current_time - self.last_request_time
        if time_since_last_request < self.min_request_interval:
            time.sleep(self.min_request_interval - time_since_last_request)
        self.last_request_time = time.time()

    def _make_api_request(self, messages: List[Dict], max_tokens: int = 4000, tools: List[Dict] = None):
        """Make API request with exponential backoff for rate limits."""
        max_retries = 3
        base_delay = 10

        for attempt in range(max_retries):
            try:
                self._throttle_request()

                kwargs = {
                    "model": self.enrichment_model,
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

    def _process_with_tools(self, messages: List[Dict], max_tokens: int = 4000, max_tool_uses: int = 3):
        """Process messages with tool support, handling tool use loops."""
        tools = [{
            "type": "web_search_20250305",
            "name": "web_search"
        }]

        tool_use_count = 0

        while tool_use_count < max_tool_uses:
            response = self._make_api_request(messages, max_tokens, tools)

            # Check if we need to continue the tool loop
            has_tool_use = any(block.type == "tool_use" for block in response.content)

            if not has_tool_use:
                return response

            # Add assistant response to conversation
            messages.append({
                "role": "assistant",
                "content": response.content
            })

            # Count tool uses
            for block in response.content:
                if block.type == "tool_use":
                    tool_use_count += 1

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

    def agent_1_selenium_scraper(self) -> str:
        """
        Agent 1: Network Traffic Listener
        Launches browser, intercepts GetRealtorResults API responses, and parses the HTML.
        """
        scraper = RealtorScraper()
        output = scraper.scrape()
        return output

    def agent_2_enrichment(self, input_file: str) -> str:
        """
        Agent 2: Website Enrichment Agent (powered with batching)
        Processes realtors in batches to find missing emails on their websites.
        """
        print("\n=== Agent 2: Website Enrichment Agent ===")
        print("Enriching contact data from personal websites...")

        # Read input CSV
        with open(input_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            realtors = list(reader)

        # Filter realtors needing enrichment
        realtors_to_enrich = [
            r for r in realtors
            if not r.get("email", "").strip() and r.get("website", "").strip()
        ]

        print(f"Found {len(realtors_to_enrich)} realtors with missing emails but valid websites")

        if len(realtors_to_enrich) == 0:
            print("No enrichment needed, copying to personal-output.csv")
            output_file = "personal-output.csv"
            with open(output_file, "w", newline="", encoding="utf-8") as f:
                fieldnames = ["name", "phone", "email", "website", "extra_emails"]
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for r in realtors:
                    r["extra_emails"] = ""
                    writer.writerow(r)
            return output_file

        # Process in batches
        enriched_realtors = list(realtors)  # Start with all realtors
        total_batches = (len(realtors_to_enrich) + self.batch_size - 1) // self.batch_size

        for batch_idx in range(total_batches):
            start_idx = batch_idx * self.batch_size
            end_idx = min(start_idx + self.batch_size, len(realtors_to_enrich))
            batch = realtors_to_enrich[start_idx:end_idx]

            print(f"Processing batch {batch_idx + 1}/{total_batches} ({len(batch)} realtors)...")

            batch_json = json.dumps(batch, indent=2)

            prompt = f"""Find missing email addresses by visiting realtor websites.

Realtors to enrich:
{batch_json}

For each realtor with a website:
1. Use web search to access their website
2. Look for emails on: homepage, contact page, footer
3. Pick the most unique email (tied to the realtor)
4. Put additional emails in "extra_emails" (comma-separated)

Output CSV format: name,phone,email,website,extra_emails

Only output observed data - no hallucinations."""

            messages = [{"role": "user", "content": prompt}]

            try:
                response = self._process_with_tools(messages, max_tokens=4000, max_tool_uses=3)
                result = self._extract_text_content(response)

                # Save batch result
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                with open(f"scraper-found/agent2_batch_{batch_idx}_{timestamp}.txt", "w") as f:
                    f.write(result)

                print(f"✓ Batch {batch_idx + 1} completed")

            except Exception as e:
                print(f"Error processing batch {batch_idx + 1}: {str(e)}")

        # Write output
        output_file = "personal-output.csv"
        with open(output_file, "w", newline="", encoding="utf-8") as f:
            fieldnames = ["name", "phone", "email", "website", "extra_emails"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in enriched_realtors:
                if "extra_emails" not in r:
                    r["extra_emails"] = ""
                writer.writerow(r)

        print(f"✓ Enrichment completed. Output saved to {output_file}")
        return output_file

    def agent_3_completion(self, input_file: str) -> str:
        """
        Agent 3: Web Search Completion Agent (powered with batching)
        Uses broader web search to fill remaining gaps with confidence scores.
        """
        print("\n=== Agent 3: Web Search Completion Agent ===")
        print("Completing missing data via web search...")

        # Read input CSV
        with open(input_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            realtors = list(reader)

        # Filter realtors needing completion
        realtors_to_complete = [r for r in realtors if not r.get("email", "").strip()]

        print(f"Found {len(realtors_to_complete)} realtors with missing data")

        if len(realtors_to_complete) == 0:
            print("No completion needed, copying to final-output.csv")
            output_file = "final-output.csv"
            with open(output_file, "w", newline="", encoding="utf-8") as f:
                fieldnames = ["name", "phone", "email", "website", "extra_emails", "confidence"]
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for r in realtors:
                    r["confidence"] = "1.0"
                    writer.writerow(r)
            return output_file

        # Process in batches
        completed_realtors = list(realtors)
        total_batches = (len(realtors_to_complete) + self.batch_size - 1) // self.batch_size

        for batch_idx in range(total_batches):
            start_idx = batch_idx * self.batch_size
            end_idx = min(start_idx + self.batch_size, len(realtors_to_complete))
            batch = realtors_to_complete[start_idx:end_idx]

            print(f"Processing batch {batch_idx + 1}/{total_batches} ({len(batch)} realtors)...")

            batch_json = json.dumps(batch, indent=2)

            prompt = f"""Find missing contact info via web search.

Realtors with missing data:
{batch_json}

For each realtor:
1. Search: "[name] Saskatchewan realtor email"
2. Check directories, business listings, social media
3. Assign confidence (0.0-1.0):
   - 1.0: Official website/verified listing
   - 0.8: Professional directory
   - 0.6: Business listing
   - 0.4: Social media
   - 0.0: Not found

Output CSV: name,phone,email,website,extra_emails,confidence

Only output observed data."""

            messages = [{"role": "user", "content": prompt}]

            try:
                response = self._process_with_tools(messages, max_tokens=4000, max_tool_uses=3)
                result = self._extract_text_content(response)

                # Save batch result
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                with open(f"scraper-found/agent3_batch_{batch_idx}_{timestamp}.txt", "w") as f:
                    f.write(result)

                print(f"✓ Batch {batch_idx + 1} completed")

            except Exception as e:
                print(f"Error processing batch {batch_idx + 1}: {str(e)}")

        # Write output
        output_file = "final-output.csv"
        with open(output_file, "w", newline="", encoding="utf-8") as f:
            fieldnames = ["name", "phone", "email", "website", "extra_emails", "confidence"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in completed_realtors:
                if "confidence" not in r:
                    r["confidence"] = "1.0"
                writer.writerow(r)

        print(f"✓ Completion agent finished. Output saved to {output_file}")
        return output_file

    def run(self):
        """Execute the complete three-agent workflow."""
        print("=" * 60)
        print("REALTOR SCRAPER - Multi-Agent Workflow")
        print("=" * 60)
        print("Target: Saskatchewan realtors from realtor.ca")
        print("Agent 1: Selenium Browser Automation")
        print("Agent 2: powered Website Enrichment (batched)")
        print("Agent 3: powered Web Search Completion (batched)")
        print("=" * 60)

        start_time = time.time()

        try:
            # Agent 1: Selenium scraping
            scraper_output = self.agent_1_selenium_scraper()
            scraper_output = "scraper-output.csv"

            # # Agent 2: Website enrichment with
            # enrichment_output = self.agent_2_enrichment(scraper_output)
            #
            # # Agent 3: Web search completion with
            # final_output = self.agent_3_completion(enrichment_output)

            elapsed = time.time() - start_time

            print("\n" + "=" * 60)
            print("WORKFLOW COMPLETED")
            print("=" * 60)
            print(f"Total time: {elapsed:.1f} seconds")
            print(f"\nOutput files:")
            print(f"  1. {scraper_output} - Initial scraping results")
            print(f"  2. {enrichment_output} - Website enrichment results")
            print(f"  3. {final_output} - Final completed dataset")
            print(f"\nRaw outputs saved in: scraper-found/")
            print("=" * 60)

        except Exception as e:
            print(f"\n❌ Error during workflow: {str(e)}")
            raise


def main():
    """Main entry point."""
    orchestrator = RealtorScraperOrchestrator()
    orchestrator.run()


if __name__ == "__main__":
    main()
