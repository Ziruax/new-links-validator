# app.py
import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
import time
import logging
from urllib.parse import urljoin, urlparse
import json

# --- Configuration ---
DEFAULT_BASE_URL = "https://realgrouplinks.com"
AJAX_ENDPOINT = "/load-more-cat.php"
HOMEPAGE_AJAX_ENDPOINT = "/more-groups.php"
TIMEOUT = 15  # Timeout for requests (seconds)
AJAX_PAGE_SIZE = 12 # Estimate from the JS, adjust if needed
DEFAULT_CAT_ID = 34 # Fallback category ID
# --- End Configuration ---

# Configure logging (Streamlit shows logs if needed)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Session State Initialization ---
if 'is_running' not in st.session_state:
    st.session_state.is_running = False
if 'is_paused' not in st.session_state:
    st.session_state.is_paused = False
if 'current_page' not in st.session_state: # For AJAX scraping
    st.session_state.current_page = 1
if 'all_results' not in st.session_state:
    st.session_state.all_results = []
if 'base_url' not in st.session_state:
    st.session_state.base_url = DEFAULT_BASE_URL
if 'option' not in st.session_state:
    st.session_state.option = "Homepage"
if 'category_path' not in st.session_state:
    st.session_state.category_path = "/category/tamil/"
if 'resolve_intermediates' not in st.session_state:
    st.session_state.resolve_intermediates = True
if 'scraping_target_info' not in st.session_state: # Store info like cat_id for resume
    st.session_state.scraping_target_info = {}
if 'intermediate_results_to_resolve' not in st.session_state: # For intermediate resolution state
    st.session_state.intermediate_results_to_resolve = []
if 'intermediate_current_index' not in st.session_state: # Track progress in resolving
    st.session_state.intermediate_current_index = 0


# --- Helper Functions (using session state where needed) ---

def get_final_whatsapp_url_bs4(group_php_url):
    """Fetches the intermediate page and extracts the final WhatsApp URL from JS."""
    logger.info(f"Fetching intermediate page: {group_php_url}")
    try:
        response = requests.get(group_php_url, timeout=TIMEOUT)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')

        script_tags = soup.find_all('script')
        for script_tag in script_tags:
            script_content = script_tag.string
            if script_content:
                match = re.search(r"setTimeout\s*\(.*?window\.location\.href\s*=\s*['\"](https?://chat\.whatsapp\.com/[^'\"]*)['\"]", script_content, re.DOTALL | re.IGNORECASE)
                if match:
                    final_url = match.group(1)
                    logger.info(f"Found final URL in JS: {final_url}")
                    return final_url

        logger.warning(f"Final URL not found in JS on {group_php_url}")
        return None

    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching {group_php_url}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error parsing {group_php_url}: {e}")
        return None

def extract_links_from_html(html_content, base_url):
    """Extracts direct and intermediate group links from HTML content."""
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

    potential_intermediate_tags = soup.find_all('a', onclick=re.compile(r'group\.php\?id='))
    for tag in potential_intermediate_tags:
        onclick_attr = tag.get('onclick')
        if onclick_attr:
            match = re.search(r"singlegroup\(\s*['\"]([^'\"]*group\.php\?id=\d+)['\"]", onclick_attr)
            if match:
                relative_or_absolute_url = match.group(1)
                full_url = urljoin(base_url, relative_or_absolute_url)
                intermediate_links.add(full_url)

    logger.info(f"Extracted {len(direct_links)} direct links and {len(intermediate_links)} intermediate links.")
    return list(direct_links), list(intermediate_links)

