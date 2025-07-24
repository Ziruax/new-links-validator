import streamlit as st
import pandas as pd
import requests
import html
from bs4 import BeautifulSoup
import re
import time
import io
from urllib.parse import urljoin, urlparse, urlencode, parse_qs
from concurrent.futures import ThreadPoolExecutor, as_completed
# --- Import Google Search Library ---
try:
    from googlesearch import search as google_search_function_actual
except ImportError:
    st.error("The `googlesearch-python` library is not installed. Please install it: `pip install googlesearch-python`")
    def google_search_function_actual(query, num_results, lang, **kwargs):
        st.error("`googlesearch-python` library not found. Cannot perform Google searches.")
        return []
# --- Import Fake User Agent Library ---
try:
    from fake_useragent import UserAgent
    from fake_useragent.errors import FakeUserAgentError
    ua_general = UserAgent()
    def get_random_headers_general():
        try:
            return {
                "User-Agent": ua_general.random,
                "Accept-Language": "en-US,en;q=0.9"
            }
        except FakeUserAgentError:
            st.warning("fake-useragent failed to get a User-Agent. Using fallback.", icon="⚠️")
            return {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9"
            }
        except Exception as e_random:
            st.warning(f"Error getting random User-Agent: {e_random}. Using fallback.", icon="⚠️")
            return {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9"
            }
except ImportError:
    st.warning("`fake-useragent` library not found. Install with `pip install fake-useragent`. Using default User-Agent.", icon="⚠️")
    def get_random_headers_general():
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9"
        }
except FakeUserAgentError as e_init:
    st.warning(f"Error initializing fake-useragent: {e_init}. Using default User-Agent.", icon="⚠️")
    def get_random_headers_general():
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9"
        }
except Exception as e_general_init:
    st.warning(f"Error initializing fake-useragent: {e_general_init}. Using default User-Agent.", icon="⚠️")
    def get_random_headers_general():
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9"
        }

# --- Streamlit Configuration & Constants ---
st.set_page_config(
    page_title="WhatsApp Link Scraper & Validator",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)
WHATSAPP_DOMAIN = "https://chat.whatsapp.com/"
UNNAMED_GROUP_PLACEHOLDER = ""  # Changed to empty string
IMAGE_PATTERN_PPS = re.compile(r'https:\/\/pps\.whatsapp\.net\/v\/t\d+\/[-\w]+\/\d+\.jpg\?')
OG_IMAGE_PATTERN = re.compile(r'https?:\/\/[^\/\s]+\/[^\/\s]+\.(jpg|jpeg|png)(\?[^\s]*)?')
MAX_VALIDATION_WORKERS = 8
MAX_SCRAPING_WORKERS = 5 # New: For concurrent scraping tasks (Google, Bulk URLs, internal crawl scraping)
# --- Custom CSS ---
st.markdown("""
<style>
body { font-family: 'Arial', sans-serif; }
.main-title { font-size: 2.8em; color: #25D366; text-align: center; margin-bottom: 0; font-weight: 600; letter-spacing: -1px; }
.subtitle { font-size: 1.3em; color: #555; text-align: center; margin-top: 5px; margin-bottom: 30px; }
.stButton>button { background-color: #25D366; color: #FFFFFF; border-radius: 8px; font-weight: bold; border: none; padding: 10px 18px; margin: 8px 0; transition: background-color 0.3s ease, transform 0.1s ease; }
.stButton>button:hover { background-color: #1EBE5A; transform: scale(1.03); }
.stButton>button:active { transform: scale(0.98); }
.stProgress > div > div > div > div { background-color: #25D366; border-radius: 4px; }
.metric-card { background-color: #F8F9FA; padding: 15px; border-radius: 10px; box-shadow: 0 4px 8px rgba(0,0,0,0.05); color: #333; text-align: center; margin-bottom: 15px; border: 1px solid #E9ECEF; }
.metric-card .metric-value { font-size: 2em; font-weight: 700; margin-top: 5px; margin-bottom: 0; line-height: 1.2; color: #25D366; }
.stTextInput > div > div > input, .stTextArea > div > textarea, .stNumberInput > div > div > input { border: 1px solid #CED4DA !important; border-radius: 6px !important; padding: 10px !important; box-shadow: inset 0 1px 2px rgba(0,0,0,0.075); }
.stTextInput > div > div > input:focus, .stTextArea > div > textarea:focus, .stNumberInput > div > div > input:focus { border-color: #25D366 !important; box-shadow: 0 0 0 0.2rem rgba(37, 211, 102, 0.25) !important; }
.st-emotion-cache-1v3rj08, .st-emotion-cache-gh2jqd, .streamlit-expanderHeader { background-color: #F8F9FA; border-radius: 6px; }
.stExpander { border: 1px solid #E9ECEF; border-radius: 8px; padding: 12px; margin-top: 15px; margin-bottom: 15px; box-shadow: 0 2px 4px rgba(0,0,0,0.03); }
.stExpander div[data-testid="stExpanderToggleIcon"] { color: #25D366; font-size: 1.2em; }
.stExpander div[data-testid="stExpanderLabel"] strong { color: #1EBE5A; font-size: 1.1em; }
.filter-container { background-color: #FDFDFD; padding: 15px; border-radius: 8px; margin-bottom: 20px; border: 1px dashed #DDE2E5; }
.filter-container .stTextInput input, .filter-container .stNumberInput input { background-color: #fff;zczy}
h4 { color: #259952; margin-top:10px; margin-bottom:10px; border-left: 3px solid #25D366; padding-left: 8px;}
.whatsapp-groups-table { border-collapse: collapse; width: 100%; margin-top: 15px; box-shadow: 0 3px 6px rgba(0,0,0,0.08); border-radius: 8px; overflow: hidden; border: 1px solid #DEE2E6; }
.whatsapp-groups-table caption { caption-side: top; text-align: left; font-weight: 600; padding: 12px 15px; font-size: 1.15em; color: #343A40; background-color: #F8F9FA; border-bottom: 1px solid #DEE2E6;}
.whatsapp-groups-table th { background-color: #343A40; color: white; padding: 14px 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; font-size: 0.9em; }
.whatsapp-groups-table th:nth-child(1) { text-align: center; width: 80px; }
.whatsapp-groups-table th:nth-child(2) { text-align: left; }
.whatsapp-groups-table th:nth-child(3) { text-align: right; width: 150px; }
.whatsapp-groups-table tr { border-bottom: 1px solid #EAEEF2; }
.whatsapp-groups-table tr:last-child { border-bottom: none; }
.whatsapp-groups-table tr:nth-child(even) { background-color: #F9FAFB; }
.whatsapp-groups-table tr:hover { background-color: #EFF8FF; }
.whatsapp-groups-table td { padding: 12px; vertical-align: middle; text-align: left; font-size: 0.95em; }
.whatsapp-groups-table td:nth-child(1) { width: 60px; padding-right: 8px; text-align: center; }
.whatsapp-groups-table td:nth-child(2) { padding-left: 8px; padding-right: 12px; word-break: break-word; font-weight: 500; color: #212529; }
.whatsapp-groups-table td:nth-child(3) { width: 140px; text-align: right; padding-left: 12px; }
.group-logo-img { width: 45px; height: 45px; border-radius: 50%; object-fit: cover; display: block; margin: 0 auto; border: 2px solid #F0F0F0; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
.join-button { display: inline-block; background-color: #25D366; color: #FFFFFF !important; padding: 7px 14px; border-radius: 6px; text-decoration: none; font-weight: 500; text-align: center; white-space: nowrap; font-size: 0.85em; transition: background-color 0.2s ease, transform 0.1s ease; }
.join-button:hover { background-color: #1DB954; color: #FFFFFF !important; text-decoration: none; transform: translateY(-1px); }
</style>
""", unsafe_allow_html=True)

