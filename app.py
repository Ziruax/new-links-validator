# app.py
import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
import time
import logging
from urllib.parse import urljoin, urlparse, quote_plus
import pandas as pd
import io

# --- Configuration ---
REALGROUP_BASE_URL = "https://realgrouplinks.com"
REALGROUP_HOMEPAGE_AJAX = "/more-groups.php"
REALGROUP_CATEGORY_AJAX = "/load-more-cat.php"
GROUPSOR_BASE_URL = "https://groupsor.link"
GROUPSOR_SEARCH_AJAX = "/group/findmore"
GROUPSOR_SEARCH_PAGE = "/group/search"
TIMEOUT = 20  # Increased timeout
MAX_RETRIES = 2
RETRY_DELAY = 3 # seconds, increased delay
DEFAULT_DELAY = 1 # second, delay between requests

# --- Logging ---
# Set level to WARNING to reduce Streamlit log output, or use DEBUG for development
logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Session State Initialization ---
if 'scraping_state' not in st.session_state:
    st.session_state.scraping_state = 'idle' # 'idle', 'running', 'paused', 'stopped'
if 'scraped_data' not in st.session_state:
    st.session_state.scraped_data = []
if 'scraping_progress' not in st.session_state: # For progress bar
    st.session_state.scraping_progress = 0
if 'scraping_message' not in st.session_state:
    st.session_state.scraping_message = "Ready to start."
if 'current_task' not in st.session_state:
    st.session_state.current_task = ""
if 'session_object' not in st.session_state: # Persistent requests session
    st.session_state.session_object = None

# --- Helper Functions ---

def create_robust_session():
    """Creates a requests session with common headers to mimic a browser."""
    session = requests.Session()
    # More comprehensive headers
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Referer': '', # Will be set dynamically
        'DNT': '1', # Do Not Track
        # 'Upgrade-Insecure-Requests': '1', # Sometimes helpful
    })
    return session

def safe_request(session, method, url, **kwargs):
    """Makes a request with retries and delays, handling common errors."""
    logger.debug(f"Making {method} request to {url}")
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = session.request(method, url, timeout=TIMEOUT, **kwargs)
            response.raise_for_status()
            # Optional: Check for Cloudflare or other blocking pages
            # if "checking your browser" in response.text.lower() or response.status_code == 403:
            #     logger.warning(f"Possible blocking page detected for {url}")
            #     # Could trigger a longer delay or stop
            return response
        except requests.exceptions.HTTPError as e:
            if response is not None and response.status_code == 403:
                logger.error(f"403 Forbidden for {url} on attempt {attempt + 1}. Check headers/cookies or site protection.")
                st.session_state.scraping_message = f"⚠️ 403 Forbidden for {url}. Retrying ({attempt + 1}/{MAX_RETRIES + 1})..."
                st.rerun() # Update UI message
            elif response is not None and response.status_code == 429:
                 logger.warning(f"429 Too Many Requests for {url} on attempt {attempt + 1}.")
                 st.session_state.scraping_message = f"⏳ 429 Rate Limited for {url}. Waiting longer..."
                 time.sleep(RETRY_DELAY * 2)
            else:
                error_msg = str(e) if response is None else f"HTTP {response.status_code}: {e}"
                logger.error(f"HTTP Error for {url} on attempt {attempt + 1}: {error_msg}")
                st.session_state.scraping_message = f"⚠️ HTTP Error for {url}. Retrying ({attempt + 1}/{MAX_RETRIES + 1})..."
                st.rerun()
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed for {url} on attempt {attempt + 1}: {e}")
            st.session_state.scraping_message = f"⚠️ Request Error for {url}. Retrying ({attempt + 1}/{MAX_RETRIES + 1})..."
            st.rerun()

        if attempt < MAX_RETRIES:
            time.sleep(RETRY_DELAY)
        else:
            logger.error(f"Failed to fetch {url} after {MAX_RETRIES + 1} attempts.")
            st.session_state.scraping_message = f"❌ Failed to fetch {url} after retries."
            st.rerun()
    return None # Should not be reached if retries exhausted


