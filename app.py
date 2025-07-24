# app.py
import streamlit as st
import time
import logging
from urllib.parse import urljoin, urlparse
import re
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
import json

# --- Configuration ---
MAX_WAIT_TIME = 30  # Maximum time to wait for elements/redirects (seconds)
BASE_URL = "https://realgrouplinks.com"
MAX_PAGES_TO_SCRAPE = 5 # Limit pages to prevent very long runs
# --- End Configuration ---

# Configure logging (Streamlit shows logs in the app if needed)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Helper Functions (adapted for Streamlit) ---

@st.cache_resource # Cache the driver setup across sessions (if Streamlit allows, otherwise it will recreate)
def setup_driver(headless=True):
    """Sets up and returns a Selenium WebDriver instance."""
    chrome_options = Options()
    if headless:
        chrome_options.add_argument("--headless=new") # Use new headless mode
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    # Disable images for potentially faster loading
    prefs = {"profile.managed_default_content_settings.images": 2}
    chrome_options.add_experimental_option("prefs", prefs)

    driver = None
    try:
        # Try using webdriver-manager first (good practice)
        from webdriver_manager.chrome import ChromeDriverManager
        from selenium.webdriver.chrome.service import Service
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        logger.info("ChromeDriver setup successful using webdriver-manager.")
    except Exception as e:
        logger.warning(f"Error setting up ChromeDriver with webdriver-manager: {e}. Trying default path.")
        # Fallback: Assume chromedriver is in PATH (common on Streamlit Cloud)
        try:
            driver = webdriver.Chrome(options=chrome_options)
            logger.info("ChromeDriver setup successful using PATH.")
        except WebDriverException as e:
            logger.error(f"Fallback ChromeDriver setup also failed: {e}")
            st.error(f"Failed to initialize Chrome browser: {e}")
            raise e
    return driver

def get_final_whatsapp_url_selenium(driver, group_php_url):
    """Navigates to the group.php page and extracts the final WhatsApp URL."""
    logger.debug(f"Getting final URL for intermediate link: {group_php_url}")
    try:
        driver.get(group_php_url)

        # Method 1: Wait for the redirect to happen (common pattern)
        try:
            WebDriverWait(driver, MAX_WAIT_TIME).until(
                EC.url_contains("chat.whatsapp.com")
            )
            final_url = driver.current_url
            logger.info(f"Redirected to final URL: {final_url}")
            return final_url
        except TimeoutException:
            logger.debug(f"Timeout waiting for redirect on {group_php_url}")

        # Method 2: If redirect didn't happen, try to extract URL from JavaScript setTimeout
        # Example from provided files: setTimeout(function(){window.location.href = 'https://chat.whatsapp.com/...';}, 7000);
        try:
            script_elements = driver.find_elements(By.XPATH, "//script[contains(text(), 'window.location.href') and contains(text(), 'chat.whatsapp.com')]")
            for script_element in script_elements:
                script_text = script_element.get_attribute('innerHTML')
                # Look for the pattern: window.location.href = 'THE_URL';
                match = re.search(r"window\.location\.href\s*=\s*['\"](https?://chat\.whatsapp\.com/[^'\"]*)['\"]\s*;", script_text)
                if match:
                    final_url = match.group(1)
                    logger.info(f"Extracted URL from JS setTimeout: {final_url}")
                    return final_url
                else:
                     logger.debug(f"JS script element found but URL pattern not matched on {group_php_url}")
        except Exception as e: # Catch general exceptions during JS parsing
             logger.warning(f"Error while trying to parse JS for URL on {group_php_url}: {e}")

        # If both methods fail
        logger.warning(f"Failed to get final URL for {group_php_url} using standard methods.")
        return group_php_url # Return the intermediate URL itself if final cannot be found easily

    except Exception as e:
        logger.error(f"Error processing intermediate link {group_php_url}: {e}")
        return None # Indicate failure