# --- Helper Functions ---
def append_query_param(url, param_name, param_value):
    if not url: return ""
    parsed_url = urlparse(url)
    query_params = parse_qs(parsed_url.query)
    query_params[param_name] = [param_value]
    new_query_string = urlencode(query_params, doseq=True)
    url_without_fragment = parsed_url._replace(query=new_query_string, fragment='').geturl()
    return f"{url_without_fragment}#{parsed_url.fragment}" if parsed_url.fragment else url_without_fragment

def load_keywords_from_excel(uploaded_file):
    if uploaded_file is None: return []
    try:
        df = pd.read_excel(io.BytesIO(uploaded_file.getvalue()), engine='openpyxl')
        if df.empty: st.warning("Excel file is empty."); return []
        keywords = [kw.strip() for kw in df.iloc[:, 0].dropna().astype(str).tolist() if len(kw.strip()) > 1]
        if not keywords: st.warning("No valid keywords found in the first column of the Excel file.")
        return keywords
    except Exception as e:
        st.error(f"Error reading Excel: {e}. Ensure 'openpyxl' is installed.", icon="❌")
        return []

def load_links_from_file(uploaded_file):
    """Loads links from TXT/CSV files for validation or bulk scraping."""
    if uploaded_file is None: return []
    try:
        content = uploaded_file.getvalue()
        text_content = None
        for encoding in ['utf-8', 'latin-1', 'cp1252']:
            try:
                text_content = content.decode(encoding)
                st.sidebar.info(f"Decoded file with {encoding}.")
                break
            except UnicodeDecodeError: continue
        if text_content is None:
            st.error(f"Could not decode file {uploaded_file.name}.", icon="❌"); return []
        if uploaded_file.name.endswith('.csv'):
            try:
                df = pd.read_csv(io.StringIO(text_content))
                if df.empty: st.warning("CSV file is empty."); return []
                # Assume links are in the first column
                return [link.strip() for link in df.iloc[:, 0].dropna().astype(str).tolist() if link.strip().startswith(('http://', 'https://'))]
            except Exception as e:
                st.error(f"Error reading CSV: {e}.", icon="❌"); return []
        else: # Assume TXT - one link per line
            return [line.strip() for line in text_content.splitlines() if line.strip().startswith(('http://', 'https://'))]
    except Exception as e:
        st.error(f"Error processing file {uploaded_file.name}: {e}", icon="❌"); return []

# --- Core Logic Functions ---

# --- Updated scrape_whatsapp_links_from_page function ---
def scrape_whatsapp_links_from_page(url, session=None, wait_for_dynamic=False, wait_time_seconds=5):
    """Scrapes a single page for WhatsApp links. Optionally waits for dynamic content."""
    links = set()
    
    def _extract_links_from_response(response):
        """Helper to extract links from a response object."""
        soup = BeautifulSoup(response.text, 'html.parser')
        # Method 1: Find <a> tags with href
        for a_tag in soup.find_all('a', href=True):
            href = a_tag.get('href')
            if href and href.startswith(WHATSAPP_DOMAIN):
                parsed_url = urlparse(href)
                links.add(f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}")
        # Method 2: Search text content for potential links
        text_content = soup.get_text()
        if WHATSAPP_DOMAIN in text_content:
            for link_url in re.findall(r'(https?://chat\.whatsapp\.com/[^\s"\'<>()\[\]{}]+)', text_content):
                clean_link = re.sub(r'[.,;!?"\'<>)]+$', '', link_url)
                clean_link = re.sub(r'(\.[a-zA-Z]{2,4})$', '', clean_link) if not clean_link.endswith(('.html', '.htm', '.php')) else clean_link
                clean_link = clean_link.split('&')[0] # Often query params are not needed for WA links
                parsed_url = urlparse(clean_link)
                if len(parsed_url.path.replace('/', '')) > 15: # Basic sanity check for WA invite ID
                    links.add(f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}")

    try:
        headers = get_random_headers_general()
        response = session.get(url, headers=headers, timeout=15) if session else requests.get(url, headers=headers, timeout=15)
        response.encoding = 'utf-8'
        response.raise_for_status()
        
        # Extract links from the initial response
        _extract_links_from_response(response)
        st.sidebar.info(f"Initial scrape of {url[:50]}... found {len(links)} links.")

        # --- Logic for waiting for dynamic content ---
        if wait_for_dynamic:
            # Heuristic: Check if the initial response contains simple timer logic
            # This is not foolproof but a lightweight check.
            # A more robust check would be to look for specific JS functions or AJAX calls,
            # which is much harder without a full JS engine.
            initial_text_lower = response.text.lower()
            
            # Simple check for setTimeout related to showing content or links
            # (This is a basic example, real-world logic might be more complex)
            timer_indicators = [
                'settimeout', # Common JS timer function
                # Add more specific patterns if you know common ones on target sites
                # e.g., r'setTimeout.*?display.*?chat\.whatsapp\.com'
            ]
            timer_detected = any(indicator in initial_text_lower for indicator in timer_indicators)

            if timer_detected or True: # Always wait if enabled for now, as detection is basic
                st.sidebar.info(f"Waiting {wait_time_seconds}s for dynamic content on {url[:50]}...")
                time.sleep(wait_time_seconds)
                
                # Fetch the page again after waiting
                try:
                    response_after_wait = session.get(url, headers=headers, timeout=15) if session else requests.get(url, headers=headers, timeout=15)
                    response_after_wait.encoding = 'utf-8'
                    response_after_wait.raise_for_status()
                    
                    # Extract links from the response after waiting
                    initial_link_count = len(links)
                    _extract_links_from_response(response_after_wait)
                    new_links_count = len(links) - initial_link_count
                    st.sidebar.info(f"After waiting, scrape of {url[:50]}... found {new_links_count} additional links.")
                except requests.exceptions.RequestException as e_wait:
                    st.sidebar.warning(f"Error fetching after wait for {url[:50]}: {e_wait}", icon="⏱️")
                except Exception as e_wait_parse:
                    st.sidebar.warning(f"Parse error after wait for {url[:50]}: {e_wait_parse}", icon="⏱️")
            else:
                st.sidebar.info(f"No simple timer detected on {url[:50]}... Proceeding without wait.")

    except requests.exceptions.Timeout: st.sidebar.warning(f"Scrape Timeout: {url[:50]}...", icon="⏱️")
    except requests.exceptions.HTTPError as e: st.sidebar.warning(f"Scrape HTTP Err {e.response.status_code}: {url[:50]}...", icon="⚠️")
    except requests.exceptions.RequestException as e: st.sidebar.warning(f"Scrape Net Err ({type(e).__name__}): {url[:50]}...", icon="⚠️")
    except Exception as e: st.sidebar.warning(f"Scrape Parse Err ({type(e).__name__}): {url[:50]}...", icon="💣")
    return list(links)

