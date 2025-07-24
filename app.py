# app.py
import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
import time
import logging
from urllib.parse import urljoin, urlparse

# --- Configuration ---
DEFAULT_BASE_URL = "https://realgrouplinks.com"
AJAX_ENDPOINT = "/load-more-cat.php" # Homepage uses /more-groups.php
HOMEPAGE_AJAX_ENDPOINT = "/more-groups.php"
TIMEOUT = 15  # Timeout for requests (seconds)
AJAX_PAGE_SIZE = 12 # Estimate from the JS, adjust if needed
DEFAULT_CAT_ID = 34 # Fallback category ID
# --- End Configuration ---

# Configure logging (Streamlit shows logs if needed)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Helper Functions ---

def get_final_whatsapp_url_bs4(group_php_url):
    """Fetches the intermediate page and extracts the final WhatsApp URL from JS."""
    logger.info(f"Fetching intermediate page: {group_php_url}")
    try:
        response = requests.get(group_php_url, timeout=TIMEOUT)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')

        # Look for the script tag containing the redirect
        # Pattern: setTimeout(function(){window.location.href = 'THE_URL';}, 7000);
        # Pattern from file: setTimeout(function(){window.location.href = 'THE_URL';}, 7000);
        script_tags = soup.find_all('script')
        for script_tag in script_tags:
            script_content = script_tag.string
            if script_content:
                # Use regex to find the URL within setTimeout
                # Make regex slightly more flexible for variations
                match = re.search(r"setTimeout\s*\(.*?window\.location\.href\s*=\s*['\"](https?://chat\.whatsapp\.com/[^'\"]*)['\"]", script_content, re.DOTALL | re.IGNORECASE)
                if match:
                    final_url = match.group(1)
                    logger.info(f"Found final URL in JS: {final_url}")
                    return final_url

        logger.warning(f"Final URL not found in JS on {group_php_url}")
        return None # Or return group_php_url if you want to keep the intermediate link

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

    # --- 1. Find Direct WhatsApp Links ---
    direct_link_tags = soup.find_all('a', href=re.compile(r'chat\.whatsapp\.com'))
    for tag in direct_link_tags:
        href = tag.get('href')
        if href:
            # Basic validation
            parsed_url = urlparse(href)
            if parsed_url.scheme and parsed_url.netloc and 'chat.whatsapp.com' in parsed_url.netloc:
                direct_links.add(href)

    # --- 2. Find Intermediate group.php Links ---
    # Look for onclick attributes containing 'group.php?id='
    # Example: onclick="singlegroup('https://realgrouplinks.com/group.php?id=775164',...
    # Also check href="#groupsingle" for confirmation, but onclick is key
    potential_intermediate_tags = soup.find_all('a', onclick=re.compile(r'group\.php\?id='))
    for tag in potential_intermediate_tags:
        onclick_attr = tag.get('onclick')
        if onclick_attr:
            # Extract URL from onclick, e.g., singlegroup('THE_URL',...
            # Make regex more robust to handle potential variations or extra quotes
            match = re.search(r"singlegroup\(\s*['\"]([^'\"]*group\.php\?id=\d+)['\"]", onclick_attr)
            if match:
                relative_or_absolute_url = match.group(1)
                full_url = urljoin(base_url, relative_or_absolute_url)
                intermediate_links.add(full_url)

    logger.info(f"Extracted {len(direct_links)} direct links and {len(intermediate_links)} intermediate links.")
    return list(direct_links), list(intermediate_links)

