# app.py
import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
import time
import logging
from urllib.parse import urljoin, urlparse, parse_qs, urlencode
import json

# --- Configuration ---
DEFAULT_BASE_URL = "https://realgrouplinks.com"
AJAX_ENDPOINT = "/load-more-cat.php"
HOMEPAGE_AJAX_ENDPOINT = "/more-groups.php"
GROUPSOR_AJAX_ENDPOINT = "/group/findmore"
TIMEOUT = 15  # Timeout for requests (seconds)
AJAX_PAGE_SIZE = 12 # Estimate from the JS, adjust if needed
GROUPSOR_PAGE_SIZE = 1 # Seems to increment by 1 based on 'group_no'
DEFAULT_CAT_ID = 34 # Fallback category ID for realgrouplinks
# --- End Configuration ---

# Configure logging (Streamlit shows logs if needed)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Session State Initialization (No changes needed) ---
if 'is_running' not in st.session_state:
    st.session_state.is_running = False
if 'is_paused' not in st.session_state:
    st.session_state.is_paused = False
if 'current_page' not in st.session_state:
    st.session_state.current_page = 0 # Start at 0 for groupsor
if 'all_results' not in st.session_state:
    st.session_state.all_results = []
if 'base_url' not in st.session_state:
    st.session_state.base_url = DEFAULT_BASE_URL
if 'option' not in st.session_state:
    st.session_state.option = "Homepage (RealGroupLinks)"
if 'category_path' not in st.session_state:
    st.session_state.category_path = "/category/tamil/"
if 'resolve_intermediates' not in st.session_state:
    st.session_state.resolve_intermediates = True
if 'scraping_target_info' not in st.session_state:
    st.session_state.scraping_target_info = {}
if 'intermediate_results_to_resolve' not in st.session_state:
    st.session_state.intermediate_results_to_resolve = []
if 'intermediate_current_index' not in st.session_state:
    st.session_state.intermediate_current_index = 0

# --- Helper Functions (Existing + New ones for groupsor.link) ---

# --- Existing Helper Functions (get_final_whatsapp_url_bs4, extract_links_from_html, etc.) ---
# ... (Keep all the existing helper functions from the previous version exactly as they were)
# ... (They are omitted here for brevity but are essential)
# Example of one key existing function signature (implementation unchanged):
def get_final_whatsapp_url_bs4(group_php_url):
    # ... (Implementation from previous version)
    pass

def extract_links_from_html(html_content, base_url):
     # ... (Implementation from previous version)
     pass

def scrape_category_via_ajax_step(base_url, cat_id, current_page):
     # ... (Implementation from previous version)
     pass

def scrape_homepage_via_ajax_step(base_url, current_page):
     # ... (Implementation from previous version)
     pass

def get_category_id(html_content):
     # ... (Implementation from previous version)
     pass

def scrape_page_bs4(url):
     # ... (Implementation from previous version)
     pass

# --- NEW Helper Functions for groupsor.link ---

def get_groupsor_ajax_params(html_content, base_url):
    """Attempts to extract AJAX parameters (gcid, cid, lid) from the initial page."""
    gcid = ""
    cid = ""
    lid = ""
    # Default fallback if not found or if scraping base category
    # Try to find them in the JS code
    soup = BeautifulSoup(html_content, 'html.parser')
    scripts = soup.find_all('script')
    for script in scripts:
        if script.string and 'group/findmore' in script.string:
             # Example: var gcid = '7'; var cid = ''; var lid = '';
             gcid_match = re.search(r"var\s+gcid\s*=\s*['\"]([^'\"]*)['\"]", script.string)
             cid_match = re.search(r"var\s+cid\s*=\s*['\"]([^'\"]*)['\"]", script.string)
             lid_match = re.search(r"var\s+lid\s*=\s*['\"]([^'\"]*)['\"]", script.string)
             if gcid_match:
                 gcid = gcid_match.group(1)
             if cid_match:
                 cid = cid_match.group(1)
             if lid_match:
                 lid = lid_match.group(1)
             logger.info(f"Extracted AJAX params for groupsor: gcid={gcid}, cid={cid}, lid={lid}")
             break # Assume first relevant script has the params
    # If not found, they might be passed via data attributes or URL params
    # Fallback to empty strings is okay for now, request might still work.
    return gcid, cid, lid

