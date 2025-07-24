# app.py
import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
import time
import logging
from urllib.parse import urljoin, urlparse
import pandas as pd
import io

# --- Configuration ---
REALGROUP_BASE_URL = "https://realgrouplinks.com"
REALGROUP_HOMEPAGE_AJAX = "/more-groups.php"
REALGROUP_CATEGORY_AJAX = "/load-more-cat.php"
GROUPSOR_BASE_URL = "https://groupsor.link"
GROUPSOR_SEARCH_AJAX = "/group/findmore"
GROUPSOR_SEARCH_PAGE = "/group/search"
TIMEOUT = 15
MAX_RETRIES = 2
RETRY_DELAY = 2 # seconds

# --- Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Helper Functions ---

def get_final_whatsapp_url_rgl(group_url, session):
    """
    Fetches the RGL intermediate page and extracts the final WhatsApp URL.
    Handles retries.
    """
    logger.info(f"Fetching RGL intermediate page: {group_url}")
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = session.get(group_url, timeout=TIMEOUT)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')
            # Look for setTimeout with window.location.href
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

        except requests.exceptions.RequestException as e:
            logger.error(f"Attempt {attempt + 1} failed fetching {group_url}: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
            else:
                logger.error(f"Failed to fetch {group_url} after {MAX_RETRIES + 1} attempts.")
                return None
        except Exception as e:
            logger.error(f"Unexpected error parsing {group_url}: {e}")
            return None
    return None

def get_final_whatsapp_url_gs(join_url, session):
    """
    Fetches the GroupSor join page and extracts the final WhatsApp URL.
    Handles retries.
    """
    logger.info(f"Fetching GroupSor join page: {join_url}")
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = session.get(join_url, timeout=TIMEOUT)
            response.raise_for_status()

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

        except requests.exceptions.RequestException as e:
            logger.error(f"Attempt {attempt + 1} failed fetching {join_url}: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
            else:
                logger.error(f"Failed to fetch {join_url} after {MAX_RETRIES + 1} attempts.")
                return None
        except Exception as e:
            logger.error(f"Unexpected error parsing GroupSor join page {join_url}: {e}")
            return None
    return None

def extract_rgl_links(html_content, base_url):
    """Extracts direct and intermediate group links from RGL HTML."""
    direct_links = set()
    intermediate_links = set()
    soup = BeautifulSoup(html_content, 'html.parser')

    # Direct links
    direct_link_tags = soup.find_all('a', href=re.compile(r'chat\.whatsapp\.com'))
    for tag in direct_link_tags:
        href = tag.get('href')
        if href:
            parsed_url = urlparse(href)
            if parsed_url.scheme and parsed_url.netloc and 'chat.whatsapp.com' in parsed_url.netloc:
                direct_links.add(href)

    # Intermediate links (from onclick)
    # Example: onclick="singlegroup('https://realgrouplinks.com/group.php?id=775164',...
    potential_intermediates = soup.find_all('a', onclick=re.compile(r'group\.php\?id='))
    for tag in potential_intermediates:
        onclick_attr = tag.get('onclick')
        if onclick_attr:
            match = re.search(r"singlegroup\(\s*['\"]([^'\"]*group\.php\?id=\d+)['\"]", onclick_attr)
            if match:
                relative_or_absolute_url = match.group(1)
                full_url = urljoin(base_url, relative_or_absolute_url)
                intermediate_links.add(full_url)

    logger.info(f"RGL Extracted {len(direct_links)} direct, {len(intermediate_links)} intermediate links.")
    return list(direct_links), list(intermediate_links)

def scrape_rgl_homepage(base_url, session):
    """Scrapes the RGL homepage and its AJAX-loaded content."""
    all_results = []
    try:
        response = session.get(base_url, timeout=TIMEOUT)
        response.raise_for_status()
        initial_html = response.text
        direct_links, intermediate_links = extract_rgl_links(initial_html, base_url)
        all_results.extend([{"Type": "Direct (Homepage)", "Source": base_url, "Link": link} for link in direct_links])
        all_results.extend([{"Type": "Intermediate (Homepage)", "Source": base_url, "Link": link} for link in intermediate_links])
        st.info(f"Homepage: Found {len(direct_links) + len(intermediate_links)} initial links.")

        # Scrape AJAX pages (Homepage uses /more-groups.php)
        page_counter = 16 # Starts at 16 based on JS analysis
        while True:
            st.info(f"Homepage AJAX: Fetching page with commentNewCount={page_counter}...")
            ajax_data = {'commentNewCount': page_counter}
            ajax_response = session.post(urljoin(base_url, REALGROUP_HOMEPAGE_AJAX), data=ajax_data, timeout=TIMEOUT)
            ajax_response.raise_for_status()
            ajax_html = ajax_response.text.strip()

            if not ajax_html:
                st.info("Homepage AJAX: No more content.")
                break

            _, ajax_intermediates = extract_rgl_links(ajax_html, base_url)
            if not ajax_intermediates:
                st.info("Homepage AJAX: No new links found, stopping.")
                break

            all_results.extend([{"Type": "Intermediate (Homepage AJAX)", "Source": f"AJAX (commentNewCount={page_counter})", "Link": link} for link in ajax_intermediates])
            st.info(f"Homepage AJAX: Found {len(ajax_intermediates)} links.")
            page_counter += 8 # Increments by 8
            time.sleep(0.5) # Be respectful

    except requests.exceptions.RequestException as e:
        st.error(f"Error scraping RGL homepage: {e}")
    except Exception as e:
        st.error(f"Unexpected error scraping RGL homepage: {e}")
    return all_results

def scrape_rgl_category(category_url, session):
    """Scrapes an RGL category page and its AJAX-loaded content."""
    all_results = []
    try:
        response = session.get(category_url, timeout=TIMEOUT)
        response.raise_for_status()
        initial_html = response.text
        direct_links, intermediate_links = extract_rgl_links(initial_html, category_url)
        all_results.extend([{"Type": "Direct (Category)", "Source": category_url, "Link": link} for link in direct_links])
        all_results.extend([{"Type": "Intermediate (Category)", "Source": category_url, "Link": link} for link in intermediate_links])
        st.info(f"Category: Found {len(direct_links) + len(intermediate_links)} initial links.")

        # Get category ID
        soup = BeautifulSoup(initial_html, 'html.parser')
        cat_id_input = soup.find('input', {'id': 'catid'})
        if not cat_id_input or not cat_id_input.get('value'):
            st.warning("Could not find category ID, AJAX loading might fail.")
            return all_results
        cat_id = cat_id_input.get('value')
        st.info(f"Found category ID: {cat_id}")

        # Scrape AJAX pages (Category uses /load-more-cat.php)
        page_counter = 12 # Starts at 12 based on JS analysis
        while True:
            st.info(f"Category AJAX: Fetching page with commentNewCount={page_counter}, catid={cat_id}...")
            ajax_data = {'commentNewCount': page_counter, 'catid': cat_id}
            ajax_response = session.post(urljoin(category_url, REALGROUP_CATEGORY_AJAX), data=ajax_data, timeout=TIMEOUT) # Use category_url as base for joining
            ajax_response.raise_for_status()
            ajax_html = ajax_response.text.strip()

            if not ajax_html:
                st.info("Category AJAX: No more content.")
                break

            _, ajax_intermediates = extract_rgl_links(ajax_html, category_url) # Use category_url as base
            if not ajax_intermediates:
                st.info("Category AJAX: No new links found, stopping.")
                break

            all_results.extend([{"Type": "Intermediate (Category AJAX)", "Source": f"AJAX (commentNewCount={page_counter}, catid={cat_id})", "Link": link} for link in ajax_intermediates])
            st.info(f"Category AJAX: Found {len(ajax_intermediates)} links.")
            page_counter += 12 # Increments by 12 (page size)
            time.sleep(0.5)

    except requests.exceptions.RequestException as e:
        st.error(f"Error scraping RGL category {category_url}: {e}")
    except Exception as e:
        st.error(f"Unexpected error scraping RGL category {category_url}: {e}")
    return all_results

def scrape_gs_search(keyword, session):
    """Scrapes GroupSor search results."""
    all_results = []
    base_url = GROUPSOR_BASE_URL
    try:
        # Initial search request to get cookies/headers context if needed (might not be strictly necessary)
        search_url = f"{base_url}{GROUPSOR_SEARCH_PAGE}?keyword={keyword}"
        st.info(f"Initiating GroupSor search for: {keyword}")
        session.get(search_url, timeout=TIMEOUT) # Might help set up session

        page_counter = 0 # Starts at 0 based on JS
        while True:
            st.info(f"GroupSor Search AJAX: Fetching page {page_counter} for keyword '{keyword}'...")
            ajax_data = {'group_no': page_counter, 'keyword': keyword}
            # Add referer header
            headers = {'Referer': search_url}
            ajax_response = session.post(urljoin(base_url, GROUPSOR_SEARCH_AJAX), data=ajax_data, headers=headers, timeout=TIMEOUT)
            ajax_response.raise_for_status()
            ajax_html = ajax_response.text.strip()

            # Check for end condition (specific string found in provided file)
            if not ajax_html or "<div id=\"no\" style=\"display: none;color: #555\">No More groups</div>" in ajax_html:
                st.info("GroupSor Search AJAX: No more content or end marker found.")
                break

            soup = BeautifulSoup(ajax_html, 'html.parser')
            join_links = []
            join_link_tags = soup.find_all('a', href=re.compile(r'/group/join/[A-Za-z0-9]+'))
            for tag in join_link_tags:
                href = tag.get('href')
                if href:
                    full_url = urljoin(base_url, href)
                    join_links.append(full_url)

            if not join_links:
                st.info("GroupSor Search AJAX: No new join links found, stopping.")
                break

            all_results.extend([{"Type": "Intermediate (GroupSor Join Link)", "Source": f"Search AJAX (Page {page_counter})", "Link": link} for link in join_links])
            st.info(f"GroupSor Search AJAX: Found {len(join_links)} join links.")
            page_counter += 1 # Increments by 1
            time.sleep(0.5)

    except requests.exceptions.RequestException as e:
        st.error(f"Error scraping GroupSor search for '{keyword}': {e}")
    except Exception as e:
        st.error(f"Unexpected error scraping GroupSor search for '{keyword}': {e}")
    return all_results


def resolve_intermediate_links(results, session, competitor):
    """Resolves intermediate links to final WhatsApp URLs."""
    if not results:
        return results

    intermediate_results = [r for r in results if 'Intermediate' in r['Type']]
    if not intermediate_results:
        st.info("No intermediate links to resolve.")
        return results

    resolved_results = []
    failed_count = 0
    progress_bar = st.progress(0)
    total_intermediates = len(intermediate_results)

    for i, result in enumerate(intermediate_results):
        intermediate_link = result['Link']
        st.info(f"Resolving ({i+1}/{total_intermediates}): {intermediate_link}")
        final_url = None

        if competitor == "RealGroupLinks.com":
            final_url = get_final_whatsapp_url_rgl(intermediate_link, session)
        elif competitor == "GroupSor.link":
            final_url = get_final_whatsapp_url_gs(intermediate_link, session)

        if final_url and final_url.startswith("http"):
            resolved_results.append({"Type": "Final (Resolved)", "Source": intermediate_link, "Link": final_url})
        else:
            resolved_results.append({"Type": "Final (Failed/Not Found)", "Source": intermediate_link, "Link": final_url or "ERROR"})
            failed_count += 1

        progress_bar.progress((i + 1) / total_intermediates)
        time.sleep(0.1) # Small delay

    progress_bar.empty()
    st.info(f"Finished resolving. Success: {len(intermediate_results) - failed_count}, Failed: {failed_count}")
    # Combine non-intermediate original results with resolved ones
    non_intermediate_results = [r for r in results if 'Intermediate' not in r['Type']]
    return non_intermediate_results + resolved_results

# --- Streamlit App ---

def main():
    st.set_page_config(page_title="WhatsApp Group Scraper", page_icon="🔍")
    st.title("🔍 WhatsApp Group Scraper (RGL & GroupSor)")
    st.markdown("Scrapes group links using `requests` and `BeautifulSoup4`.")

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

    # --- Session State for Results ---
    if 'scraped_data' not in st.session_state:
        st.session_state.scraped_data = []

    # --- Scrape Button ---
    if st.button("Start Scraping"):
        st.session_state.scraped_data = [] # Clear previous results
        # Create a session for connection pooling and potentially handling cookies
        session = requests.Session()
        # Set a common user agent
        session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'})

        try:
            if competitor == "RealGroupLinks.com":
                if target == "Homepage":
                    st.session_state.scraped_data = scrape_rgl_homepage(REALGROUP_BASE_URL, session)
                elif target == "Specific Category":
                    if not category_path:
                        st.error("Please enter a category path.")
                        return
                    full_category_url = urljoin(REALGROUP_BASE_URL, category_path)
                    st.session_state.scraped_data = scrape_rgl_category(full_category_url, session)

            elif competitor == "GroupSor.link":
                if target == "Search by Keyword":
                    if not search_keyword.strip():
                        st.error("Please enter a search keyword.")
                        return
                    st.session_state.scraped_data = scrape_gs_search(search_keyword.strip(), session)

            # --- Resolve Intermediate Links ---
            if resolve_intermediates and st.session_state.scraped_data:
                st.subheader("Resolving Intermediate Links...")
                st.session_state.scraped_data = resolve_intermediate_links(st.session_state.scraped_data, session, competitor)

            # Deduplicate final results
            if st.session_state.scraped_data:
                 unique_results_set = set((item['Type'], item['Source'], item['Link']) for item in st.session_state.scraped_data)
                 st.session_state.scraped_data = [{"Type": item[0], "Source": item[1], "Link": item[2]} for item in unique_results_set]
                 st.success(f"Scraping finished! Found {len(st.session_state.scraped_data)} unique items.")

        except Exception as e:
            logger.error(f"An unexpected error occurred: {e}", exc_info=True)
            st.error(f"An unexpected error occurred: {e}")
        finally:
            session.close()

    # --- Display Results ---
    if st.session_state.scraped_data:
        st.subheader("Scraped Data")
        df = pd.DataFrame(st.session_state.scraped_data)
        st.dataframe(df)

        # CSV Download
        csv_buffer = io.StringIO()
        df.to_csv(csv_buffer, index=False)
        csv_data = csv_buffer.getvalue()
        csv_buffer.close()

        st.download_button(
            label="Download CSV",
            data=csv_data,
            file_name='scraped_whatsapp_links.csv',
            mime='text/csv',
        )
    else:
        st.info("Click 'Start Scraping' to begin.")

if __name__ == "__main__":
    main()