def get_final_whatsapp_url_rgl(group_url):
    """Fetches the RGL intermediate page and extracts the final WhatsApp URL."""
    if not st.session_state.session_object:
        st.session_state.session_object = create_robust_session()
    session = st.session_state.session_object

    logger.info(f"Fetching RGL intermediate page: {group_url}")
    st.session_state.current_task = f"Resolving RGL link: ...{group_url[-30:]}"
    st.rerun() # Update UI

    response = safe_request(session, 'GET', group_url)
    if not response:
        return None

    try:
        soup = BeautifulSoup(response.content, 'html.parser')
        scripts = soup.find_all('script')
        for script in scripts:
            if script.string:
                # Match setTimeout(function(){window.location.href = 'URL';}, 7000);
                # Make regex flexible for spacing, quotes, and time value
                match = re.search(r"setTimeout\s*\(\s*function\s*\(\s*\)\s*{\s*window\.location\.href\s*=\s*['\"](https?://chat\.whatsapp\.com/[^'\"]*)['\"]\s*;?\s*}\s*,\s*\d+\s*\)", script.string, re.DOTALL)
                if match:
                    final_url = match.group(1)
                    logger.info(f"Found final URL in JS: {final_url}")
                    return final_url
        logger.warning(f"Final URL not found in JS on {group_url}")
        return group_url # Return intermediate link if not found
    except Exception as e:
        logger.error(f"Error parsing RGL page {group_url}: {e}")
        return None

def get_final_whatsapp_url_gs(join_url):
    """Fetches the GroupSor join page and extracts the final WhatsApp URL."""
    if not st.session_state.session_object:
        st.session_state.session_object = create_robust_session()
    session = st.session_state.session_object

    logger.info(f"Fetching GroupSor join page: {join_url}")
    st.session_state.current_task = f"Resolving GroupSor link: ...{join_url[-30:]}"
    st.rerun()

    response = safe_request(session, 'GET', join_url)
    if not response:
        return None

    try:
        soup = BeautifulSoup(response.content, 'html.parser')

        # 1. Direct link
        whatsapp_links = soup.find_all('a', href=re.compile(r'chat\.whatsapp\.com'))
        for link_tag in whatsapp_links:
            href = link_tag.get('href')
            if href and 'chat.whatsapp.com' in href:
                logger.info(f"Found final URL (direct link): {href}")
                return href

        # 2. JS patterns (window.location.href, window.open)
        scripts = soup.find_all('script')
        for script in scripts:
            if script.string:
                # window.location.href = 'URL';
                loc_match = re.search(r"window\.location\.href\s*=\s*['\"](https?://chat\.whatsapp\.com/[^'\"]*)['\"]", script.string, re.IGNORECASE)
                if loc_match:
                    final_url = loc_match.group(1)
                    logger.info(f"Found final URL in JS (window.location): {final_url}")
                    return final_url
                # window.open('URL');
                open_match = re.search(r"window\.open\(['\"](https?://chat\.whatsapp\.com/[^'\"]*)['\"]", script.string, re.IGNORECASE)
                if open_match:
                    final_url = open_match.group(1)
                    logger.info(f"Found final URL in JS (window.open): {final_url}")
                    return final_url

        logger.warning(f"Final URL not found on GroupSor join page {join_url}")
        return None
    except Exception as e:
        logger.error(f"Error parsing GroupSor join page {join_url}: {e}")
        return None

def extract_rgl_links(html_content, base_url):
    """Extracts direct and intermediate group links from RGL HTML."""
    direct_links = set()
    intermediate_links = set()
    soup = BeautifulSoup(html_content, 'html.parser')

    direct_link_tags = soup.find_all('a', href=re.compile(r'chat\.whatsapp\.com'))
    for tag in direct_link_tags:
        href = tag.get('href')
        if href:
            parsed_url = urlparse(href)
            if parsed_url.scheme and parsed_url.netloc and 'chat.whatsapp.com' in parsed_url.netloc:
                direct_links.add(href)

    # Example from Pasted_Text_1753384326305.txt:
    # onclick="singlegroup('https://realgrouplinks.com/group.php?id=775166',...
    potential_intermediates = soup.find_all('a', onclick=re.compile(r'group\.php\?id='))
    for tag in potential_intermediates:
        onclick_attr = tag.get('onclick')
        if onclick_attr:
            # Extract URL from onclick, e.g., singlegroup('THE_URL',...
            match = re.search(r"singlegroup\(\s*['\"]([^'\"]*group\.php\?id=\d+)['\"]", onclick_attr)
            if match:
                relative_or_absolute_url = match.group(1)
                full_url = urljoin(base_url, relative_or_absolute_url)
                intermediate_links.add(full_url)

    logger.debug(f"RGL Extracted {len(direct_links)} direct, {len(intermediate_links)} intermediate links.")
    return list(direct_links), list(intermediate_links)