# --- Google Search Scraper (Updated for concurrency and dynamic wait) ---
def scrape_single_google_result_page(url_from_google, wait_for_dynamic=False, wait_time_seconds=5):
    """Wrapper for scraping a single Google result page, used by ThreadPoolExecutor."""
    try:
        # Each thread gets its own session for connection pooling within that thread
        with requests.Session() as session:
            wa_links_from_page = scrape_whatsapp_links_from_page(url_from_google, session=session, wait_for_dynamic=wait_for_dynamic, wait_time_seconds=wait_time_seconds)
            return url_from_google, wa_links_from_page
    except Exception as e:
        st.sidebar.warning(f"Thread Error scraping {url_from_google[:50]}: {e}", icon="🧵")
        return url_from_google, []

def google_search_and_scrape(query, top_n=5, wait_for_dynamic=False, wait_time_seconds=5):
    """Performs Google search and scrapes multiple result pages concurrently."""
    st.info(f"Googling '{query}' (top {top_n} results)...")
    all_scraped_wa_links = set()
    try:
        search_page_urls = list(google_search_function_actual(query, num_results=top_n, lang="en"))
        if not search_page_urls:
            st.warning(f"No Google results for '{query}'. Possible reasons: "
                       f"1. Query yields no results. "
                       f"2. Google blocking (try VPN/wait). "
                       f"3. `googlesearch-python` library issue.", icon="🤔")
            return []
        st.success(f"Found {len(search_page_urls)} pages from Google. Scraping them concurrently for WhatsApp links...")
        prog_bar, stat_txt = st.progress(0), st.empty()
        successfully_processed = 0
        # Concurrently scrape the Google result pages
        with ThreadPoolExecutor(max_workers=MAX_SCRAPING_WORKERS) as executor:
            # Submit all scraping tasks
            future_to_url = {executor.submit(scrape_single_google_result_page, url, wait_for_dynamic, wait_time_seconds): url for url in search_page_urls}
            # Process completed tasks as they finish
            for i, future in enumerate(as_completed(future_to_url)):
                url_from_google = future_to_url[future]
                try:
                    url_processed, wa_links_from_page = future.result()
                    newly_found_count = 0
                    for link in wa_links_from_page:
                        if link.startswith(WHATSAPP_DOMAIN) and link not in all_scraped_wa_links:
                            all_scraped_wa_links.add(link)
                            newly_found_count += 1
                    if newly_found_count > 0:
                        st.sidebar.info(f"Found {newly_found_count} new WA links on {url_from_google[:30]}...")
                    successfully_processed += 1
                except Exception as e:
                     st.sidebar.warning(f"Error scraping {url_from_google[:50]}: {e}", icon="⚠️")
                prog_bar.progress((i + 1) / len(search_page_urls))
                stat_txt.text(f"Processed {successfully_processed}/{len(search_page_urls)} Google results...")
        stat_txt.success(f"Scraping of Google results complete. Found {len(all_scraped_wa_links)} unique WhatsApp links from '{query}'.")
        return list(all_scraped_wa_links)
    except TypeError as e:
        st.error(f"Google search TypeError: {e}. Check `googlesearch-python` version/parameters.", icon="❌")
        return []
    except Exception as e:
        st.error(f"Unexpected Google search/scrape error for '{query}': {e}. Check connection/library.", icon="❌")
        return []

# --- Bulk URL Scraper (Updated for dynamic wait) ---
def scrape_single_bulk_url(url, wait_for_dynamic=False, wait_time_seconds=5):
    """Wrapper for scraping a single URL from the bulk list, used by ThreadPoolExecutor."""
    try:
        # Each thread gets its own session for connection pooling within that thread
        with requests.Session() as session:
            wa_links_from_page = scrape_whatsapp_links_from_page(url, session=session, wait_for_dynamic=wait_for_dynamic, wait_time_seconds=wait_time_seconds)
            return url, wa_links_from_page
    except Exception as e:
        st.sidebar.warning(f"Bulk Scrape Error for {url[:50]}: {e}", icon="🔗")
        return url, []

def scrape_bulk_urls(list_of_urls, wait_for_dynamic=False, wait_time_seconds=5):
    """Scrapes a list of URLs concurrently."""
    if not list_of_urls:
        st.warning("No URLs provided for bulk scraping.")
        return set()
    st.info(f"Starting bulk scrape of {len(list_of_urls)} URLs...")
    all_scraped_wa_links = set()
    prog_bar, stat_txt = st.progress(0), st.empty()
    successfully_processed = 0
    # Concurrently scrape the URLs
    with ThreadPoolExecutor(max_workers=MAX_SCRAPING_WORKERS) as executor:
        # Submit all scraping tasks
        future_to_url = {executor.submit(scrape_single_bulk_url, url, wait_for_dynamic, wait_time_seconds): url for url in list_of_urls if url.startswith(('http://', 'https://'))}
        # Process completed tasks as they finish
        for i, future in enumerate(as_completed(future_to_url)):
            url_scraped = future_to_url[future]
            try:
                url_processed, wa_links_from_page = future.result()
                newly_found_count = 0
                for link in wa_links_from_page:
                    if link.startswith(WHATSAPP_DOMAIN) and link not in all_scraped_wa_links:
                        all_scraped_wa_links.add(link)
                        newly_found_count += 1
                if newly_found_count > 0:
                    st.sidebar.info(f"Bulk: Found {newly_found_count} new WA links on {url_scraped[:30]}...")
                successfully_processed += 1
            except Exception as e:
                 st.sidebar.warning(f"Error bulk scraping {url_scraped[:50]}: {e}", icon="⚠️")
            prog_bar.progress((i + 1) / len(future_to_url)) # Use len(future_to_url) in case some URLs were filtered
            stat_txt.text(f"Bulk Processed {successfully_processed}/{len(future_to_url)} URLs...")
    stat_txt.success(f"Bulk scraping complete. Found {len(all_scraped_wa_links)} unique WhatsApp links from {len(future_to_url)} URLs.")
    return all_scraped_wa_links

# --- Crawler Logic ---
# Define a thread-safe data structure for the crawler's shared state
from queue import Queue, Empty
import threading
from collections import defaultdict

# --- Thread-Safe Crawler State ---
class ThreadSafeCrawlerState:
    def __init__(self):
        self.lock = threading.Lock()
        self.visited_urls = set()
        self.scraped_whatsapp_links = set()
        self.domain_last_request_time = defaultdict(float) # For politeness per domain
        self.politeness_delay = 1.0 # seconds between requests to the same domain

    def add_visited_url(self, normalized_url):
        with self.lock:
            self.visited_urls.add(normalized_url)

    def is_visited(self, normalized_url):
        with self.lock:
            return normalized_url in self.visited_urls

    def add_scraped_link(self, link):
        with self.lock:
            if link not in self.scraped_whatsapp_links:
                self.scraped_whatsapp_links.add(link)
                return True # Indicating it was new
            return False

    def get_scraped_links(self):
        with self.lock:
            return self.scraped_whatsapp_links.copy()

    def update_last_request_time(self, domain, timestamp):
        with self.lock:
            self.domain_last_request_time[domain] = timestamp

    def get_last_request_time(self, domain):
        with self.lock:
            return self.domain_last_request_time[domain]

