Claude Orchestration Prompt (Final Draft)
You are an AI agent orchestrator. Your task is to build a multi-agent workflow in Python to gather realtor contact information for Saskatchewan. The workflow will involve three agents, each with a specific responsibility.
Overall Goal
Collect the following realtor details into a structured CSV format:
* name
* phone
* email
* website
Agents should save intermediate data, avoid unnecessary repeated requests, and progressively enrich missing fields across stages.

Agent 1 — Scraper Agent
Responsibility: Scrape realtor listings for Saskatchewan.
Entry Point:
* Start at: https://www.realtor.ca/realtor-search-results#province=7
* 
* The page will make background requests, such as: https://www.realtor.ca/Services/ControlFetcher.asmx/GetRealtorResults
* 
* Prefer to use batch APIs if available to minimize the number of requests.
Requirements:
* Save every raw response (HTML or JSON) in a scraper-found directory, using filenames like: scraper-found/page-{N}.{fileType}
*  Example: scraper-found/page-1.json
* Reuse saved responses in subsequent runs to avoid hitting rate limits.
* Extract fields from responses:
    * name: <span class="realtorCardName">
    * phone: <span class="TelephoneNumber">
    * website: <a class="realtorCardWebsite"> → href
    * email: if visible; otherwise leave blank (often hidden behind a button).
Output: CSV file scraper-output.csv with columns:
name,phone,email,website

Agent 2 — Website Enrichment Agent
Responsibility: For realtors in scraper-output.csv with missing emails, enrich by visiting their personal websites.
Details:
* Use a web scraper or search tool to fetch the realtor’s personal website.
* Look for email addresses on:
    * Homepage
    * Contact pages
    * Footer sections
    * Calls-to-action (CTA)
* If multiple emails are found:
    * Pick the one most unique and most likely tied to the realtor.
    * Place any additional addresses into a column extra_emails.
Output: CSV file personal-output.csv with columns:
name,phone,email,website,extra_emails

Agent 3 — Web Search Completion Agent
Responsibility: For rows in personal-output.csv with missing data, attempt completion via broader web search and scraping.
Details:
* Use realtor’s name and website/company in queries.
* Attempt to fill missing fields (especially email).
* Add a confidence score (0–1) for each piece of enriched data, reflecting how likely it is correct.
Output: CSV file final-output.csv with columns:
name,phone,email,website,extra_emails,confidence

General Rules
* Always prefer structured batch APIs when available over per-page scraping.
* Never hallucinate data — only output information directly observed from responses or search results.
* Respect rate limits by caching raw responses in scraper-found.
* Always output CSVs in valid, machine-readable format.
* Save each agent’s output before starting the next agent.