def scrape_rgl_homepage():
    """Scrapes the RGL homepage and its AJAX-loaded content (with pause/resume/stop)."""
    if not st.session_state.session_object:
        st.session_state.session_object = create_robust_session()
    session = st.session_state.session_object
    base_url = REALGROUP_BASE_URL
    all_results = []

    try:
        st.session_state.current_task = "Fetching RGL Homepage..."
        st.rerun()
        response = safe_request(session, 'GET', base_url)
        if not response:
            st.session_state.scraping_message = "Failed to fetch RGL homepage."
            return []
        initial_html = response.text
        direct_links, intermediate_links = extract_rgl_links(initial_html, base_url)
        all_results.extend([{"Type": "Direct (Homepage)", "Source": base_url, "Link": link} for link in direct_links])
        all_results.extend([{"Type": "Intermediate (Homepage)", "Source": base_url, "Link": link} for link in intermediate_links])
        st.session_state.scraping_message = f"Homepage: {len(direct_links) + len(intermediate_links)} initial links."
        st.rerun()
        time.sleep(DEFAULT_DELAY)

        # Based on JS in Pasted_Text_1753384326305.txt, homepage AJAX starts at 16, increments by 8
        page_counter = 16
        while st.session_state.scraping_state == 'running':
            st.session_state.current_task = f"Homepage AJAX (count={page_counter})..."
            st.rerun()
            ajax_data = {'commentNewCount': page_counter}
            # Set referer for AJAX request
            session.headers.update({'Referer': base_url})
            ajax_response = safe_request(session, 'POST', urljoin(base_url, REALGROUP_HOMEPAGE_AJAX), data=ajax_data)
            if not ajax_response:
                st.session_state.scraping_message = f"Homepage AJAX failed at count {page_counter}."
                break # Stop on AJAX failure
            ajax_html = ajax_response.text.strip()

            if not ajax_html:
                st.session_state.scraping_message = "Homepage AJAX: No more content."
                break

            _, ajax_intermediates = extract_rgl_links(ajax_html, base_url)
            if not ajax_intermediates:
                st.session_state.scraping_message = "Homepage AJAX: No new links, stopping."
                break

            new_count = len(ajax_intermediates)
            all_results.extend([{"Type": "Intermediate (Homepage AJAX)", "Source": f"AJAX (count={page_counter})", "Link": link} for link in ajax_intermediates])
            st.session_state.scraping_message = f"Homepage AJAX (count={page_counter}): +{new_count} links."
            st.rerun() # Update message
            page_counter += 8 # Increment by 8
            time.sleep(DEFAULT_DELAY) # Respectful delay

    except Exception as e:
        logger.error(f"Error in RGL homepage scraping loop: {e}")
        st.session_state.scraping_message = f"Error during RGL homepage scraping: {e}"
    return all_results