def scrape_groupsor_category_via_ajax_step(base_url, category_url, current_page, gcid="", cid="", lid=""):
    """Performs one step of scraping for a groupsor.link category via AJAX."""
    ajax_url = urljoin(base_url, GROUPSOR_AJAX_ENDPOINT.lstrip('/'))
    # Parameters for the AJAX request
    # GET for initial load, POST for subsequent loads based on JS
    # We'll try POST as it seems to be the standard way after initial load
    data = {
        'group_no': current_page, # Starts at 0
        'gcid': gcid,
        'cid': cid,
        'lid': lid
    }
    logger.info(f"[GroupSor AJAX Step] Fetching page {current_page} for {category_url} with data {data}")
    st.info(f"🔄 [GroupSor AJAX] Fetching page {current_page}...")

    try:
        # Use POST as per the JS logic for 'load more'
        response = requests.post(ajax_url, data=data, timeout=TIMEOUT, headers={'Referer': category_url}) # Add referer header
        response.raise_for_status()
        html_content = response.text.strip()

        if not html_content or html_content == "" or "<div id=\"no\" style=\"display: none;color: #555\">No More groups</div>" in html_content:
            logger.info(f"[GroupSor AJAX Step] No more content on page {current_page}.")
            st.info(f"✅ [GroupSor AJAX] No more groups on page {current_page}.")
            return [], current_page + 1, True # finished

        # Parse the returned HTML snippet for group links
        # Look for links to the join page: /group/join/{GROUP_ID}
        # Example from description: <a href="/group/join/C9VkRBCEGJLG1Dl3OkVlKT">
        soup = BeautifulSoup(html_content, 'html.parser')
        join_links = []
        join_link_tags = soup.find_all('a', href=re.compile(r'/group/join/[A-Za-z0-9]+'))
        for tag in join_link_tags:
            href = tag.get('href')
            if href:
                full_url = urljoin(base_url, href)
                join_links.append(full_url)

        if not join_links:
             logger.info(f"[GroupSor AJAX Step] No new join links found on page {current_page}.")
             st.info(f"⚠️ [GroupSor AJAX] No new join links on page {current_page}.")
             # It's hard to tell if finished or just no links, let's assume if one page is empty, we stop
             return [], current_page + 1, True # Consider finished

        logger.info(f"[GroupSor AJAX Step] Found {len(join_links)} join links on page {current_page}.")
        st.info(f"📄 [GroupSor AJAX] Page {current_page}: Found {len(join_links)} join links.")
        return join_links, current_page + 1, False # not finished

    except requests.exceptions.Timeout:
        logger.error(f"[GroupSor AJAX Step] Timeout on page {current_page}.")
        st.warning(f"⏰ [GroupSor AJAX] Timeout fetching page {current_page}.")
        return [], current_page, True # Stop on timeout
    except requests.exceptions.RequestException as e:
        logger.error(f"[GroupSor AJAX Step] Request error on page {current_page}: {e}")
        st.warning(f"❌ [GroupSor AJAX] Error fetching page {current_page}: {e}.")
        return [], current_page, True # Stop on error
    except Exception as e:
         logger.error(f"[GroupSor AJAX Step] Unexpected error on page {current_page}: {e}")
         st.warning(f"💥 [GroupSor AJAX] Unexpected error on page {current_page}: {e}.")
         return [], current_page, True # Stop on error

