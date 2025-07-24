# app.py
import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
import time
import logging
from urllib.parse import urljoin, urlparse, quote_plus
import json

# --- Configuration ---
COMPETITORS = {
    "RealGroupLinks.com": "https://realgrouplinks.com",
    "GroupSor.link": "https://groupsor.link"
}
# RealGroupLinks
RL_AJAX_ENDPOINT = "/load-more-cat.php"
RL_HOMEPAGE_AJAX_ENDPOINT = "/more-groups.php"
RL_DEFAULT_CAT_ID = 34

# GroupSor
GS_AJAX_ENDPOINT = "/group/findmore"
GS_SEARCH_ENDPOINT = "/group/search" # Base for search
GS_DEFAULT_PAGE_SIZE = 1 # Seems to increment by 1 based on 'group_no'

TIMEOUT = 15  # Timeout for requests (seconds)
# --- End Configuration ---

# Configure logging (Streamlit shows logs if needed)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Session State Initialization ---
if 'is_running' not in st.session_state:
    st.session_state.is_running = False
if 'is_paused' not in st.session_state:
    st.session_state.is_paused = False
if 'current_page' not in st.session_state:
    st.session_state.current_page = 0 # Start at 0 for groupsor
if 'all_results' not in st.session_state:
    st.session_state.all_results = []
# --- Removed base_url from session state, using selected competitor ---
if 'selected_competitor' not in st.session_state:
    st.session_state.selected_competitor = list(COMPETITORS.keys())[0] # Default to first
if 'option' not in st.session_state:
    st.session_state.option = "Homepage"
if 'category_path' not in st.session_state:
    st.session_state.category_path = "/category/tamil/" # Default for RealGroupLinks
if 'gs_search_keyword' not in st.session_state: # New for GroupSor search
    st.session_state.gs_search_keyword = "girls" # Default keyword
if 'resolve_intermediates' not in st.session_state:
    st.session_state.resolve_intermediates = True
if 'scraping_target_info' not in st.session_state:
    st.session_state.scraping_target_info = {}
if 'intermediate_results_to_resolve' not in st.session_state:
    st.session_state.intermediate_results_to_resolve = []
if 'intermediate_current_index' not in st.session_state:
    st.session_state.intermediate_current_index = 0

# --- Helper Functions ---

# --- Existing Helper Functions adapted for competitor selection ---
# ... (Previous helper functions like get_final_whatsapp_url_bs4, extract_links_from_html,
# scrape_category_via_ajax_step, scrape_homepage_via_ajax_step, get_category_id, scrape_page_bs4
# need to be included here. They are omitted for brevity but are essential.
# Make sure they use the base_url derived from COMPETITORS[st.session_state.selected_competitor]
# Example signature for one (implementation similar to previous versions):
def get_final_whatsapp_url_bs4(group_php_url, base_url):
    # ... (Implementation from previous version, adjusted if needed)
    # base_url parameter added for context if needed, though might not be used directly here
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

# --- NEW Helper Functions for groupsor.link (Search & AJAX) ---

def get_groupsor_search_params(html_content):
    """Attempts to extract hidden form inputs or relevant params from the search results page."""
    # Often search results pages have hidden inputs or JS vars for pagination/AJAX.
    # For simplicity, we'll assume the AJAX call just needs 'group_no' and 'keyword'.
    # More complex params can be extracted if needed later.
    # This function can be expanded if the search results page provides specific params.
    # For now, returning an empty dict means we rely on defaults.
    params = {}
    soup = BeautifulSoup(html_content, 'html.parser')
    # Example: look for hidden inputs
    hidden_inputs = soup.find_all('input', type='hidden')
    for inp in hidden_inputs:
        name = inp.get('name')
        value = inp.get('value')
        if name and value is not None:
            params[name] = value
    logger.info(f"Extracted potential AJAX params from GroupSor search page: {params}")
    return params

