import datetime
import json
import time
import csv
import string

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup


class RealtorScraper:
    def scrape(self):
        """
        Agent 1: Network Traffic Listener
        Launches browser, intercepts GetRealtorResults API responses, and parses the HTML.
        """
        num_realtors = 0

        print("\n=== Agent 1: Network Traffic Listener ===")
        print("Launching browser to intercept API responses...")

        output_file = "scraper-output-all.csv"
        realtors = []
        driver = None

        alphabet = string.ascii_lowercase
        try:
            for letter in alphabet:

                driver = self._setup_driver()

                # Enable network monitoring (no interception - just monitoring)
                driver.execute_cdp_cmd('Network.enable', {})

                # Navigate to Saskatchewan realtor search
                url = f"https://www.realtor.ca/realtor-search-results#firstname={letter}&province=7"
                print(f"Navigating to {url}")

                driver.get(url)

                new_realtors = self._scrape_page(driver)
                while len(new_realtors) > 0:
                    realtors += new_realtors
                    self._click_next(driver)
                    new_realtors = self._scrape_page(driver)

                # Remove duplicates (based on name)
                seen_names = set()
                unique_realtors = []
                for r in realtors:
                    if r['name'] and r['name'] not in seen_names:
                        seen_names.add(r['name'])
                        unique_realtors.append(r)

                realtors = unique_realtors
                num_realtors += len(unique_realtors)
                print(f"\n✓ Extracted {len(realtors)} unique realtor records from API responses")

                if driver:
                    driver.close()
                    print("✓ Browser closed")

        except Exception as e:
            print(f"Error during scraping: {str(e)}")
            import traceback
            traceback.print_exc()
            # Create empty CSV on error
            with open(output_file, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=["name", "phone", "email", "website"])
                writer.writeheader()

        finally:
            if driver:
                driver.quit()
                print("✓ Browser closed")

        # Save to CSV
        with open(output_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["name", "phone", "email", "website"])
            writer.writeheader()
            writer.writerows(realtors)

        if len(realtors) == 0:
            print("\n⚠ WARNING: No realtors extracted!")
            print("Check the saved JSON files in scraper-found/ to debug")

        print(f"✓ Scraper completed. Output saved to {output_file}")

        return output_file

    def _scrape_page(self, driver):
        # Wait for page to fully load
        print("Waiting for page to load...")
        time.sleep(2)

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        captured_count = 0

        realtors = []

        # Function to capture and process GetRealtorResults responses
        def capture_api_responses():
            nonlocal captured_count
            found_any = False
            logs = driver.get_log('performance')

            for entry in logs:
                try:
                    log_message = json.loads(entry.get('message', '{}')).get('message', {})

                    # Look for response received events
                    if log_message.get('method') == 'Network.responseReceived':
                        response = log_message.get('params', {}).get('response', {})
                        response_url = response.get('url', '')
                        request_id = log_message.get('params', {}).get('requestId')

                        if "GetRealtorResults" in response_url:
                            try:
                                print(f"✓ Found GetRealtorResults response!")
                                # Get response body
                                body = driver.execute_cdp_cmd('Network.getResponseBody', {'requestId': request_id})
                                response_text = body.get('body', '')

                                # Save raw response
                                captured_count += 1
                                filename = f"scraper-found/api_response_{captured_count}_{timestamp}.json"
                                with open(filename, "w", encoding="utf-8") as f:
                                    f.write(response_text)

                                print(f"  Saved to: {filename}")

                                # Parse JSON response
                                data = json.loads(response_text)

                                # Extract realtors from the HTML in the response
                                page_realtors = self._extract_realtors_from_json(data)

                                if page_realtors:
                                    realtors.extend(page_realtors)
                                    print(f"  Extracted {len(page_realtors)} realtors")
                                    found_any = True

                            except Exception as e:
                                print(f"  Warning: Could not process response: {str(e)}")

                except Exception:
                    continue

            return found_any

        # Scroll to trigger more API calls
        print("\nScrolling to load more results...")
        last_count = len(realtors)
        no_change_count = 0

        for scroll_attempt in range(20):  # Try up to 20 scrolls
            # Scroll down
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)

            # Capture any new API responses
            capture_api_responses()

            # Check if we got new realtors
            if len(realtors) > last_count:
                print(
                    f"Scroll {scroll_attempt + 1}: Found {len(realtors) - last_count} new realtors (total: {len(realtors)})")
                last_count = len(realtors)
                no_change_count = 0
            else:
                no_change_count += 1
                print(f"Scroll {scroll_attempt + 1}: No new realtors")

            # If no new realtors after 3 scrolls, we're done
            if no_change_count >= 3:
                print("No new data after 3 scrolls - stopping")
                break

        return realtors

    def _extract_realtors_from_json(self, data, realtors=None):
        """
        Extract realtor data from JSON response.
        The API returns HTML inside a JSON field (usually 'd' field).
        We need to parse that HTML to extract realtor info.

        Expected structure: {'d': '<span id="RealtorResults">...</span>'}
        """
        if realtors is None:
            realtors = []

        # Check if this is the expected structure: {'d': '<html>...</html>'}
        if isinstance(data, dict):
            # Look for HTML content in common fields
            html_content = None
            for key in ['d', 'html', 'content', 'result', 'data']:
                if key in data and isinstance(data[key], str):
                    # Check if it looks like HTML
                    if '<' in data[key] and '>' in data[key]:
                        html_content = data[key]
                        break

            if html_content:
                # Parse the HTML
                soup = BeautifulSoup(html_content, 'html.parser')

                # Find all realtor cards
                # Look for elements with class containing "realtor" or "card"
                cards = soup.find_all(class_=lambda x: x and ('realtor' in x.lower() or 'card' in x.lower()))

                # If no cards found with class, try other approaches
                if not cards:
                    # Try finding by structure - look for name elements
                    name_elements = soup.find_all('span', class_='realtorCardName')
                    # Group by parent container
                    for name_elem in name_elements:
                        card = name_elem.find_parent(['div', 'article', 'li', 'section'])
                        if card and card not in cards:
                            cards.append(card)

                print(f"  Found {len(cards)} realtor cards in HTML response")

                # Extract data from each card
                for card in cards:
                    realtor = {
                        "name": "",
                        "phone": "",
                        "email": "",
                        "website": ""
                    }

                    # Extract name from <span class="realtorCardName">
                    name_elem = card.find('span', class_='realtorCardName')
                    if name_elem:
                        realtor['name'] = name_elem.get_text(strip=True)

                    # Extract phone from <span class="TelephoneNumber">
                    phone_elem = card.find('span', class_='TelephoneNumber')
                    if phone_elem:
                        realtor['phone'] = phone_elem.get_text(strip=True)
                    else:
                        # Fallback: try finding by tel: link
                        tel_link = card.find('a', href=lambda x: x and x.startswith('tel:'))
                        if tel_link:
                            realtor['phone'] = tel_link.get('href', '').replace('tel:', '').strip()

                    # Extract website from <a class="realtorCardWebsite">
                    website_elem = card.find('a', class_='realtorCardWebsite')
                    if website_elem:
                        realtor['website'] = website_elem.get('href', '').strip()

                    # Extract email (if visible - often hidden behind a button)
                    email_link = card.find('a', href=lambda x: x and x.startswith('mailto:'))
                    if email_link:
                        realtor['email'] = email_link.get('href', '').replace('mailto:', '').strip()

                    # Only add if we got at least a name
                    if realtor['name']:
                        realtors.append(realtor)

        return realtors

    def _click_next(self, driver):
        # Capture initial API calls (page 1 should have loaded by now)
        print("Trying to trigger pagination...")

        # Try clicking "next page" or pagination buttons
        try:
            # Look for pagination buttons
            next_button = driver.find_element(By.CSS_SELECTOR,
                                              "a[aria-label*='next'], button[aria-label*='next'], .pagination a:last-child")
            if next_button:
                print("Clicking next page button...")
                next_button.click()
                time.sleep(2)
        except Exception:
            print("No pagination button found")

    def _setup_driver(self):
        """Set up Selenium WebDriver with Chrome (stealth mode)."""
        chrome_options = Options()

        # Run in headless mode (optional - comment out to see browser)
        # chrome_options.add_argument("--headless=new")  # DISABLED for debugging

        # Basic anti-detection
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")

        # Realistic user agent
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

        # Additional stealth options
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-infobars")
        chrome_options.add_argument("--start-maximized")
        chrome_options.add_argument("--disable-notifications")
        chrome_options.add_argument("--disable-popup-blocking")

        # Disable automation flags
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)

        # Enable performance logging to capture network traffic
        chrome_options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})

        # Set preferences to appear more human
        prefs = {
            "profile.default_content_setting_values.notifications": 2,
            "credentials_enable_service": False,
            "profile.password_manager_enabled": False,
            "profile.default_content_setting_values.images": 1,  # Load images
            "profile.managed_default_content_settings.images": 1
        }
        chrome_options.add_experimental_option("prefs", prefs)

        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)

        # Execute CDP commands to hide webdriver property and more
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                // Hide webdriver
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });

                // Fix plugins length
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [
                        {name: 'Chrome PDF Plugin'},
                        {name: 'Chrome PDF Viewer'},
                        {name: 'Native Client'}
                    ]
                });

                // Fix languages
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en']
                });

                // Add chrome runtime
                window.chrome = {
                    runtime: {},
                    loadTimes: function() {},
                    csi: function() {},
                    app: {}
                };

                // Override permissions
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );

                // Randomize screen properties to look more natural
                Object.defineProperty(screen, 'availWidth', {
                    get: () => window.screen.width
                });
                Object.defineProperty(screen, 'availHeight', {
                    get: () => window.screen.height - 40
                });

                // Mock automation-related properties
                delete navigator.__proto__.webdriver;

                // Override toString to hide proxy
                const originalToString = Function.prototype.toString;
                Function.prototype.toString = function() {
                    if (this === window.navigator.permissions.query) {
                        return 'function query() { [native code] }';
                    }
                    return originalToString.call(this);
                };
            """
        })

        # Set realistic window size
        driver.set_window_size(1920, 1080)

        # Add random mouse movements to appear more human
        driver.execute_script("""
            window.humanMovement = setInterval(() => {
                const event = new MouseEvent('mousemove', {
                    clientX: Math.random() * window.innerWidth,
                    clientY: Math.random() * window.innerHeight
                });
                document.dispatchEvent(event);
            }, 2000);
        """)

        return driver