def extract_links_from_page(driver, current_url):
    """Extracts direct and intermediate group links from the current page."""
    direct_links = set()
    intermediate_links = set()

    try:
        # Wait for some content to load (basic check)
        WebDriverWait(driver, MAX_WAIT_TIME).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )

        # --- 1. Find Direct WhatsApp Links ---
        direct_link_elements = driver.find_elements(By.XPATH, "//a[contains(@href, 'chat.whatsapp.com') and @href]")
        for element in direct_link_elements:
            href = element.get_attribute('href')
            if href:
                parsed_url = urlparse(href)
                if parsed_url.scheme and parsed_url.netloc and 'chat.whatsapp.com' in parsed_url.netloc:
                     direct_links.add(href)
        logger.info(f"Found {len(direct_link_elements)} potential direct link elements, validated {len(direct_links)} unique direct links on {current_url}.")

        # --- 2. Find Intermediate group.php Links (Modal Links) ---
        intermediate_link_elements = driver.find_elements(By.XPATH, "//a[@href='#groupsingle' and contains(@onclick, 'group.php?id=')]")
        for element in intermediate_link_elements:
            onclick_attr = element.get_attribute('onclick')
            if onclick_attr:
                # Extract URL from onclick, e.g., singlegroup('THE_URL',...
                match = re.search(r"singlegroup\(['\"]([^'\"]*group\.php\?id=\d+)['\"]", onclick_attr)
                if match:
                    relative_or_absolute_url = match.group(1)
                    full_url = urljoin(current_url, relative_or_absolute_url)
                    intermediate_links.add(full_url)
        logger.info(f"Found {len(intermediate_link_elements)} potential intermediate link elements, validated {len(intermediate_links)} unique intermediate links on {current_url}.")

    except TimeoutException:
        logger.error(f"Timeout waiting for page content to load on {current_url}")
        st.warning(f"Timeout occurred while loading {current_url}")
    except Exception as e:
        logger.error(f"Error extracting links from {current_url}: {e}")
        st.warning(f"An error occurred while extracting links from {current_url}: {e}")

    return list(direct_links), list(intermediate_links)

def get_pagination_links(driver, base_url):
    """Gets links for paginated pages."""
    pagination_links = set()
    try:
        pagination_elements = driver.find_elements(By.XPATH, "//div[contains(@class, 'pagination')]//a[@href]")
        for element in pagination_elements:
            href = element.get_attribute('href')
            text = element.text.strip()
            if href and href.startswith(base_url):
                 if text.isdigit() or re.search(r'/(\d+)/?$', href):
                    pagination_links.add(href)
        logger.info(f"Found {len(pagination_links)} potential pagination links.")
    except Exception as e:
        logger.error(f"Error extracting pagination links: {e}")
        st.warning("Could not find pagination links or an error occurred.")

    sorted_links = sorted(list(pagination_links))[:MAX_PAGES_TO_SCRAPE - 1]
    logger.info(f"Limited pagination links to scrape (max {MAX_PAGES_TO_SCRAPE} pages): {sorted_links}")
    return sorted_links

def scrape_homepage_and_pagination(driver, base_url, max_pages):
    """Main scraping logic for homepage and its pagination."""
    all_results = []
    status_placeholder = st.empty()
    progress_bar = st.progress(0)

    try:
        status_placeholder.info("Scraping homepage...")
        driver.get(base_url)
        direct_links_page1, intermediate_links_page1 = extract_links_from_page(driver, base_url)
        all_results.extend([{"Type": "Direct", "Source": base_url, "Link": link} for link in direct_links_page1])
        all_results.extend([{"Type": "Intermediate", "Source": base_url, "Link": link} for link in intermediate_links_page1])
        progress_bar.progress(1 / max_pages)

        if max_pages > 1:
            status_placeholder.info("Finding pagination links...")
            pagination_urls = get_pagination_links(driver, base_url)
            # Limit pagination URLs based on max_pages
            pagination_urls = pagination_urls[:max_pages - 1]

            total_pages = 1 + len(pagination_urls)
            for i, page_url in enumerate(pagination_urls):
                status_placeholder.info(f"Scraping page {i + 2}: {page_url}")
                try:
                    driver.get(page_url)
                    direct_links_page, intermediate_links_page = extract_links_from_page(driver, page_url)
                    all_results.extend([{"Type": "Direct", "Source": page_url, "Link": link} for link in direct_links_page])
                    all_results.extend([{"Type": "Intermediate", "Source": page_url, "Link": link} for link in intermediate_links_page])
                except Exception as e:
                    logger.error(f"Failed to scrape page {page_url}: {e}")
                    st.warning(f"Failed to scrape page {page_url}: {e}")
                progress_bar.progress((i + 2) / total_pages)
                time.sleep(0.5) # Small delay between page scrapes

        status_placeholder.success(f"Finished scraping homepage and {max_pages - 1} additional pages.")
        progress_bar.empty()
        logger.info(f"Finished scraping homepage and pagination. Total links found (direct + intermediate): {len(all_results)}")
        return all_results

    except Exception as e:
        logger.error(f"Critical error during homepage scraping: {e}")
        status_placeholder.error(f"Critical error during scraping: {e}")
        progress_bar.empty()
        return []