def scrape_rgl_category(category_url):
    """Scrapes an RGL category page and its AJAX-loaded content (with pause/resume/stop)."""
    if not st.session_state.session_object:
        st.session_state.session_object = create_robust_session()
    session = st.session_state.session_object
    all_results = []

    try:
        st.session_state.current_task = f"Fetching RGL Category: {category_url}"
        st.rerun()
        response = safe_request(session, 'GET', category_url)
        if not response:
             st.session_state.scraping_message = f"Failed to fetch RGL category {category_url}."
             return []
        initial_html = response.text
        direct_links, intermediate_links = extract_rgl_links(initial_html, category_url)
        all_results.extend([{"Type": "Direct (Category)", "Source": category_url, "Link": link} for link in direct_links])
        all_results.extend([{"Type": "Intermediate (Category)", "Source": category_url, "Link": link} for link in intermediate_links])
        st.session_state.scraping_message = f"Category: {len(direct_links) + len(intermediate_links)} initial links."
        st.rerun()
        time.sleep(DEFAULT_DELAY)

        soup = BeautifulSoup(initial_html, 'html.parser')
        # From Pasted_Text_1753383810262.txt, look for <input id="catid" value="...">
        cat_id_input = soup.find('input', {'id': 'catid'})
        if not cat_id_input or not cat_id_input.get('value'):
            st.session_state.scraping_message = "Could not find category ID for AJAX."
            st.rerun()
            return all_results # Return what we have
        cat_id = cat_id_input.get('value')
        st.session_state.scraping_message = f"Found category ID: {cat_id}. Starting AJAX..."
        st.rerun()
        time.sleep(DEFAULT_DELAY)

        # Based on JS in Pasted_Text_1753383810262.txt, category AJAX starts at 12, increments by 12
        page_counter = 12
        while st.session_state.scraping_state == 'running':
            st.session_state.current_task = f"Category AJAX (count={page_counter}, id={cat_id})..."
            st.rerun()
            ajax_data = {'commentNewCount': page_counter, 'catid': cat_id}
            session.headers.update({'Referer': category_url}) # Update referer
            # Use category_url as base for joining the AJAX endpoint, important if base_url differs
            ajax_response = safe_request(session, 'POST', urljoin(category_url, REALGROUP_CATEGORY_AJAX), data=ajax_data)
            if not ajax_response:
                 st.session_state.scraping_message = f"Category AJAX failed at count {page_counter}."
                 break
            ajax_html = ajax_response.text.strip()

            if not ajax_html:
                st.session_state.scraping_message = "Category AJAX: No more content."
                break

            _, ajax_intermediates = extract_rgl_links(ajax_html, category_url) # Use category_url as base
            if not ajax_intermediates:
                st.session_state.scraping_message = "Category AJAX: No new links, stopping."
                break

            new_count = len(ajax_intermediates)
            all_results.extend([{"Type": "Intermediate (Category AJAX)", "Source": f"AJAX (count={page_counter}, id={cat_id})", "Link": link} for link in ajax_intermediates])
            st.session_state.scraping_message = f"Category AJAX (count={page_counter}): +{new_count} links."
            st.rerun()
            page_counter += 12 # Increment by 12 (page size)
            time.sleep(DEFAULT_DELAY)

    except Exception as e:
        logger.error(f"Error in RGL category scraping loop: {e}")
        st.session_state.scraping_message = f"Error during RGL category scraping: {e}"
    return all_results

def scrape_gs_search(keyword):
    """Scrapes GroupSor search results (with pause/resume/stop)."""
    if not st.session_state.session_object:
        st.session_state.session_object = create_robust_session()
    session = st.session_state.session_object
    base_url = GROUPSOR_BASE_URL
    all_results = []

    try:
        search_url = f"{base_url}{GROUPSOR_SEARCH_PAGE}?keyword={quote_plus(keyword)}"
        st.session_state.current_task = f"Initiating GroupSor search for: {keyword}"
        st.rerun()
        # Initial search request to potentially set cookies/context
        safe_request(session, 'GET', search_url)
        time.sleep(DEFAULT_DELAY)

        # Based on JS in Pasted_Text_1753385726418.txt, starts at 0, increments by 1
        page_counter = 0
        while st.session_state.scraping_state == 'running':
            st.session_state.current_task = f"GroupSor Search AJAX (page={page_counter})..."
            st.rerun()
            ajax_data = {'group_no': page_counter, 'keyword': keyword}
            headers = {'Referer': search_url}
            # Update session headers temporarily
            original_headers = session.headers.copy()
            session.headers.update(headers)
            ajax_response = safe_request(session, 'POST', urljoin(base_url, GROUPSOR_SEARCH_AJAX), data=ajax_data)
            # Restore original headers
            session.headers.clear()
            session.headers.update(original_headers)

            if not ajax_response:
                 # Specific check for 403 or other persistent failures
                 st.session_state.scraping_message = f"GroupSor AJAX failed at page {page_counter} (likely 403 or connection error)."
                 break # Stop scraping on persistent failure
            ajax_html = ajax_response.text.strip()

            # Check for end condition (string found in Pasted_Text_1753385726418.txt)
            if not ajax_html or "<div id=\"no\" style=\"display: none;color: #555\">No More groups</div>" in ajax_html:
                st.session_state.scraping_message = "GroupSor Search AJAX: No more content."
                break

            soup = BeautifulSoup(ajax_html, 'html.parser')
            join_links = []
            # Look for links to the join page: /group/join/{GROUP_ID}
            # Example pattern from description: <a href="/group/join/C9VkRBCEGJLG1Dl3OkVlKT">
            join_link_tags = soup.find_all('a', href=re.compile(r'/group/join/[A-Za-z0-9]+'))
            for tag in join_link_tags:
                href = tag.get('href')
                if href:
                    full_url = urljoin(base_url, href)
                    join_links.append(full_url)

            if not join_links:
                st.session_state.scraping_message = "GroupSor Search AJAX: No new links, stopping."
                break

            new_count = len(join_links)
            all_results.extend([{"Type": "Intermediate (GroupSor Join Link)", "Source": f"Search AJAX (page={page_counter})", "Link": link} for link in join_links])
            st.session_state.scraping_message = f"GroupSor Search AJAX (page={page_counter}): +{new_count} links."
            st.rerun()
            page_counter += 1 # Increment by 1
            time.sleep(DEFAULT_DELAY + 0.5) # Slightly longer delay for GroupSor

    except Exception as e:
        logger.error(f"Error in GroupSor search scraping loop: {e}")
        st.session_state.scraping_message = f"Error during GroupSor search scraping: {e}"
    return all_results