def scrape_category_via_ajax(base_url, cat_id):
    """Scrapes ALL group links for a category by calling the AJAX endpoint repeatedly."""
    all_group_php_links = []
    ajax_url = urljoin(base_url, AJAX_ENDPOINT.lstrip('/')) # Ensure correct URL joining

    status_placeholder = st.empty()
    progress_placeholder = st.empty() # For dynamic updates without progress bar

    page = 1
    while True: # Loop until no more data
        comment_new_count = page * AJAX_PAGE_SIZE
        data = {
            'commentNewCount': comment_new_count,
            'catid': cat_id
        }
        logger.info(f"Fetching AJAX page {page} for category {cat_id} with data {data}")
        status_placeholder.info(f"🔄 Fetching AJAX page {page} for category ID {cat_id}...")

        try:
            response = requests.post(ajax_url, data=data, timeout=TIMEOUT)
            response.raise_for_status()
            html_content = response.text.strip()

            if not html_content or html_content == "":
                logger.info(f"No more content on AJAX page {page}. Stopping.")
                status_placeholder.info(f"✅ Finished AJAX scraping for category {cat_id}. No more groups found on page {page}.")
                break # No more data

            # Parse the returned HTML snippet for group links
            _, ajax_links_on_page = extract_links_from_html(html_content, base_url)
            # Filter to ensure they are group.php links (extra safety)
            ajax_links_on_page = [link for link in ajax_links_on_page if 'group.php?id=' in link]

            if not ajax_links_on_page:
                 logger.info(f"No new group links found in AJAX response for page {page}. Stopping.")
                 status_placeholder.info(f"⚠️ No new group links on AJAX page {page}. Stopping.")
                 break # Likely no more links

            new_links_count = len(ajax_links_on_page)
            all_group_php_links.extend(ajax_links_on_page)
            total_links_so_far = len(all_group_php_links)
            logger.info(f"Found {new_links_count} links on AJAX page {page}. Total: {total_links_so_far}")
            progress_placeholder.info(f"📄 Page {page}: Found {new_links_count} links. Total: {total_links_so_far}")
            # status_placeholder.info(f"Found {new_links_count} links on AJAX page {page}.")

            page += 1 # Increment for next page

            # Optional: Add a small delay between requests to be respectful
            time.sleep(0.5)

        except requests.exceptions.Timeout:
            logger.error(f"Timeout error fetching AJAX page {page} for category {cat_id}. Stopping.")
            status_placeholder.warning(f"⏰ Timeout fetching AJAX page {page}. Stopping scraping for this category.")
            break # Stop on timeout
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching AJAX page {page} for category {cat_id}: {e}")
            status_placeholder.warning(f"❌ Error fetching AJAX page {page}: {e}. Stopping.")
            break # Stop on other request errors
        except Exception as e:
             logger.error(f"Unexpected error during AJAX scraping page {page}: {e}")
             status_placeholder.warning(f"💥 Unexpected error on AJAX page {page}: {e}. Stopping.")
             break

    # progress_placeholder.empty() # Clear the dynamic progress text
    logger.info(f"Total group links found via AJAX for category {cat_id}: {len(all_group_php_links)}")
    return all_group_php_links

def scrape_homepage_via_ajax(base_url):
    """Scrapes ALL group links from the homepage by calling its AJAX endpoint repeatedly."""
    all_group_php_links = []
    ajax_url = urljoin(base_url, HOMEPAGE_AJAX_ENDPOINT.lstrip('/'))

    status_placeholder = st.empty()
    progress_placeholder = st.empty()

    page = 1
    while True:
        comment_new_count = 16 + (page - 1) * 8 # Starts at 16, increments by 8 (from JS)
        data = {
            'commentNewCount': comment_new_count
        }
        logger.info(f"Fetching Homepage AJAX page {page} with data {data}")
        status_placeholder.info(f"🔄 Fetching Homepage AJAX page {page}...")

        try:
            response = requests.post(ajax_url, data=data, timeout=TIMEOUT)
            response.raise_for_status()
            html_content = response.text.strip()

            if not html_content or html_content == "":
                logger.info(f"No more content on Homepage AJAX page {page}. Stopping.")
                status_placeholder.info(f"✅ Finished AJAX scraping homepage. No more groups found on page {page}.")
                break

            _, ajax_links_on_page = extract_links_from_html(html_content, base_url)
            ajax_links_on_page = [link for link in ajax_links_on_page if 'group.php?id=' in link]

            if not ajax_links_on_page:
                 logger.info(f"No new group links found in Homepage AJAX response for page {page}. Stopping.")
                 status_placeholder.info(f"⚠️ No new group links on Homepage AJAX page {page}. Stopping.")
                 break

            new_links_count = len(ajax_links_on_page)
            all_group_php_links.extend(ajax_links_on_page)
            total_links_so_far = len(all_group_php_links)
            logger.info(f"Found {new_links_count} links on Homepage AJAX page {page}. Total: {total_links_so_far}")
            progress_placeholder.info(f"📄 Page {page}: Found {new_links_count} links. Total: {total_links_so_far}")

            page += 1
            time.sleep(0.5)

        except requests.exceptions.Timeout:
            logger.error(f"Timeout error fetching Homepage AJAX page {page}. Stopping.")
            status_placeholder.warning(f"⏰ Timeout fetching Homepage AJAX page {page}. Stopping.")
            break
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching Homepage AJAX page {page}: {e}")
            status_placeholder.warning(f"❌ Error fetching Homepage AJAX page {page}: {e}. Stopping.")
            break
        except Exception as e:
             logger.error(f"Unexpected error during Homepage AJAX scraping page {page}: {e}")
             status_placeholder.warning(f"💥 Unexpected error on Homepage AJAX page {page}: {e}. Stopping.")
             break

    logger.info(f"Total group links found via Homepage AJAX: {len(all_group_php_links)}")
    return all_group_php_links