def scrape_groupsor_search_via_ajax_step(base_url, search_keyword, current_page):
    """Performs one step of scraping for a groupsor.link search via AJAX."""
    ajax_url = urljoin(base_url, GS_AJAX_ENDPOINT.lstrip('/'))
    # Parameters for the AJAX request
    # Based on JS: $.post('https://groupsor.link/group/findmore', {'group_no': total_record, 'keyword': keyword}, ...
    data = {
        'group_no': current_page, # Starts at 0
        'keyword': search_keyword # Pass the keyword
        # Add other params if get_groupsor_search_params finds them and they are needed
    }
    logger.info(f"[GroupSor Search AJAX Step] Fetching page {current_page} for keyword '{search_keyword}' with data {data}")
    st.info(f"🔄 [GroupSor Search AJAX] Fetching page {current_page} for '{search_keyword}'...")

    try:
        # Use POST as per the JS logic for 'load more' on search results
        # Construct a referer URL for the search results page
        referer_url = f"{base_url}{GS_SEARCH_ENDPOINT}?keyword={quote_plus(search_keyword)}"
        response = requests.post(ajax_url, data=data, timeout=TIMEOUT, headers={'Referer': referer_url})
        response.raise_for_status()
        html_content = response.text.strip()

        # Check for "No More groups" indicator
        if not html_content or html_content == "" or "<div id=\"no\" style=\"display: none;color: #555\">No More groups</div>" in html_content:
            logger.info(f"[GroupSor Search AJAX Step] No more content on page {current_page}.")
            st.info(f"✅ [GroupSor Search AJAX] No more groups on page {current_page}.")
            return [], current_page + 1, True # finished

        # Parse the returned HTML snippet for group links
        soup = BeautifulSoup(html_content, 'html.parser')
        join_links = []
        # Look for links to the join page: /group/join/{GROUP_ID}
        join_link_tags = soup.find_all('a', href=re.compile(r'/group/join/[A-Za-z0-9]+'))
        for tag in join_link_tags:
            href = tag.get('href')
            if href:
                full_url = urljoin(base_url, href)
                join_links.append(full_url)

        if not join_links:
             logger.info(f"[GroupSor Search AJAX Step] No new join links found on page {current_page}.")
             st.info(f"⚠️ [GroupSor Search AJAX] No new join links on page {current_page}.")
             # Assume finished if one page is empty after initial load
             return [], current_page + 1, True

        logger.info(f"[GroupSor Search AJAX Step] Found {len(join_links)} join links on page {current_page}.")
        st.info(f"📄 [GroupSor Search AJAX] Page {current_page}: Found {len(join_links)} join links.")
        return join_links, current_page + 1, False # not finished

    except requests.exceptions.Timeout:
        logger.error(f"[GroupSor Search AJAX Step] Timeout on page {current_page}.")
        st.warning(f"⏰ [GroupSor Search AJAX] Timeout fetching page {current_page}.")
        return [], current_page, True # Stop on timeout
    except requests.exceptions.RequestException as e:
        logger.error(f"[GroupSor Search AJAX Step] Request error on page {current_page}: {e}")
        st.warning(f"❌ [GroupSor Search AJAX] Error fetching page {current_page}: {e}.")
        return [], current_page, True # Stop on error
    except Exception as e:
         logger.error(f"[GroupSor Search AJAX Step] Unexpected error on page {current_page}: {e}")
         st.warning(f"💥 [GroupSor Search AJAX] Unexpected error on page {current_page}: {e}.")
         return [], current_page, True # Stop on error