def get_final_whatsapp_url_groupsor(join_url):
    """Fetches the groupsor intermediate join page and extracts the final WhatsApp URL."""
    logger.info(f"Fetching groupsor intermediate page: {join_url}")
    try:
        response = requests.get(join_url, timeout=TIMEOUT)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')

        # Look for the actual WhatsApp link
        # Common patterns: direct link, link in a button, link in a meta tag, or within script
        # Let's try common locations first

        # 1. Direct link in an anchor tag
        whatsapp_links = soup.find_all('a', href=re.compile(r'chat\.whatsapp\.com'))
        for link_tag in whatsapp_links:
            href = link_tag.get('href')
            if href and 'chat.whatsapp.com' in href:
                logger.info(f"Found final URL (direct link): {href}")
                return href

        # 2. Link might be in an onclick attribute or similar
        # Example patterns to look for in scripts or onclicks if direct link not found
        # This part might need adjustment based on actual page structure

        # 3. Look in scripts for window.location or similar
        script_tags = soup.find_all('script')
        for script_tag in script_tags:
            script_content = script_tag.string
            if script_content:
                # Pattern: window.location.href = 'THE_URL';
                match = re.search(r"window\.location\.href\s*=\s*['\"](https?://chat\.whatsapp\.com/[^'\"]*)['\"]", script_content, re.IGNORECASE)
                if match:
                    final_url = match.group(1)
                    logger.info(f"Found final URL in JS (window.location): {final_url}")
                    return final_url
                # Pattern: window.open('THE_URL');
                match_open = re.search(r"window\.open\(['\"](https?://chat\.whatsapp\.com/[^'\"]*)['\"]", script_content, re.IGNORECASE)
                if match_open:
                    final_url = match_open.group(1)
                    logger.info(f"Found final URL in JS (window.open): {final_url}")
                    return final_url

        logger.warning(f"Final URL not found on groupsor join page {join_url}")
        return None

    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching groupsor join page {join_url}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error parsing groupsor join page {join_url}: {e}")
        return None

# --- Streamlit App Logic (Updated) ---