def resolve_intermediate_links(results, competitor):
    """Resolves intermediate links to final WhatsApp URLs (with pause/resume/stop)."""
    if not results or st.session_state.scraping_state != 'running':
        return results

    intermediate_results = [r for r in results if 'Intermediate' in r['Type']]
    if not intermediate_results:
        st.session_state.scraping_message = "No intermediate links to resolve."
        st.rerun()
        return results

    resolved_results = []
    total_intermediates = len(intermediate_results)
    st.session_state.scraping_message = f"Resolving {total_intermediates} intermediate links..."
    st.rerun()

    for i, result in enumerate(intermediate_results):
        if st.session_state.scraping_state != 'running':
            break # Stop if paused or stopped
        intermediate_link = result['Link']
        st.session_state.scraping_progress = (i + 1) / total_intermediates
        st.session_state.current_task = f"Resolving {i+1}/{total_intermediates}"
        st.rerun()
        final_url = None

        if competitor == "RealGroupLinks.com":
            final_url = get_final_whatsapp_url_rgl(intermediate_link)
        elif competitor == "GroupSor.link":
            final_url = get_final_whatsapp_url_gs(intermediate_link)

        if final_url and final_url.startswith("http"):
            resolved_results.append({"Type": "Final (Resolved)", "Source": intermediate_link, "Link": final_url})
        else:
            resolved_results.append({"Type": "Final (Failed/Not Found)", "Source": intermediate_link, "Link": final_url or "ERROR"})
        time.sleep(0.2) # Small delay between resolutions

    st.session_state.scraping_progress = 0 # Reset progress bar
    success_count = len([r for r in resolved_results if r['Type'] == 'Final (Resolved)'])
    st.session_state.scraping_message = f"Finished resolving. Success: {success_count}/{total_intermediates}"
    st.rerun()
    non_intermediate_results = [r for r in results if 'Intermediate' not in r['Type']]
    return non_intermediate_results + resolved_results

# --- Streamlit App ---