def scrape_page_bs4(url):
    """Scrapes a single page (homepage or category) for initial links."""
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

def get_category_id(html_content):
    """Attempts to extract the category ID from the page's HTML."""
    soup = BeautifulSoup(html_content, 'html.parser')
    try:
        # Look for hidden input with id 'catid'
        cat_id_element = soup.find('input', {'id': 'catid'})
        if cat_id_element and cat_id_element.get('value'):
            return int(cat_id_element.get('value'))
    except (ValueError, TypeError) as e:
        logger.warning(f"Error parsing category ID from HTML: {e}")
    return DEFAULT_CAT_ID # Fallback

# --- Streamlit App ---

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
    """)

    # --- Input Configuration ---
    st.sidebar.header("Configuration")
    # 1. Allow editing Base URL
    base_url = st.sidebar.text_input("Base URL", value=DEFAULT_BASE_URL)

    option = st.sidebar.selectbox("Scraping Target", ("Homepage", "Specific Category (w/ AJAX)"))

    category_path = ""
    if option == "Specific Category (w/ AJAX)":
        category_path = st.sidebar.text_input("Enter category path (e.g., /category/tamil/):", value="/category/tamil/")

    resolve_intermediates = st.sidebar.checkbox("Resolve Intermediate Links", value=True)
    st.sidebar.markdown("---")
    st.sidebar.markdown("**Note:** Scraping involves multiple HTTP requests. Unlimited scraping might take a long time.")

    all_results = []

    if st.button("Start Scraping"):
        if not base_url:
             st.error("Please enter a Base URL.")
             return
        try:
            if option == "Homepage":
                with st.spinner("Scraping Initial Homepage Content..."):
                    direct_links, intermediate_links = scrape_page_bs4(base_url)
                    initial_count = len(direct_links) + len(intermediate_links)
                    all_results.extend([{"Type": "Direct", "Source": base_url, "Link": link} for link in direct_links])
                    all_results.extend([{"Type": "Intermediate", "Source": base_url, "Link": link} for link in intermediate_links])
                    st.info(f"Found {initial_count} initial links on the homepage.")

                # Scrape additional links via AJAX (unlimited)
                st.subheader("Loading More Homepage Groups via AJAX...")
                ajax_links = scrape_homepage_via_ajax(base_url)
                all_results.extend([{"Type": "Intermediate (AJAX)", "Source": f"AJAX (Homepage)", "Link": link} for link in ajax_links])


            elif option == "Specific Category (w/ AJAX)":
                if not category_path:
                    st.warning("Please enter a category path.")
                    return
                category_url = urljoin(base_url, category_path)
                with st.spinner(f"Scraping Initial Category Page Content: {category_url}"):
                    # 1. Get initial links and category ID
                    try:
                        response = requests.get(category_url, timeout=TIMEOUT)
                        response.raise_for_status()
                        initial_html = response.text
                        initial_direct_links, initial_intermediate_links = extract_links_from_html(initial_html, category_url)
                        initial_count = len(initial_direct_links) + len(initial_intermediate_links)
                        all_results.extend([{"Type": "Direct", "Source": category_url, "Link": link} for link in initial_direct_links])
                        all_results.extend([{"Type": "Intermediate", "Source": category_url, "Link": link} for link in initial_intermediate_links])
                        st.info(f"Found {initial_count} initial links on the category page.")

                        # 2. Get Category ID for AJAX
                        cat_id = get_category_id(initial_html)
                        st.info(f"Found category ID: {cat_id}")

                        # 3. Scrape ALL remaining links via AJAX
                        st.subheader("Loading More Category Groups via AJAX (Unlimited)...")
                        ajax_links = scrape_category_via_ajax(base_url, cat_id)
                        all_results.extend([{"Type": "Intermediate (AJAX)", "Source": f"AJAX (Cat {cat_id})", "Link": link} for link in ajax_links])

                    except requests.exceptions.RequestException as e:
                        st.error(f"Error fetching category page {category_url}: {e}")
                        return
                    except Exception as e:
                        st.error(f"Error processing category page {category_url}: {e}")
                        return

            # --- Deduplicate Results ---
            # It's possible the same intermediate link is found on the initial page and via AJAX
            # Using a set of tuples to represent unique entries
            unique_results_set = set((item['Type'], item['Source'], item['Link']) for item in all_results)
            # Convert back to list of dicts
            unique_all_results = [{"Type": item[0], "Source": item[1], "Link": item[2]} for item in unique_results_set]
            all_results = unique_all_results
            st.success(f"✅ Scraping completed. Total unique links found before resolving: {len(all_results)}")


            # --- Process Intermediate Links ---
            if resolve_intermediates:
                intermediate_results = [r for r in all_results if 'Intermediate' in r['Type']]
                if intermediate_results:
                    st.subheader("Resolving Intermediate Links")
                    status_placeholder = st.empty()
                    progress_bar = st.progress(0)
                    final_results = []
                    total_intermediates = len(intermediate_results)

                    for i, result in enumerate(intermediate_results):
                        intermediate_link = result['Link']
                        status_placeholder.info(f"🔗 Resolving {i+1}/{total_intermediates}: {intermediate_link}")
                        final_url = get_final_whatsapp_url_bs4(intermediate_link)
                        if final_url:
                            final_results.append({"Type": "Final (from Intermediate)", "Source": intermediate_link, "Link": final_url})
                        else:
                            final_results.append({"Type": "Final (FAILED/Not Found)", "Source": intermediate_link, "Link": "ERROR"})
                        progress_bar.progress((i + 1) / total_intermediates)
                        # Small delay to prevent overwhelming the server
                        time.sleep(0.1)

                    progress_bar.empty()
                    status_placeholder.success("✅ Finished resolving intermediate links.")
                    # Add final results to overall list, replacing original intermediates
                    non_intermediate_results = [r for r in all_results if 'Intermediate' not in r['Type']]
                    all_results = non_intermediate_results + final_results

            # --- Display Results ---
            if all_results:
                df = st.dataframe(all_results)
                # Create CSV data
                csv_lines = ["Type,Source,Link"] # Header
                csv_lines.extend([f"{item['Type']},{item['Source']},{item['Link']}" for item in all_results])
                csv_data = "\n".join(csv_lines)

                st.download_button(
                    label="💾 Download CSV",
                    data=csv_data,
                    file_name='realgrouplinks_scraped_data.csv',
                    mime='text/csv',
                )
                st.success(f"🎉 Scraping process finished! Total items in final output: {len(all_results)}.")
            else:
                st.info("ℹ️ No links were found.")

        except Exception as e:
            logger.error(f"An unexpected error occurred in the main app logic: {e}", exc_info=True)
            st.error(f"💥 An unexpected error occurred: {e}")


if __name__ == "__main__":
    main()