def main():
    st.set_page_config(page_title="Multi-Site WhatsApp Scraper (BS4)", page_icon="🔍")
    st.title("🔍 Multi-Site WhatsApp Group Scraper (Requests + BS4)")
    st.markdown("""
    This tool scrapes WhatsApp group links from competitor sites using `requests` and `BeautifulSoup4`.
    Supported Sites:
    - `realgrouplinks.com`
    - `groupsor.link` (New!)
    It handles:
    - Direct links
    - Links behind intermediate pages
    - Site-specific AJAX-based pagination
    - Timer-based redirects (on intermediate pages)
    - **Pause/Resume Functionality**
    """)

    # --- Input Configuration ---
    st.sidebar.header("Configuration")
    # Allow editing Base URL
    st.session_state.base_url = st.sidebar.text_input("Base URL", value=st.session_state.base_url)
    # Updated options to specify the site
    st.session_state.option = st.sidebar.selectbox(
        "Scraping Target",
        (
            "Homepage (RealGroupLinks)",
            "Specific Category (RealGroupLinks, w/ AJAX)",
            "Specific Category (GroupSor.link, w/ AJAX)" # New Option
        ),
        index=["Homepage (RealGroupLinks)", "Specific Category (RealGroupLinks, w/ AJAX)", "Specific Category (GroupSor.link, w/ AJAX)"].index(st.session_state.option) if st.session_state.option in ["Homepage (RealGroupLinks)", "Specific Category (RealGroupLinks, w/ AJAX)", "Specific Category (GroupSor.link, w/ AJAX)"] else 0
    )

    # Input for category path (relevant for specific categories)
    if "Specific Category" in st.session_state.option:
        default_path = "/category/tamil/" if "RealGroupLinks" in st.session_state.option else "/group/find" # Default for groupsor
        st.session_state.category_path = st.sidebar.text_input(
            f"Enter category path for {st.session_state.option.split('(')[1].split(')')[0]}:",
            value=st.session_state.category_path if st.session_state.category_path else default_path
        )

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
                st.session_state.current_page = 0 if "GroupSor" in st.session_state.option else 1 # GroupSor starts at 0
                st.session_state.all_results = []
                st.session_state.scraping_target_info = {}
                st.session_state.intermediate_results_to_resolve = []
                st.session_state.intermediate_current_index = 0
                st.experimental_rerun()

    with col2:
        if st.session_state.is_running and not st.session_state.is_paused:
            if st.button("⏸️ Pause Scraping", key="pause_button"):
                st.session_state.is_running = False
                st.session_state.is_paused = True
                st.experimental_rerun()

    with col3:
        if st.session_state.is_paused:
            if st.button("▶️ Resume Scraping", key="resume_button"):
                st.session_state.is_running = True
                st.session_state.is_paused = False
                st.experimental_rerun()

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
            # --- Phase 1: Initial Setup and Scrape ---
            if not st.session_state.scraping_target_info: # Initial setup for the target
                st.session_state.scraping_target_info['type'] = option
                if option == "Homepage (RealGroupLinks)":
                    # --- Logic for RealGroupLinks Homepage ---
                    with st.spinner("Scraping Initial Homepage Content..."):
                        direct_links, intermediate_links = scrape_page_bs4(base_url)
                        initial_count = len(direct_links) + len(intermediate_links)
                        st.session_state.all_results.extend([{"Type": "Direct", "Source": base_url, "Link": link} for link in direct_links])
                        st.session_state.all_results.extend([{"Type": "Intermediate", "Source": base_url, "Link": link} for link in intermediate_links])
                        st.info(f"Found {initial_count} initial links on the homepage.")
                    st.session_state.scraping_target_info['ajax_type'] = 'homepage_realgrouplinks'
                    st.session_state.current_page = 1

                elif option == "Specific Category (RealGroupLinks, w/ AJAX)":
                    # --- Logic for RealGroupLinks Category ---
                    if not category_path:
                        st.warning("Please enter a category path for RealGroupLinks.")
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
                            st.session_state.scraping_target_info['ajax_type'] = 'category_realgrouplinks'
                            st.session_state.scraping_target_info['cat_id'] = cat_id
                            st.session_state.current_page = 1

                        except requests.exceptions.RequestException as e:
                            st.error(f"Error fetching RealGroupLinks category page {category_url}: {e}")
                            st.session_state.is_running = False
                            st.experimental_rerun()
                            return
                        except Exception as e:
                            st.error(f"Error processing RealGroupLinks category page {category_url}: {e}")
                            st.session_state.is_running = False
                            st.experimental_rerun()
                            return

                elif option == "Specific Category (GroupSor.link, w/ AJAX)":
                    # --- Logic for GroupSor.link Category ---
                    if not category_path:
                        st.warning("Please enter a category path for GroupSor.link (e.g., /group/find).")
                        st.session_state.is_running = False
                        st.experimental_rerun()
                        return
                    category_url = urljoin(base_url, category_path)
                    with st.spinner(f"Scraping Initial GroupSor Category Setup: {category_url}"):
                        try:
                            response = requests.get(category_url, timeout=TIMEOUT)
                            response.raise_for_status()
                            initial_html = response.text
                            # No initial links on main page for groupsor, get AJAX params
                            gcid, cid, lid = get_groupsor_ajax_params(initial_html, base_url)
                            st.info(f"Found AJAX params for GroupSor: gcid={gcid}, cid={cid}, lid={lid}")
                            st.session_state.scraping_target_info['ajax_type'] = 'category_groupsor'
                            st.session_state.scraping_target_info['gcid'] = gcid
                            st.session_state.scraping_target_info['cid'] = cid
                            st.session_state.scraping_target_info['lid'] = lid
                            st.session_state.current_page = 0 # GroupSor AJAX starts at 0

                        except requests.exceptions.RequestException as e:
                            st.error(f"Error fetching GroupSor category page {category_url}: {e}")
                            st.session_state.is_running = False
                            st.experimental_rerun()
                            return
                        except Exception as e:
                            st.error(f"Error processing GroupSor category page {category_url}: {e}")
                            st.session_state.is_running = False
                            st.experimental_rerun()
                            return

            # --- Phase 2: AJAX Scraping Loop (Step by Step) ---
            # --- Existing RealGroupLinks AJAX Logic ---
            if st.session_state.scraping_target_info.get('ajax_type') == 'homepage_realgrouplinks':
                # ... (Existing logic for RealGroupLinks homepage AJAX)
                new_links, next_page, finished = scrape_homepage_via_ajax_step(base_url, st.session_state.current_page)
                if new_links:
                    st.session_state.all_results.extend([{"Type": "Intermediate (AJAX)", "Source": f"AJAX (Homepage)", "Link": link} for link in new_links])
                st.session_state.current_page = next_page
                if finished:
                    st.success("✅ RealGroupLinks Homepage AJAX scraping finished.")
                    st.session_state.scraping_target_info['ajax_finished'] = True
                    # ... (rest of resolution logic)

            elif st.session_state.scraping_target_info.get('ajax_type') == 'category_realgrouplinks':
                 # ... (Existing logic for RealGroupLinks category AJAX)
                 cat_id = st.session_state.scraping_target_info.get('cat_id', DEFAULT_CAT_ID)
                 new_links, next_page, finished = scrape_category_via_ajax_step(base_url, cat_id, st.session_state.current_page)
                 if new_links:
                    st.session_state.all_results.extend([{"Type": "Intermediate (AJAX)", "Source": f"AJAX (Cat {cat_id})", "Link": link} for link in new_links])
                 st.session_state.current_page = next_page
                 if finished:
                    st.success("✅ RealGroupLinks Category AJAX scraping finished.")
                    st.session_state.scraping_target_info['ajax_finished'] = True
                    # ... (rest of resolution logic)

            # --- NEW AJAX Logic for GroupSor.link ---
            elif st.session_state.scraping_target_info.get('ajax_type') == 'category_groupsor':
                gcid = st.session_state.scraping_target_info.get('gcid', "")
                cid = st.session_state.scraping_target_info.get('cid', "")
                lid = st.session_state.scraping_target_info.get('lid', "")
                # Reconstruct category URL for referer (or use base_url if not available easily)
                category_url_for_referer = urljoin(base_url, st.session_state.category_path) if st.session_state.category_path else base_url

                new_join_links, next_page, finished = scrape_groupsor_category_via_ajax_step(
                    base_url, category_url_for_referer, st.session_state.current_page, gcid, cid, lid
                )
                if new_join_links:
                    # Store the join links as intermediates
                    st.session_state.all_results.extend([{"Type": "Intermediate (GroupSor Join Link)", "Source": f"GroupSor AJAX Page {st.session_state.current_page}", "Link": link} for link in new_join_links])
                st.session_state.current_page = next_page
                if finished:
                    st.success("✅ GroupSor Category AJAX scraping finished.")
                    st.session_state.scraping_target_info['ajax_finished'] = True
                    if resolve_intermediates:
                        st.session_state.intermediate_results_to_resolve = [r for r in st.session_state.all_results if 'Intermediate' in r['Type']]
                        st.session_state.intermediate_current_index = 0
                        st.session_state.scraping_target_info['resolving_intermediates'] = True
                    else:
                        st.session_state.is_running = False
                        st.session_state.scraping_target_info['finished'] = True

            # --- Phase 3: Resolve Intermediates (Updated to handle GroupSor) ---
            if st.session_state.scraping_target_info.get('resolving_intermediates'):
                intermediates = st.session_state.intermediate_results_to_resolve
                current_idx = st.session_state.intermediate_current_index
                if current_idx < len(intermediates):
                    result = intermediates[current_idx]
                    intermediate_link = result['Link']
                    link_type = result['Type']
                    st.info(f"🔗 Resolving intermediate link {current_idx + 1}/{len(intermediates)}: {intermediate_link}")

                    final_url = None
                    if "GroupSor" in link_type:
                        final_url = get_final_whatsapp_url_groupsor(intermediate_link)
                    else: # Default to RealGroupLinks logic
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

            # --- Rerun to continue the loop ---
            if st.session_state.is_running and not st.session_state.is_paused:
                st.experimental_rerun()

        except Exception as e:
            logger.error(f"An unexpected error occurred in the main app logic: {e}", exc_info=True)
            st.error(f"💥 An unexpected error occurred: {e}")
            st.session_state.is_running = False
            st.experimental_rerun()

    # --- Display Results (always shown if data exists) ---
    # Deduplicate results for display/download (same as before)
    if st.session_state.all_results:
        unique_results_set = set((item['Type'], item['Source'], item['Link']) for item in st.session_state.all_results)
        unique_all_results = [{"Type": item[0], "Source": item[1], "Link": item[2]} for item in unique_results_set]

        st.subheader("Scraped Data")
        st.write(f"Total unique items: {len(unique_all_results)}")
        df = st.dataframe(unique_all_results)

        csv_lines = ["Type,Source,Link"]
        csv_lines.extend([f"{item['Type']},{item['Source']},{item['Link']}" for item in unique_all_results])
        csv_data = "\n".join(csv_lines)

        st.download_button(
            label="💾 Download CSV",
            data=csv_data,
            file_name='scraped_whatsapp_links.csv', # Generic name
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
            st.info("ℹ️ Configure options and click 'Start Scraping' to begin.")


if __name__ == "__main__":
    main()