def main():
    st.set_page_config(page_title="WhatsApp Group Scraper", page_icon="🔍")
    st.title("🔍 WhatsApp Group Scraper (RGL & GroupSor)")
    st.markdown("Scrapes group links. Handles pauses/stops.")

    # --- Configuration ---
    st.sidebar.header("Configuration")
    competitor = st.sidebar.selectbox("Select Competitor", ["RealGroupLinks.com", "GroupSor.link"])

    target = "Homepage"
    category_path = ""
    search_keyword = ""
    if competitor == "RealGroupLinks.com":
        target = st.sidebar.selectbox("Target", ["Homepage", "Specific Category"])
        if target == "Specific Category":
            category_path = st.sidebar.text_input("Category Path (e.g., /category/tamil/)", value="/category/tamil/")
    elif competitor == "GroupSor.link":
        target = "Search by Keyword"
        search_keyword = st.sidebar.text_input("Search Keyword", value="girls")

    resolve_intermediates = st.sidebar.checkbox("Resolve Intermediate Links", value=True)

    # --- Control Buttons ---
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("▶️ Start"):
            if st.session_state.scraping_state == 'idle' or st.session_state.scraping_state == 'stopped':
                st.session_state.scraped_data = []
                st.session_state.scraping_state = 'running'
                st.session_state.scraping_message = "Starting scrape..."
                st.session_state.current_task = "Initializing..."
                st.session_state.scraping_progress = 0
                # Create session only if it doesn't exist or was closed
                if not st.session_state.session_object:
                     st.session_state.session_object = create_robust_session()
                st.rerun()
    with col2:
        if st.button("⏸️ Pause"):
            if st.session_state.scraping_state == 'running':
                st.session_state.scraping_state = 'paused'
                st.rerun()
    with col3:
        if st.button("⏹️ Stop"):
            if st.session_state.scraping_state in ['running', 'paused']:
                st.session_state.scraping_state = 'stopped'
                st.session_state.scraping_message = "Scraping stopped by user."
                st.session_state.current_task = "Stopped."
                # Optionally close session
                # if st.session_state.session_object:
                #     st.session_state.session_object.close()
                #     st.session_state.session_object = None
                st.rerun()

    # --- Progress and Status ---
    st.progress(st.session_state.scraping_progress)
    st.info(f"**Status:** {st.session_state.scraping_message}")
    st.caption(f"*Task:* {st.session_state.current_task}")

    # --- Scrape Execution (in parts based on state) ---
    if st.session_state.scraping_state == 'running':
        try:
            # Determine scrape function to call
            scrape_function = None
            scrape_args = ()
            if competitor == "RealGroupLinks.com":
                if target == "Homepage":
                    scrape_function = scrape_rgl_homepage
                elif target == "Specific Category":
                    if not category_path:
                        st.session_state.scraping_message = "Error: Category path is empty."
                        st.session_state.scraping_state = 'stopped'
                        st.rerun()
                        return
                    full_category_url = urljoin(REALGROUP_BASE_URL, category_path)
                    scrape_function = scrape_rgl_category
                    scrape_args = (full_category_url,)
            elif competitor == "GroupSor.link":
                if target == "Search by Keyword":
                    if not search_keyword.strip():
                        st.session_state.scraping_message = "Error: Search keyword is empty."
                        st.session_state.scraping_state = 'stopped'
                        st.rerun()
                        return
                    scrape_function = scrape_gs_search
                    scrape_args = (search_keyword.strip(),)

            if scrape_function:
                st.session_state.scraped_data = scrape_function(*scrape_args)

            # --- Resolve Intermediate Links ---
            if resolve_intermediates and st.session_state.scraped_data and st.session_state.scraping_state == 'running':
                st.session_state.scraped_data = resolve_intermediate_links(st.session_state.scraped_data, competitor)

            # --- Finalize ---
            if st.session_state.scraping_state == 'running': # Only if finished normally
                 if st.session_state.scraped_data: # FIXED LINE 536
                      # Deduplicate final results
                      unique_results_set = set((item['Type'], item['Source'], item['Link']) for item in st.session_state.scraped_data)
                      st.session_state.scraped_data = [{"Type": item[0], "Source": item[1], "Link": item[2]} for item in unique_results_set]
                 st.session_state.scraping_message = f"✅ Finished! Found {len(st.session_state.scraped_data)} unique items."
                 st.session_state.current_task = "Complete."
                 st.session_state.scraping_state = 'idle' # Reset state
            elif st.session_state.scraping_state == 'paused':
                 st.session_state.scraping_message = "⏸️ Paused. Click 'Start' to resume."
                 st.session_state.current_task = "Paused."
            elif st.session_state.scraping_state == 'stopped':
                 # Message already set by stop button
                 pass

        except Exception as e:
            logger.error(f"An unexpected error occurred during scraping: {e}", exc_info=True)
            st.session_state.scraping_message = f"💥 Unexpected error: {e}"
            st.session_state.scraping_state = 'stopped'
            st.session_state.current_task = "Error."
        st.rerun() # Re-run to update UI at the end of the scraping process

    # --- Resume Button (only shown when paused) ---
    if st.session_state.scraping_state == 'paused':
        st.divider()
        if st.button("▶️ Resume"):
            st.session_state.scraping_state = 'running'
            st.session_state.scraping_message = "Resuming scrape..."
            st.rerun()

    # --- Display Results ---
    if st.session_state.scraped_data: # FIXED LINE 569
        st.divider()
        st.subheader("📊 Scraped Data")
        df = pd.DataFrame(st.session_state.scraped_data)
        st.dataframe(df, use_container_width=True)

        # CSV Download
        csv_buffer = io.StringIO()
        df.to_csv(csv_buffer, index=False)
        csv_data = csv_buffer.getvalue()
        csv_buffer.close()

        st.download_button(
            label="💾 Download CSV",
            data=csv_data,
            file_name='scraped_whatsapp_links.csv',
            mime='text/csv',
        )
    else:
        if st.session_state.scraping_state == 'idle':
            st.info("Configure options and click 'Start'.")

if __name__ == "__main__":
    main()