def scrape_category_via_ajax_step(base_url, cat_id, current_page):
    """Performs one step of scraping for a category via AJAX."""
    ajax_url = urljoin(base_url, AJAX_ENDPOINT.lstrip('/'))
    comment_new_count = current_page * AJAX_PAGE_SIZE
    data = {
        'commentNewCount': comment_new_count,
        'catid': cat_id
    }
    logger.info(f"[AJAX Step] Fetching page {current_page} for category {cat_id}")
    st.info(f"🔄 [AJAX] Fetching page {current_page} for category ID {cat_id}...")

    try:
        response = requests.post(ajax_url, data=data, timeout=TIMEOUT)
        response.raise_for_status()
        html_content = response.text.strip()

        if not html_content or html_content == "":
            logger.info(f"[AJAX Step] No more content on page {current_page}.")
            st.info(f"✅ [AJAX] No more groups on page {current_page}.")
            return [], current_page + 1, True # finished

        _, ajax_links_on_page = extract_links_from_html(html_content, base_url)
        ajax_links_on_page = [link for link in ajax_links_on_page if 'group.php?id=' in link]

        if not ajax_links_on_page:
             logger.info(f"[AJAX Step] No new links on page {current_page}.")
             st.info(f"⚠️ [AJAX] No new links on page {current_page}.")
             return [], current_page + 1, True # Consider finished if no links

        logger.info(f"[AJAX Step] Found {len(ajax_links_on_page)} links on page {current_page}.")
        st.info(f"📄 [AJAX] Page {current_page}: Found {len(ajax_links_on_page)} links.")
        return ajax_links_on_page, current_page + 1, False # not finished

    except requests.exceptions.Timeout:
        logger.error(f"[AJAX Step] Timeout on page {current_page}.")
        st.warning(f"⏰ [AJAX] Timeout fetching page {current_page}.")
        return [], current_page, True # Stop on timeout
    except requests.exceptions.RequestException as e:
        logger.error(f"[AJAX Step] Request error on page {current_page}: {e}")
        st.warning(f"❌ [AJAX] Error fetching page {current_page}: {e}.")
        return [], current_page, True # Stop on error
    except Exception as e:
         logger.error(f"[AJAX Step] Unexpected error on page {current_page}: {e}")
         st.warning(f"💥 [AJAX] Unexpected error on page {current_page}: {e}.")
         return [], current_page, True # Stop on error

def scrape_homepage_via_ajax_step(base_url, current_page):
    """Performs one step of scraping for the homepage via AJAX."""
    ajax_url = urljoin(base_url, HOMEPAGE_AJAX_ENDPOINT.lstrip('/'))
    # Starts at 16, increments by 8 (from JS)
    comment_new_count = 16 + (current_page - 1) * 8
    data = {
        'commentNewCount': comment_new_count
    }
    logger.info(f"[Homepage AJAX Step] Fetching page {current_page}")
    st.info(f"🔄 [Homepage AJAX] Fetching page {current_page}...")

    try:
        response = requests.post(ajax_url, data=data, timeout=TIMEOUT)
        response.raise_for_status()
        html_content = response.text.strip()

        if not html_content or html_content == "":
            logger.info(f"[Homepage AJAX Step] No more content on page {current_page}.")
            st.info(f"✅ [Homepage AJAX] No more groups on page {current_page}.")
            return [], current_page + 1, True

        _, ajax_links_on_page = extract_links_from_html(html_content, base_url)
        ajax_links_on_page = [link for link in ajax_links_on_page if 'group.php?id=' in link]

        if not ajax_links_on_page:
             logger.info(f"[Homepage AJAX Step] No new links on page {current_page}.")
             st.info(f"⚠️ [Homepage AJAX] No new links on page {current_page}.")
             return [], current_page + 1, True

        logger.info(f"[Homepage AJAX Step] Found {len(ajax_links_on_page)} links on page {current_page}.")
        st.info(f"📄 [Homepage AJAX] Page {current_page}: Found {len(ajax_links_on_page)} links.")
        return ajax_links_on_page, current_page + 1, False

    except requests.exceptions.Timeout:
        logger.error(f"[Homepage AJAX Step] Timeout on page {current_page}.")
        st.warning(f"⏰ [Homepage AJAX] Timeout fetching page {current_page}.")
        return [], current_page, True
    except requests.exceptions.RequestException as e:
        logger.error(f"[Homepage AJAX Step] Request error on page {current_page}: {e}")
        st.warning(f"❌ [Homepage AJAX] Error fetching page {current_page}: {e}.")
        return [], current_page, True
    except Exception as e:
         logger.error(f"[Homepage AJAX Step] Unexpected error on page {current_page}: {e}")
         st.warning(f"💥 [Homepage AJAX] Unexpected error on page {current_page}: {e}.")
         return [], current_page, True

