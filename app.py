import streamlit as st
import pandas as pd
import requests
from html import unescape
from bs4 import BeautifulSoup
import re
import time
from urllib.parse import urljoin, urlparse
from collections import deque
import random
from fake_useragent import UserAgent

# Streamlit Configuration
st.set_page_config(
    page_title="WhatsApp Link Validator",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Constants
WHATSAPP_DOMAIN = "https://chat.whatsapp.com/"
IMAGE_PATTERN = re.compile(r'https:\/\/pps\.whatsapp\.net\/.*\.jpg\?[^&]*&[^&]+')
GOOGLE_SEARCH_URL = "https://www.google.com/search"

# Initialize UserAgent (handle potential errors in Streamlit Cloud)
try:
    ua = UserAgent()
    USER_AGENT = ua.random
except Exception as e:
    # Fallback if fake-useragent fails (common in some cloud environments)
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36 Edg/118.0.2088.46"

# Custom CSS for enhanced UI
st.markdown("""
    <style>
    .main-title {
        font-size: 2.5em;
        color: #25D366; /* WhatsApp Green */
        text-align: center;
        margin-bottom: 0;
        font-weight: bold;
    }
    .subtitle {
        font-size: 1.2em;
        color: #4A4A4A; /* Dark Gray */
        text-align: center;
        margin-top: 0;
    }
    .stButton>button {
        background-color: #25D366;
        color: #FFFFFF;
        border-radius: 8px;
        font-weight: bold;
        border: none;
        padding: 8px 16px;
    }
    .stButton>button:hover {
        background-color: #1EBE5A;
        color: #FFFFFF;
    }
    .stProgress .st-bo {
        background-color: #25D366;
    }
    .metric-card {
        background-color: #F5F6F5;
        padding: 12px;
        border-radius: 8px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        color: #333333;
        text-align: center;
    }
    .stTextInput, .stTextArea, .stNumberInput {
        border: 1px solid #25D366;
        border-radius: 5px;
    }
    .sidebar .sidebar-content {
        background-color: #F5F6F5;
    }
    .stExpander {
        border: 1px solid #E0E0E0;
        border-radius: 5px;
    }
    </style>
""", unsafe_allow_html=True)

def get_headers():
    """Generate headers with a random user agent."""
    return {
        "User-Agent": USER_AGENT,
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Cache-Control": "max-age=0"
    }

def is_valid_url(url):
    """Check if a URL is valid."""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except:
        return False

def is_same_domain(url1, url2):
    """Check if two URLs belong to the same domain."""
    try:
        domain1 = urlparse(url1).netloc
        domain2 = urlparse(url2).netloc
        # Normalize domains by removing 'www.' for comparison
        domain1 = domain1.replace('www.', '')
        domain2 = domain2.replace('www.', '')
        return domain1 == domain2
    except:
        return False

def normalize_url(url):
    """Normalize a URL by removing fragments and standardizing."""
    try:
        parsed = urlparse(url)
        # Reconstruct URL without fragment for comparison
        normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        if parsed.query:
             # Include query params but sort them for consistency
             params = sorted(parsed.query.split('&'))
             normalized += '?' + '&'.join(params)
        return normalized.lower()
    except:
        return url.lower()

def fetch_page_content(url, timeout=15, retries=2, backoff_factor=1.0):
    """
    Fetch page content with retries and exponential backoff.
    """
    headers = get_headers()
    for attempt in range(retries + 1):
        try:
            # Adding a small random delay before request to be polite
            time.sleep(random.uniform(0.1, 0.5))
            response = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
            response.raise_for_status() # Raise an exception for bad status codes
            return response
        except requests.exceptions.RequestException as e:
            if attempt < retries:
                wait_time = backoff_factor * (2 ** attempt) + random.uniform(0, 1)
                st.warning(f"Attempt {attempt + 1} failed for {url}. Retrying in {wait_time:.2f}s... Error: {type(e).__name__}")
                time.sleep(wait_time)
            else:
                 st.error(f"Failed to fetch {url} after {retries + 1} attempts. Error: {e}")
                 return None
    return None

def scrape_website_comprehensive_requests(base_url, delay_seconds=5, max_pages=None, status_placeholder=None):
    """
    Crawl a website using requests/BeautifulSoup to find WhatsApp links.
    Note: This cannot execute JavaScript but uses retries and delays to try and capture
    content that might appear quickly or be present in initial HTML.
    """
    if not is_valid_url(base_url):
        st.error("Invalid base URL provided.")
        return []

    whatsapp_links = set()
    visited_urls = set()
    url_queue = deque([base_url])
    pages_crawled = 0

    if status_placeholder:
        status_placeholder.info("Starting website crawl with requests (no JS execution)...")

    while url_queue and (max_pages is None or pages_crawled < max_pages):
        current_url = url_queue.popleft()
        normalized_current_url = normalize_url(current_url)

        if normalized_current_url in visited_urls:
            continue

        visited_urls.add(normalized_current_url)
        pages_crawled += 1

        if status_placeholder:
            status_placeholder.info(f"Crawling ({pages_crawled}): {current_url[:100]}...")

        # --- Fetch page content ---
        # Use a longer timeout to mimic waiting for content
        effective_timeout = max(15, delay_seconds + 5) # Ensure a minimum timeout
        response = fetch_page_content(current_url, timeout=effective_timeout)

        if response is None:
            continue # Error already logged in fetch_page_content

        # --- Parse HTML ---
        try:
            soup = BeautifulSoup(response.text, 'html.parser')
        except Exception as e:
            if status_placeholder:
                status_placeholder.warning(f"Error parsing HTML for {current_url}: {e}")
            continue

        # --- Find WhatsApp Links ---
        links_on_page = soup.find_all('a', href=True)
        for link_tag in links_on_page:
            href = link_tag['href']
            absolute_href = urljoin(current_url, href)

            # Check if it's a WhatsApp group link
            if absolute_href.startswith(WHATSAPP_DOMAIN):
                whatsapp_links.add(absolute_href)

            # Check if it's an internal link for further crawling
            elif is_same_domain(current_url, absolute_href) and is_valid_url(absolute_href):
                normalized_href = normalize_url(absolute_href)
                if normalized_href not in visited_urls:
                    url_queue.append(absolute_href)

    if status_placeholder:
        status_placeholder.success(f"Crawling completed. Visited {pages_crawled} pages.")

    return list(whatsapp_links)

def validate_link(link):
    """Validate a WhatsApp group link and return details if active."""
    result = {
        "Group Name": "Expired",
        "Group Link": link,
        "Logo URL": "",
        "Status": "Expired"
    }
    try:
        headers = get_headers() # Use rotating user agent
        response = requests.get(link, headers=headers, timeout=15, allow_redirects=True)
        if WHATSAPP_DOMAIN not in response.url:
            return result
        soup = BeautifulSoup(response.text, 'html.parser')
        meta_title = soup.find('meta', property='og:title')
        result["Group Name"] = unescape(meta_title['content']).strip() if meta_title and meta_title.get('content') else "Unnamed Group"
        img_tags = soup.find_all('img', src=True)
        for img in img_tags:
            src = unescape(img['src'])
            if IMAGE_PATTERN.match(src):
                result["Logo URL"] = src
                result["Status"] = "Active"
                break
        return result
    except Exception as e:
         # Optional: Log validation errors for debugging
         # st.warning(f"Validation error for {link}: {e}")
        return result

def scrape_whatsapp_links(url):
    """Scrape WhatsApp group links from a webpage."""
    try:
        headers = get_headers() # Use rotating user agent
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        links = [a['href'] for a in soup.find_all('a', href=True) if a['href'].startswith(WHATSAPP_DOMAIN)]
        return links
    except Exception as e:
         # Optional: Log scraping errors for debugging
         # st.warning(f"Scraping error for {url}: {e}")
        return []

def google_search(query, num_pages):
    """Custom Google search to fetch URLs from multiple pages."""
    search_results = []
    headers = get_headers() # Use rotating user agent
    for page in range(num_pages):
        params = {
            "q": query,
            "start": page * 10
        }
        try:
            # Longer timeout for search
            response = requests.get(GOOGLE_SEARCH_URL, headers=headers, params=params, timeout=20)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            for a in soup.find_all('a', href=True):
                href = a['href']
                if href.startswith('/url?q='):
                    url = href.split('/url?q=')[1].split('&')[0]
                    search_results.append(url)
            time.sleep(random.uniform(2, 4)) # Randomized pause to be polite
        except Exception as e:
            st.error(f"Error on Google page {page + 1}: {e}")
            break
    return list(set(search_results))

def load_links(uploaded_file):
    """Load WhatsApp group links from an uploaded TXT or CSV file."""
    if uploaded_file.name.endswith('.csv'):
        return pd.read_csv(uploaded_file).iloc[:, 0].tolist()
    else:
        # Decode bytes to string
        content = uploaded_file.read().decode('utf-8')
        return [line.strip() for line in content.splitlines() if line.strip()]

def main():
    """Main function for the WhatsApp Group Validator app."""
    st.markdown('<h1 class="main-title">WhatsApp Group Validator 🚀</h1>', unsafe_allow_html=True)
    st.markdown('<p class="subtitle">Search, scrape, or validate WhatsApp group links with ease</p>', unsafe_allow_html=True)

    # Sidebar for settings
    with st.sidebar:
        st.header("⚙️ Settings")
        st.markdown("Customize your experience")
        input_method = st.selectbox(
            "Input Method",
            [
                "Search and Scrape from Google",
                "Enter Links Manually",
                "Upload File (TXT/CSV)",
                "Scrape Entire Website (Requests)"
            ],
            help="Choose how to input links"
        )

        if input_method == "Search and Scrape from Google":
            num_pages = st.slider("Google Pages to Scrape", min_value=1, max_value=5, value=3, help="More pages may increase scraping time")
        elif input_method == "Scrape Entire Website (Requests)":
            delay_seconds = st.slider("Simulated JS Load Delay (seconds)", min_value=0, max_value=30, value=5,
                                      help="Extra time to wait for page load (note: no real JS execution)")
            max_pages = st.number_input("Max Pages to Crawl (0 for unlimited)", min_value=0, value=50,
                                        help="Limit crawling to avoid excessive runtime. Set to 0 for no limit (use carefully).")
            if max_pages == 0:
                max_pages = None

    # Clear Results Button
    if st.button("🗑️ Clear Results", use_container_width=True):
        if 'results' in st.session_state:
            del st.session_state['results']
        st.success("Results cleared successfully!")

    # Input Section
    with st.container():
        results = []
        if input_method == "Search and Scrape from Google":
            st.subheader("🔍 Google Search & Scrape")
            keyword = st.text_input("Search Query:", placeholder="e.g., 'whatsapp group links site:*.com -inurl:(login)'", help="Refine with site: or -inurl:")
            if st.button("Search, Scrape, and Validate", use_container_width=True):
                if not keyword:
                    st.warning("Please enter a search query.")
                    return
                with st.spinner("Searching Google..."):
                    search_results = google_search(keyword, num_pages)
                if not search_results:
                    st.info("No search results found for the query.")
                    return
                st.success(f"Found {len(search_results)} webpages. Scraping WhatsApp links...")
                all_links = []
                progress_bar = st.progress(0)
                total_search_results = len(search_results)
                for idx, url in enumerate(search_results):
                    links = scrape_whatsapp_links(url)
                    all_links.extend(links)
                    progress_bar.progress((idx + 1) / total_search_results)
                unique_links = list(set(all_links))
                if not unique_links:
                    st.warning("No WhatsApp group links found in the scraped webpages.")
                    return
                st.success(f"Scraped {len(unique_links)} unique WhatsApp group links. Validating...")
                progress_bar = st.progress(0)
                status_text = st.empty()
                total_unique_links = len(unique_links)
                for i, link in enumerate(unique_links):
                    result = validate_link(link)
                    results.append(result)
                    progress_bar.progress((i + 1) / total_unique_links)
                    status_text.text(f"Validated {i + 1}/{total_unique_links} links")
                status_text.empty() # Clear status when done

        elif input_method == "Scrape Entire Website (Requests)":
            st.subheader("🕷️ Scrape Entire Website (Requests-based)")
            base_url = st.text_input("Base Website URL:", placeholder="e.g., https://example.com",
                                     help="The starting point for crawling the website")
            st.info("⚠️ **Note:** This method uses `requests` and `BeautifulSoup`. It **cannot** execute JavaScript. It will only find links present in the initial HTML or loaded very quickly. For sites with heavy JS delays, results may be limited.")
            if st.button("Crawl, Scrape, and Validate", use_container_width=True):
                if not base_url:
                    st.warning("Please enter a base website URL.")
                    return

                status_placeholder = st.empty()
                status_placeholder.info("Starting website crawl...")

                try:
                    unique_links = scrape_website_comprehensive_requests(
                        base_url,
                        delay_seconds=delay_seconds,
                        max_pages=max_pages,
                        status_placeholder=status_placeholder
                    )
                except Exception as e:
                    st.error(f"An unexpected error occurred during crawling: {e}")
                    return

                if not unique_links:
                    st.warning("No WhatsApp group links found on the crawled website.")
                    return

                st.success(f"Scraped {len(unique_links)} unique WhatsApp group links. Validating...")
                progress_bar = st.progress(0)
                status_text = st.empty()
                total_unique_links = len(unique_links)
                for i, link in enumerate(unique_links):
                    result = validate_link(link)
                    results.append(result)
                    progress_bar.progress((i + 1) / total_unique_links)
                    status_text.text(f"Validated {i + 1}/{total_unique_links} links")
                status_text.empty() # Clear status when done


        elif input_method == "Enter Links Manually":
            st.subheader("📝 Manual Link Entry")
            links_text = st.text_area("Enter WhatsApp Links (one per line):", height=200, placeholder="e.g., https://chat.whatsapp.com/ABC123")
            if st.button("Validate Links", use_container_width=True):
                # Handle potential different line endings
                links = [line.strip() for line in links_text.replace('\r\n', '\n').split('\n') if line.strip()]
                if not links:
                    st.warning("Please enter at least one link.")
                    return
                progress_bar = st.progress(0)
                status_text = st.empty()
                total_links = len(links)
                for i, link in enumerate(links):
                    result = validate_link(link)
                    results.append(result)
                    progress_bar.progress((i + 1) / total_links)
                    status_text.text(f"Validated {i + 1}/{total_links} links")
                status_text.empty() # Clear status when done

        elif input_method == "Upload File (TXT/CSV)":
            st.subheader("📥 File Upload")
            uploaded_file = st.file_uploader("Upload TXT or CSV", type=["txt", "csv"], help="One link per line or in first column")
            if uploaded_file and st.button("Validate File Links", use_container_width=True):
                try:
                    links = load_links(uploaded_file)
                except Exception as e:
                     st.error(f"Error reading file: {e}")
                     return
                if not links:
                    st.warning("No links found in the uploaded file.")
                    return
                progress_bar = st.progress(0)
                status_text = st.empty()
                total_links = len(links)
                for i, link in enumerate(links):
                    result = validate_link(link)
                    results.append(result)
                    progress_bar.progress((i + 1) / total_links)
                    status_text.text(f"Validated {i + 1}/{total_links} links")
                status_text.empty() # Clear status when done

        # Store results in session state
        if results:
            st.session_state['results'] = results

    # Results Section
    if 'results' in st.session_state:
        df = pd.DataFrame(st.session_state['results'])
        active_df = df[df['Status'] == 'Active']
        expired_df = df[df['Status'] == 'Expired']

        # Summary Metrics
        st.subheader("📊 Results Summary")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown('<div class="metric-card">', unsafe_allow_html=True)
            st.metric("Total Links", len(df), help="Total links processed")
            st.markdown('</div>', unsafe_allow_html=True)
        with col2:
            st.markdown('<div class="metric-card">', unsafe_allow_html=True)
            st.metric("Active Links", len(active_df), help="Valid WhatsApp groups")
            st.markdown('</div>', unsafe_allow_html=True)
        with col3:
            st.markdown('<div class="metric-card">', unsafe_allow_html=True)
            st.metric("Expired Links", len(expired_df), help="Invalid or expired links")
            st.markdown('</div>', unsafe_allow_html=True)

        # Filter and Display Results
        with st.expander("🔎 View and Filter Results", expanded=True):
            status_filter = st.multiselect("Filter by Status", options=["Active", "Expired"], default=["Active"], help="Select statuses to display")
            filtered_df = df[df['Status'].isin(status_filter)] if status_filter else df
            st.dataframe(
                filtered_df,
                column_config={
                    "Group Link": st.column_config.LinkColumn("Invite Link", display_text="Join Group", help="Click to join"),
                    "Logo URL": st.column_config.LinkColumn("Logo", help="Click to view logo")
                },
                height=400,
                use_container_width=True
            )

        # Download Buttons
        col_dl1, col_dl2 = st.columns(2)
        with col_dl1:
            csv_active = active_df.to_csv(index=False)
            st.download_button(
                "📥 Download Active Groups",
                csv_active,
                "active_groups.csv",
                "text/csv",
                use_container_width=True
            )
        with col_dl2:
            csv_all = df.to_csv(index=False)
            st.download_button(
                "📥 Download All Results",
                csv_all,
                "all_groups.csv",
                "text/csv",
                use_container_width=True
            )
    else:
        st.info("Select an input method and start validating WhatsApp group links!", icon="ℹ️")

if __name__ == "__main__":
    main()