def get_final_whatsapp_url_groupsor(join_url):
    """Fetches the groupsor intermediate join page and extracts the final WhatsApp URL."""
    logger.info(f"Fetching groupsor intermediate page: {join_url}")
    try:
        response = requests.get(join_url, timeout=TIMEOUT)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')

        # Look for the actual WhatsApp link
        # 1. Direct link in an anchor tag (most common)
        whatsapp_links = soup.find_all('a', href=re.compile(r'chat\.whatsapp\.com'))
        for link_tag in whatsapp_links:
            href = link_tag.get('href')
            if href and 'chat.whatsapp.com' in href:
                logger.info(f"Found final URL (direct link): {href}")
                return href

        # 2. Look in scripts for window.location or window.open
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
    - `groupsor.link`
    It handles:
    - Direct links
    - Links behind intermediate pages
    - Site-specific AJAX-based pagination/loading
    - Timer-based redirects (on intermediate pages)
    - **Pause/Resume Functionality**
    """)

    # --- Input Configuration ---
    st.sidebar.header("Configuration")
    # Dropdown for competitor website selection
    st.session_state.selected_competitor = st.sidebar.selectbox(
        "Select Competitor Website",
        options=list(COMPETITORS.keys()),
        index=list(COMPETITORS.keys()).index(st.session_state.selected_competitor) if st.session_state.selected_competitor in COMPETITORS else 0
    )
    # Derive base_url from selection
    base_url = COMPETITORS[st.session_state.selected_competitor]

    # Option selection based on competitor
    competitor_options = {
        "RealGroupLinks.com": ["Homepage", "Specific Category (w/ AJAX)"],
        "GroupSor.link": ["Homepage", "Search by Keyword (w/ AJAX)"] # Updated option for GroupSor
    }
    available_options = competitor_options.get(st.session_state.selected_competitor, ["Homepage"])
    st.session_state.option = st.sidebar.selectbox(
        "Scraping Target",
        options=available_options,
        index=available_options.index(st.session_state.option) if st.session_state.option in available_options else 0
    )

    # Input for category path or search keyword based on option
    if st.session_state.option == "Specific Category (w/ AJAX)" and st.session_state.selected_competitor == "RealGroupLinks.com":
        st.session_state.category_path = st.sidebar.text_input(
            "Enter category path for RealGroupLinks:",
            value=st.session_state.category_path if st.session_state.category_path else "/category/tamil/"
        )
    elif st.session_state.option == "Search by Keyword (w/ AJAX)" and st.session_state.selected_competitor == "GroupSor.link":
        st.session_state.gs_search_keyword = st.sidebar.text_input(
            "Enter search keyword for GroupSor:",
            value=st.session_state.gs_search_keyword if st.session_state.gs_search_keyword else "girls"
        )

    st.session_state.resolve_intermediates = st.sidebar.checkbox("Resolve Intermediate Links", value=st.session_state.resolve_intermediates)
    st.sidebar.markdown("---")
    st.sidebar.markdown("**Note:** Scraping involves multiple HTTP requests. Use Pause/Resume for long tasks.")

    # --- Pause/Resume Controls ---
    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        if not st.session_state.is_running and not st.session_state.is_paused:
            if st.button("▶️ Start Scraping", key="start_button"):
                # Validation
                if st.session_state.option == "Specific Category (w/ AJAX)" and st.session_state.selected_competitor == "RealGroupLinks.com" and not st.session_state.category_path:
                    st.error("Please enter a category path for RealGroupLinks.")
                    return
                if st.session_state.option == "Search by Keyword (w/ AJAX)" and st.session_state.selected_competitor == "GroupSor.link" and not st.session_state.gs_search_keyword.strip():
                    st.error("Please enter a search keyword for GroupSor.")
                    return

                # Reset state for a new run
                st.session_state.is_running = True
                st.session_state.is_paused = False
                st.session_state.current_page = 0 # Reset page counter
                st.session_state.all_results = []
                st.session_state.scraping_target_info = {}
                st.session_state.intermediate_results_to_resolve = []
                st.session_state.intermediate_current_index = 0
                st.rerun() # Use st.rerun() instead of st.experimental_rerun()

    with col2:
        if st.session_state.is_running and not st.session_state.is_paused:
            if st.button("⏸️ Pause Scraping", key="pause_button"):
                st.session_state.is_running = False
                st.session_state.is_paused = True
                st.rerun()

    with col3:
        if st.session_state.is_paused:
            if st.button("▶️ Resume Scraping", key="resume_button"):
                st.session_state.is_running = True
                st.session_state.is_paused = False
                st.rerun()

    # --- Display Current Status ---
    if st.session_state.is_paused:
        st.info(f"⏸️ **Scraping Paused.** Collected {len(st.session_state.all_results)} items so far.")
    elif st.session_state.is_running:
        st.info("🔄 **Scraping in progress...**")

    # --- Main Scraping Logic (Runs in chunks based on session state) ---
    if st.session_state.is_running:
        # base_url is derived from the selection above
        option = st.session_state.option
        resolve_intermediates = st.session_state.resolve_intermediates

        try:
            # --- Phase 1: Initial Setup and Scrape ---
            if not st.session_state.scraping_target_info: # Initial setup for the target
                st.session_state.scraping_target_info['competitor'] = st.session_state.selected_competitor
                st.session_state.scraping_target_info['type'] = option

                if st.session_state.selected_competitor == "RealGroupLinks.com":
                    if option == "Homepage":
                        with st.spinner("Scraping Initial RealGroupLinks Homepage Content..."):
                            direct_links, intermediate_links = scrape_page_bs4(base_url)
                            initial_count = len(direct_links) + len(intermediate_links)
                            st.session_state.all_results.extend([{"Type": "Direct", "Source": base_url, "Link": link} for link in direct_links])
                            st.session_state.all_results.extend([{"Type": "Intermediate", "Source": base_url, "Link": link} for link in intermediate_links])
                            st.info(f"Found {initial_count} initial links on the homepage.")
                        st.session_state.scraping_target_info['ajax_type'] = 'homepage_realgrouplinks'
                        st.session_state.current_page = 1

                    elif option == "Specific Category (w/ AJAX)":
                        category_path = st.session_state.category_path
                        if not category_path:
                             # This check is also in the button, but good to have
                             st.warning("Please enter a category path for RealGroupLinks.")
                             st.session_state.is_running = False
                             st.rerun()
                             return
                        category_url = urljoin(base_url, category_path)
                        with st.spinner(f"Scraping Initial RealGroupLinks Category Page Content: {category_url}"):
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
                                st.rerun()
                                return
                            except Exception as e:
                                st.error(f"Error processing RealGroupLinks category page {category_url}: {e}")
                                st.session_state.is_running = False
                                st.rerun()
                                return

                elif st.session_state.selected_competitor == "GroupSor.link":
                    if option == "Homepage":
                        # GroupSor Homepage scraping logic (if applicable, might need AJAX too)
                        # Placeholder or specific logic if homepage groups are loaded differently
                        # For now, let's assume homepage scraping for GroupSor is not the primary focus
                        # or requires different handling. We can implement it later if needed.
                        # Let's treat homepage as search with an empty keyword or a default one.
                        # Or, we can disable homepage option for GroupSor.
                        # For this update, we focus on search.
                        st.warning("Homepage scraping for GroupSor.link might require specific implementation. Consider using 'Search by Keyword'.")
                        st.session_state.is_running = False
                        st.rerun()
                        return # Stop if homepage selected for GroupSor for now

                    elif option == "Search by Keyword (w/ AJAX)":
                         search_keyword = st.session_state.gs_search_keyword.strip()
                         if not search_keyword:
                             st.warning("Please enter a search keyword for GroupSor.")
                             st.session_state.is_running = False
                             st.rerun()
                             return
                         # Construct the initial search URL
                         search_url = f"{base_url}{GS_SEARCH_ENDPOINT}?keyword={quote_plus(search_keyword)}"
                         with st.spinner(f"Setting up GroupSor Search for '{search_keyword}'..."):
                             try:
                                 response = requests.get(search_url, timeout=TIMEOUT)
                                 response.raise_for_status()
                                 initial_html = response.text
                                 # Get initial AJAX params if any (though likely not needed for keyword search)
                                 # ajax_params = get_groupsor_search_params(initial_html) # Not used directly here yet
                                 # No initial links on main search page? Or scrape them?
                                 # Let's assume initial links are loaded via the first AJAX call.
                                 # So, we just prepare for AJAX scraping.
                                 st.session_state.scraping_target_info['ajax_type'] = 'search_groupsor'
                                 st.session_state.scraping_target_info['search_keyword'] = search_keyword
                                 st.session_state.current_page = 0 # GroupSor AJAX for search starts at 0

                             except requests.exceptions.RequestException as e:
                                 st.error(f"Error initiating GroupSor search for '{search_keyword}': {e}")
                                 st.session_state.is_running = False
                                 st.rerun()
                                 return
                             except Exception as e:
                                 st.error(f"Error processing GroupSor search setup for '{search_keyword}': {e}")
                                 st.session_state.is_running = False
                                 st.rerun()
                                 return

            # --- Phase 2: AJAX Scraping Loop (Step by Step) ---
            # --- RealGroupLinks AJAX Logic ---
            if st.session_state.scraping_target_info.get('ajax_type') == 'homepage_realgrouplinks':
                new_links, next_page, finished = scrape_homepage_via_ajax_step(base_url, st.session_state.current_page)
                if new_links:
                    st.session_state.all_results.extend([{"Type": "Intermediate (AJAX)", "Source": f"AJAX (Homepage)", "Link": link} for link in new_links])
                st.session_state.current_page = next_page
                if finished:
                    st.success("✅ RealGroupLinks Homepage AJAX scraping finished.")
                    st.session_state.scraping_target_info['ajax_finished'] = True
                    if resolve_intermediates:
                        st.session_state.intermediate_results_to_resolve = [r for r in st.session_state.all_results if 'Intermediate' in r['Type']]
                        st.session_state.intermediate_current_index = 0
                        st.session_state.scraping_target_info['resolving_intermediates'] = True
                    else:
                        st.session_state.is_running = False
                        st.session_state.scraping_target_info['finished'] = True

            elif st.session_state.scraping_target_info.get('ajax_type') == 'category_realgrouplinks':
                 cat_id = st.session_state.scraping_target_info.get('cat_id', RL_DEFAULT_CAT_ID)
                 new_links, next_page, finished = scrape_category_via_ajax_step(base_url, cat_id, st.session_state.current_page)
                 if new_links:
                    st.session_state.all_results.extend([{"Type": "Intermediate (AJAX)", "Source": f"AJAX (Cat {cat_id})", "Link": link} for link in new_links])
                 st.session_state.current_page = next_page
                 if finished:
                    st.success("✅ RealGroupLinks Category AJAX scraping finished.")
                    st.session_state.scraping_target_info['ajax_finished'] = True
                    if resolve_intermediates:
                        st.session_state.intermediate_results_to_resolve = [r for r in st.session_state.all_results if 'Intermediate' in r['Type']]
                        st.session_state.intermediate_current_index = 0
                        st.session_state.scraping_target_info['resolving_intermediates'] = True
                    else:
                        st.session_state.is_running = False
                        st.session_state.scraping_target_info['finished'] = True

            # --- NEW AJAX Logic for GroupSor.link Search ---
            elif st.session_state.scraping_target_info.get('ajax_type') == 'search_groupsor':
                search_keyword = st.session_state.scraping_target_info.get('search_keyword', "")
                new_join_links, next_page, finished = scrape_groupsor_search_via_ajax_step(
                    base_url, search_keyword, st.session_state.current_page
                )
                if new_join_links:
                    st.session_state.all_results.extend([{"Type": "Intermediate (GroupSor Join Link)", "Source": f"GroupSor Search AJAX Page {st.session_state.current_page}", "Link": link} for link in new_join_links])
                st.session_state.current_page = next_page
                if finished:
                    st.success("✅ GroupSor Search AJAX scraping finished.")
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
                        # Pass base_url if needed by the function
                        final_url = get_final_whatsapp_url_bs4(intermediate_link, base_url)

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
                st.rerun() # Use st.rerun() instead of st.experimental_rerun()

        except Exception as e:
            logger.error(f"An unexpected error occurred in the main app logic: {e}", exc_info=True)
            st.error(f"💥 An unexpected error occurred: {e}")
            st.session_state.is_running = False
            st.rerun() # Use st.rerun() instead of st.experimental_rerun()

    # --- Display Results (always shown if data exists) ---
    # Deduplicate results for display/download
    if st.session_state.all_results:
        # Simple deduplication using a set of tuples
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
            file_name='scraped_whatsapp_links.csv',
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