def get_category_id(html_content):
    """Attempts to extract the category ID from the page's HTML."""
    soup = BeautifulSoup(html_content, 'html.parser')
    try:
        cat_id_element = soup.find('input', {'id': 'catid'})
        if cat_id_element and cat_id_element.get('value'):
            return int(cat_id_element.get('value'))
    except (ValueError, TypeError) as e:
        logger.warning(f"Error parsing category ID from HTML: {e}")
    return DEFAULT_CAT_ID

def scrape_page_bs4(url):
    """Scrapes a single page for initial links."""
    logger.info(f"Scraping page: {url}")
    try:
        response = requests.get(url, timeout=TIMEOUT)
        response.raise_for_status()
        html_content = response.text
        return extract_links_from_html(html_content, url)
    except requests.exceptions.RequestException as e:
        logger.error(f"Error scraping {url}: {e}")
        st.error(f"Error fetching {url}: {e}")
        return [], []
    except Exception as e:
        logger.error(f"Unexpected error scraping {url}: {e}")
        st.error(f"Unexpected error processing {url}: {e}")
        return [], []

# --- Streamlit App Logic ---

def main():
    st.set_page_config(page_title="RealGroupLinks Scraper (BS4)", page_icon="🔍")
    st.title("🔍 RealGroupLinks.com Scraper (Requests + BS4)")
    st.markdown("""
    This tool scrapes WhatsApp group links from `realgrouplinks.com` using `requests` and `BeautifulSoup4`.
    It handles:
    - Direct links
    - Links behind modal popups (intermediate pages)
    - AJAX-based pagination (for homepage and categories)
    - Timer-based redirects (on intermediate pages)
    - **Pause/Resume Functionality**
    """)

    # --- Input Configuration (bound to session state) ---
    st.sidebar.header("Configuration")
    st.session_state.base_url = st.sidebar.text_input("Base URL", value=st.session_state.base_url)
    st.session_state.option = st.sidebar.selectbox("Scraping Target", ("Homepage", "Specific Category (w/ AJAX)"), index=0 if st.session_state.option == "Homepage" else 1)
    
    if st.session_state.option == "Specific Category (w/ AJAX)":
        st.session_state.category_path = st.sidebar.text_input("Enter category path (e.g., /category/tamil/):", value=st.session_state.category_path)

    st.session_state.resolve_intermediates = st.sidebar.checkbox("Resolve Intermediate Links", value=st.session_state.resolve_intermediates)
    st.sidebar.markdown("---")
    st.sidebar.markdown("**Note:** Scraping involves multiple HTTP requests. Use Pause/Resume for long tasks.")

    # --- Pause/Resume Controls ---
    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        if not st.session_state.is_running and not st.session_state.is_paused:
            if st.button("▶️ Start Scraping", key="start_button"):
                if not st.session_state.base_url:
                    st.error("Please enter a Base URL.")
                    return
                # Reset state for a new run
                st.session_state.is_running = True
                st.session_state.is_paused = False
                st.session_state.current_page = 1
                st.session_state.all_results = []
                st.session_state.scraping_target_info = {}
                st.session_state.intermediate_results_to_resolve = []
                st.session_state.intermediate_current_index = 0
                st.experimental_rerun() # Refresh to show running state

    with col2:
        if st.session_state.is_running and not st.session_state.is_paused:
            if st.button("⏸️ Pause Scraping", key="pause_button"):
                st.session_state.is_running = False
                st.session_state.is_paused = True
                st.experimental_rerun() # Refresh to show paused state

    with col3:
        if st.session_state.is_paused:
            if st.button("▶️ Resume Scraping", key="resume_button"):
                st.session_state.is_running = True
                st.session_state.is_paused = False
                st.experimental_rerun() # Refresh to resume

    # --- Display Current Status ---
    if st.session_state.is_paused:
        st.info(f"⏸️ **Scraping Paused.** Collected {len(st.session_state.all_results)} items so far.")
    elif st.session_state.is_running:
        st.info("🔄 **Scraping in progress...**")

    # --- Main Scraping Logic (Runs in chunks based on session state) ---
    if st.session_state.is_running:
        base_url = st.session_state.base_url
        option = st.session_state.option
        category_path = st.session_state.category_path
        resolve_intermediates = st.session_state.resolve_intermediates

        try:
            # --- Phase 1: Initial Scrape and AJAX Loading ---
            if not st.session_state.scraping_target_info: # Initial setup for the target
                st.session_state.scraping_target_info['type'] = option
                if option == "Homepage":
                    with st.spinner("Scraping Initial Homepage Content..."):
                        direct_links, intermediate_links = scrape_page_bs4(base_url)
                        initial_count = len(direct_links) + len(intermediate_links)
                        st.session_state.all_results.extend([{"Type": "Direct", "Source": base_url, "Link": link} for link in direct_links])
                        st.session_state.all_results.extend([{"Type": "Intermediate", "Source": base_url, "Link": link} for link in intermediate_links])
                        st.info(f"Found {initial_count} initial links on the homepage.")
                    st.session_state.scraping_target_info['ajax_type'] = 'homepage'
                    st.session_state.current_page = 1 # Start AJAX from page 1

                elif option == "Specific Category (w/ AJAX)":
                    if not category_path:
                        st.warning("Please enter a category path.")
                        st.session_state.is_running = False
                        st.experimental_rerun()
                        return
                    category_url = urljoin(base_url, category_path)
                    with st.spinner(f"Scraping Initial Category Page Content: {category_url}"):
                        try:
                            response = requests.get(category_url, timeout=TIMEOUT)
                            response.raise_for_status()
                            initial_html = response.text
                            initial_direct_links, initial_intermediate_links = extract_links_from_html(initial_html, category_url)
                            initial_count = len(initial_direct_links) + len(initial_intermediate_links)
                            st.session_state.all_results.extend([{"Type": "Direct", "Source": category_url, "Link": link} for link in initial_direct_links])
                            st.session_state.all_results.extend([{"Type": "Intermediate", "Source": category_url, "Link": link} for link in initial_intermediate_links])
                            st.info(f"Found {initial_count} initial links on the category page.")

                            cat_id = get_category_id(initial_html)
                            st.info(f"Found category ID: {cat_id}")
                            st.session_state.scraping_target_info['ajax_type'] = 'category'
                            st.session_state.scraping_target_info['cat_id'] = cat_id
                            st.session_state.current_page = 1 # Start AJAX from page 1

                        except requests.exceptions.RequestException as e:
                            st.error(f"Error fetching category page {category_url}: {e}")
                            st.session_state.is_running = False
                            st.experimental_rerun()
                            return
                        except Exception as e:
                            st.error(f"Error processing category page {category_url}: {e}")
                            st.session_state.is_running = False
                            st.experimental_rerun()
                            return

            # --- Phase 2: AJAX Scraping Loop (Step by Step) ---
            if st.session_state.scraping_target_info.get('ajax_type') == 'homepage':
                new_links, next_page, finished = scrape_homepage_via_ajax_step(base_url, st.session_state.current_page)
                if new_links:
                    st.session_state.all_results.extend([{"Type": "Intermediate (AJAX)", "Source": f"AJAX (Homepage)", "Link": link} for link in new_links])
                st.session_state.current_page = next_page
                if finished:
                    st.success("✅ Homepage AJAX scraping finished.")
                    # Move to intermediate resolution phase
                    st.session_state.scraping_target_info['ajax_finished'] = True
                    if resolve_intermediates:
                        st.session_state.intermediate_results_to_resolve = [r for r in st.session_state.all_results if 'Intermediate' in r['Type']]
                        st.session_state.intermediate_current_index = 0
                        st.session_state.scraping_target_info['resolving_intermediates'] = True
                    else:
                        st.session_state.is_running = False # Done if not resolving
                        st.session_state.scraping_target_info['finished'] = True

            elif st.session_state.scraping_target_info.get('ajax_type') == 'category':
                 cat_id = st.session_state.scraping_target_info.get('cat_id', DEFAULT_CAT_ID)
                 new_links, next_page, finished = scrape_category_via_ajax_step(base_url, cat_id, st.session_state.current_page)
                 if new_links:
                    st.session_state.all_results.extend([{"Type": "Intermediate (AJAX)", "Source": f"AJAX (Cat {cat_id})", "Link": link} for link in new_links])
                 st.session_state.current_page = next_page
                 if finished:
                    st.success("✅ Category AJAX scraping finished.")
                    st.session_state.scraping_target_info['ajax_finished'] = True
                    if resolve_intermediates:
                        st.session_state.intermediate_results_to_resolve = [r for r in st.session_state.all_results if 'Intermediate' in r['Type']]
                        st.session_state.intermediate_current_index = 0
                        st.session_state.scraping_target_info['resolving_intermediates'] = True
                    else:
                        st.session_state.is_running = False
                        st.session_state.scraping_target_info['finished'] = True

            # --- Phase 3: Resolve Intermediates (Step by Step) ---
            if st.session_state.scraping_target_info.get('resolving_intermediates'):
                intermediates = st.session_state.intermediate_results_to_resolve
                current_idx = st.session_state.intermediate_current_index
                if current_idx < len(intermediates):
                    result = intermediates[current_idx]
                    intermediate_link = result['Link']
                    st.info(f"🔗 Resolving intermediate link {current_idx + 1}/{len(intermediates)}: {intermediate_link}")
                    final_url = get_final_whatsapp_url_bs4(intermediate_link)
                    if final_url:
                        st.session_state.all_results.append({"Type": "Final (from Intermediate)", "Source": intermediate_link, "Link": final_url})
                    else:
                        st.session_state.all_results.append({"Type": "Final (FAILED/Not Found)", "Source": intermediate_link, "Link": "ERROR"})
                    
                    st.session_state.intermediate_current_index += 1
                    time.sleep(0.1) # Small delay

                else:
                    st.success("✅ Finished resolving all intermediate links.")
                    # Cleanup intermediate data and mark finished
                    st.session_state.all_results = [r for r in st.session_state.all_results if 'Intermediate' not in r['Type']] + \
                                                  [r for r in st.session_state.all_results if r['Type'] in ['Final (from Intermediate)', 'Final (FAILED/Not Found)']]
                    st.session_state.scraping_target_info['resolving_intermediates'] = False
                    st.session_state.scraping_target_info['finished'] = True
                    st.session_state.is_running = False

            # --- Deduplication (only once at the end or when paused) ---
            # This is tricky with step-by-step, so we do it less frequently or at the end.
            # For simplicity here, we deduplicate only when finished or paused.
            # A more robust way would be to use a set for `all_results` internally.

            # --- Rerun to continue the loop ---
            if st.session_state.is_running and not st.session_state.is_paused:
                st.experimental_rerun()

        except Exception as e:
            logger.error(f"An unexpected error occurred in the main app logic: {e}", exc_info=True)
            st.error(f"💥 An unexpected error occurred: {e}")
            st.session_state.is_running = False
            st.experimental_rerun()

    # --- Display Results (always shown if data exists) ---
    # Deduplicate results for display/download
    if st.session_state.all_results:
        # Simple deduplication using a set of tuples
        unique_results_set = set((item['Type'], item['Source'], item['Link']) for item in st.session_state.all_results)
        unique_all_results = [{"Type": item[0], "Source": item[1], "Link": item[2]} for item in unique_results_set]
        
        st.subheader("Scraped Data")
        st.write(f"Total unique items: {len(unique_all_results)}")
        df = st.dataframe(unique_all_results)
        
        # Create CSV data
        csv_lines = ["Type,Source,Link"] # Header
        csv_lines.extend([f"{item['Type']},{item['Source']},{item['Link']}" for item in unique_all_results])
        csv_data = "\n".join(csv_lines)

        st.download_button(
            label="💾 Download CSV",
            data=csv_data,
            file_name='realgrouplinks_scraped_data.csv',
            mime='text/csv',
        )
        
        if st.session_state.is_paused:
            st.info("ℹ️ You can download the data collected so far.")
        elif st.session_state.scraping_target_info.get('finished'):
             st.success("🎉 Full scraping process finished!")
        else:
             st.info("ℹ️ Scraping is in progress or paused.")

    else:
        if not st.session_state.is_running and not st.session_state.is_paused:
            st.info("ℹ️ Click 'Start Scraping' to begin.")


if __name__ == "__main__":
    main()