# --- Crawler Worker Thread (Updated for dynamic wait) ---
def crawler_worker(thread_id, url_queue, state, base_domain, max_depth, session_factory, stop_event, progress_callback, wait_for_dynamic=False, wait_time_seconds=5):
    """Worker thread function for the crawler."""
    while not stop_event.is_set():
        try:
            # Non-blocking get with timeout to allow checking stop_event
            current_url, depth = url_queue.get(timeout=1)
        except Empty:
            continue # Check stop_event again

        # Check depth limit if it's set (not None)
        if max_depth is not None and depth > max_depth:
            url_queue.task_done()
            continue

        # Normalize URL for visited check
        normalized_current_url = urljoin(current_url, urlparse(current_url).path or '/')

        # Check if already visited (thread-safe)
        if state.is_visited(normalized_current_url):
            url_queue.task_done()
            continue

        # Mark as visited (thread-safe)
        state.add_visited_url(normalized_current_url)

        # Politeness delay per domain
        current_domain = urlparse(current_url).netloc.replace('www.', '')
        last_req_time = state.get_last_request_time(current_domain)
        time_since_last = time.time() - last_req_time
        if time_since_last < state.politeness_delay:
            time.sleep(state.politeness_delay - time_since_last)
        state.update_last_request_time(current_domain, time.time())

        # --- Perform the scraping ---
        try:
            # Get a new session from the factory for this request
            with session_factory() as session:
                # --- Use the updated scraping function with wait option ---
                wa_links_from_page = scrape_whatsapp_links_from_page(current_url, session=session, wait_for_dynamic=wait_for_dynamic, wait_time_seconds=wait_time_seconds)
                # --- End of updated scraping call ---

                newly_found_count = 0
                for link in wa_links_from_page:
                    if link.startswith(WHATSAPP_DOMAIN):
                        # Add link (thread-safe)
                        if state.add_scraped_link(link):
                            newly_found_count += 1
                if newly_found_count > 0:
                    st.sidebar.info(f"T{thread_id}: Found {newly_found_count} new WA links on {current_url[:30]}...")

                progress_callback(thread_id, current_url, depth) # Report progress

                # --- Discover new links to crawl (if within depth limit) ---
                # Only discover new links if depth limit is not reached (or if it's unlimited)
                if max_depth is None or depth < max_depth:
                     # Re-fetch the page content for link discovery if needed, or use the last fetched content
                     # For simplicity, let's re-fetch if waiting was involved, otherwise use the last result
                     # Note: scrape_whatsapp_links_from_page doesn't return the full response/soup
                     # We need to fetch the page content again for parsing links.
                     # This is a limitation of the current design.
                     # A better approach would be to refactor scrape_whatsapp_links_from_page to also return the soup
                     # or make link discovery a separate step.
                     try:
                         response_for_links = session.get(current_url, headers=get_random_headers_general(), timeout=10)
                         response_for_links.raise_for_status()
                         if 'text/html' not in response_for_links.headers.get('Content-Type', '').lower():
                             url_queue.task_done()
                             continue
                         soup = BeautifulSoup(response_for_links.text, 'html.parser')
                         for link_tag in soup.find_all('a', href=True):
                             href = link_tag.get('href')
                             if href:
                                 abs_url = urljoin(current_url, href)
                                 parsed_abs_url = urlparse(abs_url)
                                 # Check if it's an internal link to the same domain
                                 if (parsed_abs_url.scheme in ['http', 'https'] and
                                     parsed_abs_url.netloc.replace('www.', '') == base_domain and
                                     not parsed_abs_url.fragment):
                                     normalized_abs_url = urljoin(abs_url, parsed_abs_url.path or '/')
                                     # Check if already visited or queued (basic check, queue isn't fully thread-safe here without more complexity)
                                     # A more robust crawler might use a separate thread-safe set for 'seen' URLs to add to the queue.
                                     if not state.is_visited(normalized_abs_url):
                                         # Add to queue for other workers
                                         url_queue.put((abs_url, depth + 1))
                     except requests.exceptions.RequestException as e_links:
                         st.sidebar.warning(f"T{thread_id}: Link Discovery Req Err ({type(e_links).__name__}): {current_url[:50]}...", icon="🕸️")
                     except Exception as e_links_parse:
                         st.sidebar.error(f"T{thread_id}: Link Discovery Parse Err ({type(e_links_parse).__name__}): {current_url[:50]}...", icon="💥")

        except requests.exceptions.RequestException as e:
            st.sidebar.warning(f"T{thread_id}: Crawl Req Err ({type(e).__name__}): {current_url[:50]}...", icon="🕸️")
        except Exception as e:
            st.sidebar.error(f"T{thread_id}: Crawl Parse Err ({type(e).__name__}): {current_url[:50]}...", icon="💥")
        finally:
            url_queue.task_done()

def crawl_website(start_url, max_depth=None, max_pages=1000000, wait_for_dynamic=False, wait_time_seconds=5):
    """Crawls a website concurrently using multiple threads.
    Args:
        start_url (str): The initial URL to start crawling from.
        max_depth (int, optional): Maximum depth to crawl. If None, depth is unlimited.
        max_pages (int, optional): Maximum number of pages to crawl. Defaults to 1000000 (effectively unlimited).
        wait_for_dynamic (bool): Whether to wait for dynamic content.
        wait_time_seconds (int): Time to wait if waiting for dynamic content.
    Returns:
        set: A set of unique WhatsApp links found during the crawl.
    """
    scraped_whatsapp_links = set()
    if not start_url.strip():
        return scraped_whatsapp_links
    if not start_url.startswith(('http://', 'https://')):
        start_url = 'https://' + start_url
        st.sidebar.warning(f"Prepending 'https://': {start_url}", icon="🔗")
    try:
        parsed_start_url = urlparse(start_url)
    except Exception as pe:
        st.sidebar.error(f"Invalid start URL format: {start_url} - {pe}", icon="🚫")
        return scraped_whatsapp_links
    if not parsed_start_url.netloc:
        st.sidebar.error(f"Invalid start URL: {start_url}", icon="🚫")
        return scraped_whatsapp_links
    base_domain = parsed_start_url.netloc.replace('www.', '')

    # Initialize thread-safe state
    crawler_state = ThreadSafeCrawlerState()

    # Create a queue for URLs to be crawled
    url_queue = Queue()
    url_queue.put((start_url, 0)) # Add the starting URL with depth 0

    # Event to signal threads to stop
    stop_event = threading.Event()

    # Progress tracking variables
    page_count = 0
    progress_lock = threading.Lock() # Lock for updating shared progress variables

    def progress_callback(thread_id, url, depth):
        nonlocal page_count
        with progress_lock:
            page_count += 1
            current_page_count = page_count
            current_queue_size = url_queue.qsize()
        st.sidebar.text(f"T{thread_id} (D:{depth},P:{current_page_count},Q:{current_queue_size}): {url[:50]}...")
        # Check stop conditions based on max_pages
        if current_page_count >= max_pages:
             stop_event.set()
             st.sidebar.warning(f"Reached max pages limit ({max_pages}). Stopping crawl.", icon="🛑")

    # Session factory to create new sessions for threads
    def session_factory():
        session = requests.Session()
        # Optional: Add retry strategy for robustness
        # from requests.adapters import HTTPAdapter
        # from urllib3.util.retry import Retry
        # retry_strategy = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
        # adapter = HTTPAdapter(max_retries=retry_strategy)
        # session.mount("http://", adapter)
        # session.mount("https://", adapter)
        return session

    # Create and start worker threads
    num_threads = min(MAX_SCRAPING_WORKERS, 4) # Limit crawler threads more conservatively
    threads = []
    for i in range(num_threads):
        # Pass wait parameters to the worker
        t = threading.Thread(target=crawler_worker, args=(i, url_queue, crawler_state, base_domain, max_depth, session_factory, stop_event, progress_callback, wait_for_dynamic, wait_time_seconds))
        t.start()
        threads.append(t)
        # Slight stagger start to avoid initial burst
        time.sleep(0.05)

    # Wait for all tasks in the queue to be processed or stop event
    try:
        # Main waiting loop while threads are working or items are in the queue
        last_check_time = time.time()
        while not stop_event.is_set():
            # Check periodically if queue is empty and threads seem idle
            time.sleep(1)
            current_time = time.time()
            # Check every few seconds
            if current_time - last_check_time > 3:
                if url_queue.empty():
                    # Give threads a moment to finish current tasks or add new URLs
                    time.sleep(1.5)
                    if url_queue.empty():
                         # Likely done or stalled
                         break
                last_check_time = current_time
    except KeyboardInterrupt:
        st.sidebar.error("Crawl interrupted by user (Ctrl+C).", icon="🛑")
        stop_event.set()
    except Exception as general_crawl_wait_error:
         st.sidebar.error(f"Unexpected error during crawl wait: {general_crawl_wait_error}", icon="💥")
         stop_event.set()

    # Signal threads to stop if they haven't already
    stop_event.set()

    # Wait for threads to finish gracefully (with timeout)
    for t in threads:
        t.join(timeout=5) # Give them a timeout to finish

    # Get final results from the thread-safe state
    scraped_whatsapp_links = crawler_state.get_scraped_links()
    final_msg = f"Crawl finished. Scraped approx {page_count} pages, found {len(scraped_whatsapp_links)} links."
    if page_count >= max_pages:
        final_msg += f" Stopped at {max_pages} pages limit."
    if max_depth is not None:
        final_msg += f" Max depth was {max_depth}."
    st.sidebar.success(final_msg)
    return scraped_whatsapp_links