def process_intermediate_links(driver, intermediate_results):
    """Processes intermediate links to find final WhatsApp URLs."""
    if not intermediate_results:
        st.info("No intermediate links to process.")
        return []

    processed_results = []
    status_placeholder = st.empty()
    progress_bar = st.progress(0)
    total_intermediate = len(intermediate_results)

    status_placeholder.info(f"Processing {total_intermediate} intermediate links to find final URLs...")
    for i, result in enumerate(intermediate_results):
        intermediate_link = result['Link']
        status_placeholder.info(f"Processing {i+1}/{total_intermediate}: {intermediate_link}")
        final_url = get_final_whatsapp_url_selenium(driver, intermediate_link)
        if final_url and final_url != intermediate_link:
            processed_results.append({"Type": "Final (from Intermediate)", "Source": intermediate_link, "Link": final_url})
        else:
            processed_results.append({"Type": "Final (FAILED/Not Found)", "Source": intermediate_link, "Link": final_url or "ERROR"})
        progress_bar.progress((i + 1) / total_intermediate)
        # Optional: Small delay
        time.sleep(0.2)

    progress_bar.empty()
    status_placeholder.success("Finished processing intermediate links.")
    return processed_results

# --- Streamlit App ---

def main():
    st.set_page_config(page_title="RealGroupLinks Scraper", page_icon="🔗")
    st.title("🔗 RealGroupLinks.com Scraper")
    st.markdown("Scrape WhatsApp group links directly and via intermediate pages.")

    # Input Configuration
    st.sidebar.header("Configuration")
    base_url = st.sidebar.text_input("Base URL", value=BASE_URL, disabled=True) # Fixed for this scraper
    max_pages = st.sidebar.slider("Max Pages to Scrape", min_value=1, max_value=10, value=MAX_PAGES_TO_SCRAPE)
    resolve_intermediates = st.sidebar.checkbox("Resolve Intermediate Links", value=True)
    st.sidebar.markdown("---")
    st.sidebar.markdown("**Note:** Scraping involves loading web pages. It may take a minute or two.")

    # Start Scraping Button
    if st.button("Start Scraping"):
        driver = None
        all_scraped_data = []
        try:
            with st.spinner("Initializing browser..."):
                driver = setup_driver(headless=True)

            # 1. Scrape Homepage and Pagination
            raw_results = scrape_homepage_and_pagination(driver, base_url, max_pages)
            if not raw_results:
                 st.warning("No data was scraped from the homepage and pagination.")
                 return

            # Separate direct and intermediate results
            direct_results = [r for r in raw_results if r['Type'] == 'Direct']
            intermediate_results = [r for r in raw_results if r['Type'] == 'Intermediate']

            st.subheader("Initial Scraping Results")
            st.write(f"- Direct Links Found: {len(direct_results)}")
            st.write(f"- Intermediate Links Found: {len(intermediate_results)}")
            all_scraped_data.extend(direct_results) # Add direct links first

            # 2. Process Intermediate Links (if requested)
            if resolve_intermediates and intermediate_results:
                final_results = process_intermediate_links(driver, intermediate_results)
                all_scraped_data.extend(final_results)
            elif intermediate_results:
                 # If not resolving, add intermediate links as is
                 all_scraped_data.extend(intermediate_results)

        except Exception as e:
            logger.error(f"An unexpected error occurred in the main app logic: {e}")
            st.error(f"An unexpected error occurred: {e}")
        finally:
            if driver:
                try:
                    driver.quit()
                    logger.info("Browser closed successfully.")
                except Exception as e:
                    logger.warning(f"Error closing browser: {e}")

        # 3. Display and Download Results
        if all_scraped_data:
            df = pd.DataFrame(all_scraped_data)
            st.subheader("Scraped Data")
            st.dataframe(df)

            csv = df.to_csv(index=False)
            st.download_button(
                label="Download CSV",
                data=csv,
                file_name='realgrouplinks_scraped_data.csv',
                mime='text/csv',
            )

            st.success(f"Scraping completed! Total items: {len(all_scraped_data)}")
        else:
            st.info("No data was successfully scraped or processed.")

if __name__ == "__main__":
    main()