# --- End of Crawler Logic ---

def validate_link(link):
    # Initialize with empty group name
    result = {"Group Name": UNNAMED_GROUP_PLACEHOLDER, "Group Link": link, "Logo URL": "", "Status": "Error"}
    try:
        response = requests.get(link, headers=get_random_headers_general(), timeout=20, allow_redirects=True)
        response.encoding = 'utf-8'
        if response.status_code != 200:
            result["Status"] = "Expired (404 Not Found)" if response.status_code == 404 else f"HTTP Error {response.status_code}"
            return result
        if WHATSAPP_DOMAIN not in response.url:
            final_netloc = urlparse(response.url).netloc or 'Unknown Site'
            result["Status"] = f"Redirected Away ({final_netloc})"
            return result
        soup = BeautifulSoup(response.text, 'html.parser')
        page_text_lower = soup.get_text().lower()
        expired_phrases = ["invite link is invalid", "invite link was reset", "group doesn't exist", "this group is no longer available"]
        if any(phrase in page_text_lower for phrase in expired_phrases):
            result["Status"] = "Expired"
        group_name_found = False
        meta_title = soup.find('meta', property='og:title')
        if meta_title and meta_title.get('content'):
            group_name = html.unescape(meta_title['content']).strip()
            if group_name: result["Group Name"] = group_name; group_name_found = True
        if not group_name_found:
            potential_name_tags = soup.find_all(['h2', 'strong', 'span'], class_=re.compile('group-name', re.IGNORECASE)) + soup.find_all('div', class_=re.compile('name', re.IGNORECASE))
            for tag in potential_name_tags:
                text = tag.get_text().strip()
                if text and len(text) > 2 and text.lower() not in ["whatsapp group invite", "whatsapp", "join group", "invite link"]:
                    result["Group Name"] = text; group_name_found = True; break
        logo_found = False
        meta_image = soup.find('meta', property='og:image')
        if meta_image and meta_image.get('content'):
            src = html.unescape(meta_image['content'])
            if OG_IMAGE_PATTERN.match(src) or src.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
                result["Logo URL"] = src; logo_found = True
        if not logo_found:
            for img in soup.find_all('img', src=True):
                src = html.unescape(img['src'])
                if src.startswith('https://pps.whatsapp.net/'):
                    result["Logo URL"] = src; logo_found = True; break
        if result["Status"] == "Error":
            result["Status"] = "Active"
        elif result["Status"] == "Expired" and (group_name_found or logo_found):
            if soup.find('a', attrs={'id': 'action-button', 'href': link}):
                result["Status"] = "Active"
        # New validation rule: Active status requires valid group name
        if result["Status"] == "Active" and not result["Group Name"].strip():
            result["Status"] = "Expire"
        # Groups without valid names are marked "Expire"
        elif not result["Group Name"].strip():
            result["Status"] = "Expire"
    except requests.exceptions.Timeout: result["Status"] = "Timeout Error"
    except requests.exceptions.ConnectionError: result["Status"] = "Connection Error"
    except requests.exceptions.RequestException as e: result["Status"] = f"Network Error ({type(e).__name__})"
    except Exception as e:
        result["Status"] = f"Parsing Error ({type(e).__name__})"
        # Apply rule after exception
        if not result["Group Name"].strip():
            result["Status"] = "Expire"
    return result

def generate_styled_html_table(data_df_for_table):
    df_to_display = data_df_for_table[data_df_for_table['Group Name'] != UNNAMED_GROUP_PLACEHOLDER].copy()
    if df_to_display.empty:
        return "<p style='text-align:center; color:#777; margin-top:20px;'><i>No groups match the current display filters. Try adjusting them.</i></p>"
    html_string = '<table class="whatsapp-groups-table" aria-label="List of Active WhatsApp Groups">'
    html_string += '<caption>Filtered Active WhatsApp Groups</caption>'
    html_string += '<thead><tr>'
    html_string += '<th scope="col">Logo</th>'
    html_string += '<th scope="col">Group Name</th>'
    html_string += '<th scope="col">Group Link</th>'
    html_string += '</tr></thead>'
    html_string += '<tbody>'
    for _, row in df_to_display.iterrows():
        logo_url = row.get("Logo URL", "")
        group_name = row.get("Group Name", UNNAMED_GROUP_PLACEHOLDER)
        group_link = row.get("Group Link", "")
        html_string += '<tr>'
        html_string += '<td class="group-logo-cell">'
        alt_text = f"{html.escape(group_name)} Group Logo"
        if logo_url:
            display_logo_url = append_query_param(logo_url, 'w', '96') if logo_url.startswith('https://pps.whatsapp.net/') else logo_url
            html_string += f'<img src="{html.escape(display_logo_url)}" alt="{alt_text}" class="group-logo-img" loading="lazy">'
        else:
            html_string += f'<div class="group-logo-img" style="background-color:#e0e0e0; display:flex; align-items:center; justify-content:center; font-size:0.8em; color:#888;" aria-label="{alt_text}">?</div>'
        html_string += '</td>'
        safe_group_name = html.escape(group_name)
        html_string += f'<td class="group-name-cell">{safe_group_name}</td>'
        html_string += '<td class="join-button-cell">'
        if group_link and group_link.startswith(WHATSAPP_DOMAIN):
            html_string += f'<a href="{html.escape(group_link)}" class="join-button" target="_blank" rel="noopener noreferrer">Join Group</a>'
        else:
            html_string += '<span style="color:#888; font-size:0.9em;">N/A</span>'
        html_string += '</td></tr>'
    html_string += '</tbody></table>'
    return html_string

# --- Main Application Logic ---
def main():
    st.markdown('<h1 class="main-title">WhatsApp Link Scraper & Validator 🚀</h1>', unsafe_allow_html=True)
    st.markdown('<p class="subtitle">Discover, Scrape, Validate, and Manage WhatsApp Group Links with Enhanced Filtering.</p>', unsafe_allow_html=True)

    # Initialize session state
    if 'results' not in st.session_state: st.session_state.results = []
    if 'processed_links_in_session' not in st.session_state: st.session_state.processed_links_in_session = set()
    if 'styled_table_name_keywords' not in st.session_state: st.session_state.styled_table_name_keywords = ""
    if 'styled_table_current_limit_value' not in st.session_state: st.session_state.styled_table_current_limit_value = 50
    # Set "Active" as default filter for advanced filtering
    if 'adv_filter_status' not in st.session_state:
        st.session_state.adv_filter_status = ["Active"]
    if 'adv_filter_name_keywords' not in st.session_state:
        st.session_state.adv_filter_name_keywords = ""
    # Ensure processed_links_in_session is a set and populate it
    if not isinstance(st.session_state.processed_links_in_session, set):
        st.session_state.processed_links_in_session = set()
    if isinstance(st.session_state.results, list):
        for res_item in st.session_state.results:
            if isinstance(res_item, dict) and 'Group Link' in res_item and res_item['Group Link']:
                try:
                    parsed_link = urlparse(res_item['Group Link'])
                    normalized_link = f"{parsed_link.scheme}://{parsed_link.netloc}{parsed_link.path}"
                    st.session_state.processed_links_in_session.add(normalized_link)
                except Exception:
                    st.session_state.processed_links_in_session.add(res_item['Group Link'])

    # Sidebar
    with st.sidebar:
        st.header("⚙️ Input & Settings")
        input_method = st.selectbox("Choose Input Method:", [
            "Search and Scrape from Google", "Search & Scrape from Google (Bulk via Excel)",
            "Scrape from Specific Webpage URL", "Scrape from Bulk Specific URLs (TXT/CSV/Excel)",
            "Scrape from Entire Website (Extensive Crawl)",
            "Enter Links Manually (for Validation)", "Upload Link File (TXT/CSV/Excel - Validation)"
        ], key="input_method_main_select")

        # --- New Settings for Dynamic Content Handling ---
        st.markdown("---")
        st.subheader("🔄 Dynamic Content Handling")
        wait_for_dynamic_content = st.checkbox(
            "Wait for Dynamic Content (e.g., Timers)",
            value=False,
            key="wait_for_dynamic_checkbox",
            help="Enable this if target pages load links after a delay using JavaScript. Increases scrape time."
        )
        wait_time_seconds = 5
        if wait_for_dynamic_content:
            wait_time_seconds = st.slider(
                "Wait Time (seconds):",
                min_value=1,
                max_value=30,
                value=5,
                step=1,
                key="wait_time_slider",
                help="How long to wait before scraping the page again."
            )
        # --- End of New Settings ---

        gs_top_n = 5
        if input_method in ["Search and Scrape from Google", "Search & Scrape from Google (Bulk via Excel)", "Upload Link File (TXT/CSV/Excel - Validation)"]:
            gs_top_n = st.slider("Google Results to Scrape (per keyword)", 1, 20, 5, key="gs_top_n_slider", help="Number of Google search result pages to analyze per keyword.")

        # --- Updated Crawl Settings UI ---
        crawl_depth, crawl_pages = None, 1000000 # Defaults for unlimited
        if input_method == "Scrape from Entire Website (Extensive Crawl)":
            st.info("ℹ️ Default settings are now 'Unlimited Depth' and 'Unlimited Pages'. Adjust if needed.", icon="ℹ️")
            # Use None or a specific int for depth. None means unlimited.
            crawl_depth_option = st.radio(
                "Crawl Depth Limit:",
                options=["Unlimited Depth", "Set Depth Limit"],
                index=0, # Default to Unlimited
                key="crawl_depth_option_radio"
            )
            if crawl_depth_option == "Set Depth Limit":
                crawl_depth = st.slider("Max Crawl Depth", 0, 10, 2, key="crawl_depth_slider")
            # Use a very high default for pages, effectively unlimited unless changed.
            crawl_pages_option = st.radio(
                "Crawl Page Limit:",
                options=["Unlimited Pages (Default)", "Set Page Limit"],
                index=0, # Default to Unlimited
                key="crawl_pages_option_radio"
            )
            if crawl_pages_option == "Set Page Limit":
                crawl_pages = st.slider("Max Pages to Crawl", 1, 50000, 1000, step=100, key="crawl_pages_slider")
            st.markdown("---")
            st.warning("⚠️ Unlimited crawl can take a very long time and consume significant resources. Ensure the target site allows crawling. Consider setting limits.", icon="🚨")
        st.markdown("---")
        if st.button("🗑️ Clear All Results & Reset Filters", use_container_width=True, key="clear_all_button"):
            st.session_state.results, st.session_state.processed_links_in_session = [], set()
            st.session_state.styled_table_name_keywords = ""
            st.session_state.styled_table_current_limit_value = 50
            st.session_state.adv_filter_status = ["Active"]  # Reset to default "Active"
            st.session_state.adv_filter_name_keywords = ""
            st.cache_data.clear(); st.success("Results & filters cleared!"); st.rerun()

    # Action Zone
    current_action_scraped_links = set()
    st.subheader(f"🚀 Action Zone: {input_method}")
    try:
        if input_method == "Search and Scrape from Google":
            query = st.text_input("Search Query:", placeholder="e.g., Islamic WhatsApp group", key="gs_query_input")
            if st.button("Search, Scrape & Validate", use_container_width=True, key="gs_button"):
                if query:
                    # Pass wait parameters
                    current_action_scraped_links.update(google_search_and_scrape(query, gs_top_n, wait_for_dynamic_content, wait_time_seconds))
                else: st.warning("Please enter a search query.")
        elif input_method == "Search & Scrape from Google (Bulk via Excel)":
            file = st.file_uploader("Upload Excel (keywords in 1st col)", type=["xlsx"], key="gs_bulk_excel_upload")
            if file and st.button("Process Excel, Scrape & Validate", use_container_width=True, key="gs_bulk_button"):
                keywords = load_keywords_from_excel(file)
                if keywords:
                    st.info(f"Processing {len(keywords)} keywords...")
                    prog_b, stat_b = st.progress(0), st.empty()
                    total_l = 0
                    for i, kw in enumerate(keywords):
                        stat_b.text(f"Keyword: '{kw}' ({i+1}/{len(keywords)}). Total links: {total_l}")
                        # Pass wait parameters
                        links_from_kw = google_search_and_scrape(kw, gs_top_n, wait_for_dynamic_content, wait_time_seconds)
                        current_action_scraped_links.update(links_from_kw)
                        total_l = len(current_action_scraped_links)
                        prog_b.progress((i+1)/len(keywords))
                    stat_b.success(f"Bulk done. Found {total_l} links.")
                else: st.warning("No valid keywords in Excel.")
        elif input_method == "Scrape from Specific Webpage URL":
            url = st.text_input("Webpage URL:", placeholder="https://example.com/page", key="specific_url_input")
            if st.button("Scrape Page & Validate", use_container_width=True, key="specific_url_button"):
                if url and (url.startswith("http://") or url.startswith("https://")):
                    with st.spinner(f"Scraping {url}..."):
                        # Pass wait parameters
                        current_action_scraped_links.update(scrape_whatsapp_links_from_page(url, wait_for_dynamic=wait_for_dynamic_content, wait_time_seconds=wait_time_seconds))
                    st.success(f"Scraping done. Found {len(current_action_scraped_links)} links.")
                else: st.warning("Please enter a valid URL.")
        # --- New Bulk URL Scraping Feature ---
        elif input_method == "Scrape from Bulk Specific URLs (TXT/CSV/Excel)":
             file = st.file_uploader("Upload TXT/CSV/Excel (containing URLs to scrape)", type=["txt", "csv", "xlsx"], key="bulk_urls_file_uploader")
             if file and st.button("Process Bulk URLs & Validate", use_container_width=True, key="bulk_urls_button"):
                urls_to_scrape = load_links_from_file(file) # Reuse the function, it handles TXT/CSV now
                if file.name.endswith('.xlsx'):
                    # Special handling for Excel: assume first column contains URLs
                    try:
                        df_excel = pd.read_excel(io.BytesIO(file.getvalue()), engine='openpyxl')
                        if df_excel.empty: st.warning("Excel file is empty."); urls_to_scrape = []
                        else:
                            urls_to_scrape = [url.strip() for url in df_excel.iloc[:, 0].dropna().astype(str).tolist() if url.strip().startswith(('http://', 'https://'))]
                            if not urls_to_scrape: st.warning("No valid URLs found in the first column of the Excel file.")
                    except Exception as e_excel:
                        st.error(f"Error reading Excel for URLs: {e_excel}", icon="❌")
                        urls_to_scrape = []
                if urls_to_scrape:
                    st.info(f"Loaded {len(urls_to_scrape)} URLs. Starting concurrent scrape...")
                    # Pass wait parameters
                    current_action_scraped_links.update(scrape_bulk_urls(urls_to_scrape, wait_for_dynamic_content, wait_time_seconds))
                else:
                    st.warning("No valid URLs found in the uploaded file.")
        elif input_method == "Scrape from Entire Website (Extensive Crawl)":
            domain = st.text_input("Base Domain URL:", placeholder="example.com", key="crawl_domain_input")
            if st.button("Crawl & Scrape", use_container_width=True, key="crawl_button"):
                if domain:
                    st.info("Starting crawl. Progress in sidebar.")
                    # Pass wait parameters
                    current_action_scraped_links.update(crawl_website(domain, crawl_depth, crawl_pages, wait_for_dynamic_content, wait_time_seconds))
                    st.success(f"Crawl done. Found {len(current_action_scraped_links)} links.")
                else: st.warning("Please enter a domain.")
        elif input_method == "Enter Links Manually (for Validation)":
            text = st.text_area("WhatsApp Links (one per line):", height=200, key="manual_links_area")
            if st.button("Validate Links", use_container_width=True, key="manual_validate_button"):
                links = [line.strip() for line in text.split('\n') if line.strip()]
                if links:
                    valid_links = {l for l in links if l.startswith(WHATSAPP_DOMAIN)}
                    if len(valid_links) < len(links): st.warning(f"Skipped {len(links)-len(valid_links)} non-WhatsApp links.")
                    current_action_scraped_links.update(valid_links)
                else: st.warning("Please enter links.")
        elif input_method == "Upload Link File (TXT/CSV/Excel - Validation)":
            file = st.file_uploader("Upload TXT, CSV (links) or Excel (keywords)", type=["txt", "csv", "xlsx"], key="upload_file_input_validation")
            if file and st.button("Process File for Validation", use_container_width=True, key="upload_process_button_validation"):
                if file.name.endswith('.xlsx'):
                    st.info("Loading keywords from Excel for Google search...")
                    keywords = load_keywords_from_excel(file)
                    if keywords:
                        prog_e, stat_e = st.progress(0), st.empty()
                        total_le = 0
                        for i, kw in enumerate(keywords):
                            stat_e.text(f"Keyword: {kw} ({i+1}/{len(keywords)}). Links: {total_le}")
                            # Pass wait parameters
                            links_from_kw = google_search_and_scrape(kw, gs_top_n, wait_for_dynamic_content, wait_time_seconds)
                            current_action_scraped_links.update(links_from_kw)
                            total_le = len(current_action_scraped_links)
                            prog_e.progress((i+1)/len(keywords))
                        stat_e.success(f"Excel processing done. Found {total_le} links.")
                    else: st.warning("No keywords in Excel.")
                elif file.name.endswith(('.txt', '.csv')):
                    st.info("Loading links from TXT/CSV for validation...")
                    links = load_links_from_file(file)
                    if links:
                        valid_links = {l for l in links if l.startswith(WHATSAPP_DOMAIN)}
                        if len(valid_links) < len(links): st.warning(f"Skipped {len(links)-len(valid_links)} non-WhatsApp links.")
                        current_action_scraped_links.update(valid_links)
                    else: st.warning("No links in file.")
                else: st.warning("Unsupported file. Use .txt, .csv, or .xlsx.")
    except Exception as e: st.error(f"Input/Scraping Error: {e}", icon="💥")

    # Validation
    links_to_validate_now = list(current_action_scraped_links - st.session_state.processed_links_in_session)
    if links_to_validate_now:
        st.success(f"Found {len(current_action_scraped_links)} links. Validating {len(links_to_validate_now)} new links...")
        prog_val, stat_val = st.progress(0), st.empty()
        new_results_this_run = []
        with ThreadPoolExecutor(max_workers=MAX_VALIDATION_WORKERS) as executor:
            future_to_link = {executor.submit(validate_link, link): link for link in links_to_validate_now}
            for i, future in enumerate(as_completed(future_to_link)):
                link_validated = future_to_link[future]
                try:
                    result_validated = future.result()
                    new_results_this_run.append(result_validated)
                    parsed_url_val = urlparse(link_validated)
                    normalized_link_val = f"{parsed_url_val.scheme}://{parsed_url_val.netloc}{parsed_url_val.path}"
                    st.session_state.processed_links_in_session.add(normalized_link_val)
                except Exception as val_exc:
                    st.warning(f"Error validating {link_validated[:40]}...: {val_exc}", icon="⚠️")
                    parsed_url_val_err = urlparse(link_validated)
                    normalized_link_val_err = f"{parsed_url_val_err.scheme}://{parsed_url_val_err.netloc}{parsed_url_val_err.path}"
                    st.session_state.processed_links_in_session.add(normalized_link_val_err)
                    new_results_this_run.append({"Group Name": "Validation Error", "Group Link": link_validated, "Logo URL": "", "Status": f"Validation Failed: {type(val_exc).__name__}"})
                prog_val.progress((i+1)/len(links_to_validate_now))
                stat_val.text(f"Validated {i+1}/{len(links_to_validate_now)} links")
        if new_results_this_run:
            st.session_state.results.extend(new_results_this_run)
        stat_val.success(f"Validation complete for {len(links_to_validate_now)} new links!")
    elif current_action_scraped_links and not links_to_validate_now:
        st.info("No *new* WhatsApp links found from this action. All were previously processed.")

    # Results Display
    if 'results' in st.session_state and st.session_state.results:
        unique_results_df = pd.DataFrame(st.session_state.results).drop_duplicates(subset=['Group Link'], keep='first')
        st.session_state.results = unique_results_df.to_dict('records')
        df_display_master = unique_results_df.reset_index(drop=True)

        # Updated status handling to include "Expire"
        condition_expired = (df_display_master['Status'].str.startswith('Expired')) | (df_display_master['Status'] == 'Expire')
        active_df_all_master = df_display_master[df_display_master['Status'] == 'Active'].copy()
        expired_df_master = df_display_master[condition_expired].copy()
        error_df_master = df_display_master[~condition_expired & (df_display_master['Status'] != 'Active')].copy()

        st.subheader("📊 Results Summary")
        col1, col2, col3, col4 = st.columns(4)
        col1.markdown(f'<div class="metric-card">Total Processed<br><div class="metric-value">{len(df_display_master)}</div></div>', unsafe_allow_html=True)
        col2.markdown(f'<div class="metric-card">Active Links<br><div class="metric-value">{len(active_df_all_master)}</div></div>', unsafe_allow_html=True)
        col3.markdown(f'<div class="metric-card">Expired/Expire Links<br><div class="metric-value">{len(expired_df_master)}</div></div>', unsafe_allow_html=True)
        col4.markdown(f'<div class="metric-card">Other Status<br><div class="metric-value">{len(error_df_master)}</div></div>', unsafe_allow_html=True)

        # Styled Table with Filters
        st.subheader("✨ Active Groups Display (Styled Table)")
        with st.expander("View and Filter Active Groups", expanded=False):
            if not active_df_all_master.empty:
                st.markdown('<div class="filter-container">', unsafe_allow_html=True)
                st.markdown("#### Filter Displayed Active Groups:")
                with st.form("styled_table_filters_form"):
                    name_keywords_input = st.text_input(
                        "Filter by Group Name Keywords (comma-separated):",
                        value=st.session_state.styled_table_name_keywords,
                        placeholder="e.g., study, fun, tech",
                        help="Enter keywords (comma-separated). Shows groups matching ANY keyword."
                    ).strip()
                    limit_input = st.number_input(
                        "Max Groups to Display in Table:",
                        min_value=1,
                        max_value=1000,
                        value=st.session_state.styled_table_current_limit_value,
                        step=10,
                        help="Set the maximum number of groups to display in the table."
                    )
                    apply_filters = st.form_submit_button("Apply Filters")
                if apply_filters:
                    st.session_state.styled_table_name_keywords = name_keywords_input
                    st.session_state.styled_table_current_limit_value = limit_input
                if st.button("Reset Filters", key="reset_styled_table_filters_button"):
                    st.session_state.styled_table_name_keywords = ""
                    st.session_state.styled_table_current_limit_value = 50
                    st.rerun()

                # Filter the dataframe
                active_df_for_styled_table = active_df_all_master.copy()
                if st.session_state.styled_table_name_keywords:
                    keywords_list = [kw.strip().lower() for kw in st.session_state.styled_table_name_keywords.split(',') if kw.strip()]
                    if keywords_list:
                        regex_pattern = '|'.join(map(re.escape, keywords_list))
                        active_df_for_styled_table = active_df_for_styled_table[
                            active_df_for_styled_table['Group Name'].str.lower().str.contains(regex_pattern, na=False, regex=True)
                        ]
                num_matching = len(active_df_for_styled_table)
                num_displayed = min(num_matching, st.session_state.styled_table_current_limit_value)
                active_df_for_styled_table_final = active_df_for_styled_table.head(num_displayed)
                if num_matching > 0:
                    st.write(f"Showing {num_displayed} out of {num_matching} matching active groups.")
                else:
                    st.write("No groups match the current filters.")
                html_out = generate_styled_html_table(active_df_for_styled_table_final)
                st.markdown(html_out, unsafe_allow_html=True)
                st.markdown("---")
                st.text_area("Copy Raw HTML Code (above table):", value=html_out, height=150, key="styled_html_export_area_key", help="Ctrl+A, Ctrl+C")
                st.markdown('</div>', unsafe_allow_html=True) # Close filter-container
            else:
                st.info("No active groups found yet to display here.")

        # Advanced Filtering for Downloads
        with st.expander("🔬 Advanced Filtering for Downloads & Analysis (Optional)", expanded=False):
            st.markdown('<div class="filter-container" style="border-style:solid;">', unsafe_allow_html=True)
            st.markdown("#### Filter Full Dataset (for Download/Analysis):")
            all_statuses_master = sorted(list(df_display_master['Status'].unique()))
            # Set "Active" as default filter
            st.session_state.adv_filter_status = st.multiselect(
                "Filter by Status:", options=all_statuses_master,
                default=st.session_state.adv_filter_status, key="adv_status_filter_multiselect_key"
            )
            st.session_state.adv_filter_name_keywords = st.text_input(
                "Filter by Group Name Keywords (comma-separated):", value=st.session_state.adv_filter_name_keywords,
                key="adv_name_keyword_filter_input_key", placeholder="e.g., news, jobs, global",
                help="Applies to the entire dataset for download/analysis. Comma-separated."
            ).strip()
            st.markdown('</div>', unsafe_allow_html=True)

            df_for_adv_download_or_view = df_display_master.copy()
            adv_filters_applied = False
            if st.session_state.adv_filter_status:
                df_for_adv_download_or_view = df_for_adv_download_or_view[df_for_adv_download_or_view['Status'].isin(st.session_state.adv_filter_status)]
                adv_filters_applied = True
            if st.session_state.adv_filter_name_keywords:
                adv_keywords_list = [kw.strip().lower() for kw in st.session_state.adv_filter_name_keywords.split(',') if kw.strip()]
                if adv_keywords_list:
                    adv_regex_pattern = '|'.join(map(re.escape, adv_keywords_list))
                    df_for_adv_download_or_view = df_for_adv_download_or_view[
                        df_for_adv_download_or_view['Group Name'].str.lower().str.contains(adv_regex_pattern, na=False, regex=True)
                    ]
                    adv_filters_applied = True
            st.markdown(f"**Preview of Data for Download/Analysis ({'Filtered' if adv_filters_applied else 'All'} - {len(df_for_adv_download_or_view)} rows):**")
            st.dataframe(df_for_adv_download_or_view, column_config={
                "Group Link": st.column_config.LinkColumn("Invite Link", display_text="Join", width="medium"),
                "Group Name": st.column_config.TextColumn("Group Name", width="large"),
                "Logo URL": st.column_config.LinkColumn("Logo URL", display_text="View", width="small"),
                "Status": st.column_config.TextColumn("Status", width="small")
            }, hide_index=True, height=300, use_container_width=True)

        # Downloads
        st.subheader("📥 Download Results (CSV)")
        dl_col1, dl_col2 = st.columns(2)
        if not active_df_all_master.empty:
            dl_col1.download_button("Active Groups (CSV)", active_df_all_master.to_csv(index=False).encode('utf-8'), "active_groups.csv", "text/csv", use_container_width=True, key="dl_active_csv_main_key")
        else:
            dl_col1.button("Active Groups (CSV)", disabled=True, use_container_width=True, help="No active groups to download.")
        if not df_for_adv_download_or_view.empty:
            download_label = "All Processed Results (CSV)"
            if adv_filters_applied: download_label = f"Filtered Processed Results (CSV - {len(df_for_adv_download_or_view)} rows)"
            dl_col2.download_button(download_label, df_for_adv_download_or_view.to_csv(index=False).encode('utf-8'), "processed_results.csv", "text/csv", use_container_width=True, key="dl_all_or_filtered_csv_key")
        elif not df_display_master.empty and df_for_adv_download_or_view.empty and adv_filters_applied:
            dl_col2.button("No Results Match Advanced Filters", disabled=True, use_container_width=True)
        else:
            dl_col2.button("All Processed Results (CSV)", disabled=True, use_container_width=True, help="No results to download.")
    else:
        st.info("Start by searching, entering, or uploading links to see results!", icon="ℹ️")

if __name__ == "__main__":
    main()
