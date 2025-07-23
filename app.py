# group_links_validator.py

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

# --- Streamlit Configuration ---
st.set_page_config(
    page_title="WhatsApp Link Validator",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Constants ---
WHATSAPP_DOMAIN = "https://chat.whatsapp.com/"
IMAGE_PATTERN = re.compile(r'https:\/\/pps\.whatsapp\.net\/.*\.jpg\?[^&]*&[^&]+')
GOOGLE_SEARCH_URL = "https://www.google.com/search"

# --- Initialize User Agent ---
try:
    ua = UserAgent()
    BASE_USER_AGENT = ua.random
except Exception:
    # Fallback User-Agent if fake-useragent fails
    BASE_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36"

# --- Custom CSS for enhanced UI ---
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
    .warning-note {
        background-color: #fff3cd;
        color: #856404;
        padding: 10px;
        border-radius: 5px;
        border: 1px solid #ffeaa7;
        margin-top: 10px;
        font-size: 0.9em;
    }
    </style>
""", unsafe_allow_html=True)

# --- Helper Functions ---

def get_headers():
    """Generate headers with a User-Agent."""
    return {
        "User-Agent": BASE_USER_AGENT,
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

def is_internal_link(base_url, link_url):
    """Check if a link is internal to the base domain."""
    try:
        base_parsed = urlparse(base_url)
        link_parsed = urlparse(link_url)
        # Compare network locations (netloc) after removing 'www.' for consistency
        base_netloc = base_parsed.netloc.replace('www.', '')
        link_netloc = link_parsed.netloc.replace('www.', '')
        return base_netloc == link_netloc
    except:
        return False

def normalize_url(url):
    """Normalize a URL for consistent comparison (removes fragments)."""
    try:
        parsed = urlparse(url)
        normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        if parsed.query:
            # Sort query parameters for consistent key ordering
            params = sorted(parsed.query.split('&'))
            normalized += '?' + '&'.join(params)
        return normalized.lower()
    except:
        return url.lower()

def fetch_page(url, timeout=15):
    """Fetch a single page with error handling."""
    try:
        headers = get_headers()
        # Add a small random delay to be respectful
        time.sleep(random.uniform(0.1, 0.3))
        response = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        response.raise_for_status()
        return response
    except requests.exceptions.RequestException as e:
        st.warning(f"Failed to fetch {url}: {type(e).__name__}")
        return None

# --- Core Logic Functions ---

def validate_link(link):
    """Validate a WhatsApp group link and return details."""
    result = {
        "Group Name": "Expired",
        "Group Link": link,
        "Logo URL": "",
        "Status": "Expired"
    }
    try:
        headers = get_headers()
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
    except Exception:
        # Optional: Log specific validation errors for debugging
        # st.warning(f"Validation error for {link}: {e}")
        return result

def scrape_whatsapp_links(url):
    """Scrape WhatsApp group links from a single webpage."""
    try:
        headers = get_headers()
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        links = [a['href'] for a in soup.find_all('a', href=True) if a['href'].startswith(WHATSAPP_DOMAIN)]
        return links
    except Exception:
        # Optional: Log specific scraping errors for debugging
        # st.warning(f"Scraping error for {url}: {e}")
        return []

def google_search(query, num_pages):
    """Perform a custom Google search to fetch URLs from multiple pages."""
    search_results = []
    headers = get_headers()
    for page in range(num_pages):
        params = {
            "q": query,
            "start": page * 10
        }
        try:
            response = requests.get(GOOGLE_SEARCH_URL, headers=headers, params=params, timeout=20)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            for a in soup.find_all('a', href=True):
                href = a['href']
                if href.startswith('/url?q='):
                    # Extract the actual URL from Google's redirect link
                    url = href.split('/url?q=')[1].split('&')[0]
                    search_results.append(url)
            # Pause between requests to be respectful
            time.sleep(random.uniform(1, 2))
        except Exception as e:
            st.error(f"Error fetching Google page {page + 1}: {e}")
            break
    # Return unique URLs
    return list(set(search_results))

def load_links(uploaded_file):
    """Load WhatsApp group links from an uploaded TXT or CSV file."""
    try:
        if uploaded_file.name.endswith('.csv'):
            # Read the first column, assuming it contains the links
            df = pd.read_csv(uploaded_file, header=None)
            if not df.empty:
                 # Get the first column and convert to list of strings, stripping whitespace
                return df.iloc[:, 0].astype(str).str.strip().tolist()
            else:
                return []
        else:
            # For TXT files, read lines
            content = uploaded_file.read().decode('utf-8')
            # Handle different line endings (\r\n, \n)
            lines = content.replace('\r\n', '\n').split('\n')
            return [line.strip() for line in lines if line.strip()]
    except Exception as e:
        st.error(f"Error reading file: {e}")
        return []

def scrape_entire_website(base_url, max_pages, status_placeholder):
    """
    Crawl an entire website (limited by max_pages) to find WhatsApp links.
    Note: This uses requests/BeautifulSoup and cannot execute JavaScript.
    """
    if not is_valid_url(base_url):
        st.error("Invalid base URL provided.")
        return []

    found_links = set()
    visited_urls = set()
    # Use a queue for breadth-first crawling
    urls_to_visit = deque([base_url])
    pages_crawled = 0

    status_placeholder.info("Starting website crawl... (Note: Cannot execute JavaScript)")

    while urls_to_visit and (max_pages is None or pages_crawled < max_pages):
        current_url = urls_to_visit.popleft()
        normalized_url = normalize_url(current_url)

        # Skip if already visited
        if normalized_url in visited_urls:
            continue

        visited_urls.add(normalized_url)
        pages_crawled += 1

        status_placeholder.info(f"Crawling ({pages_crawled}/{max_pages if max_pages else '∞'}): {current_url[:70]}{'...' if len(current_url) > 70 else ''}")

        response = fetch_page(current_url, timeout=15)
        if response is None:
            continue

        try:
            soup = BeautifulSoup(response.text, 'html.parser')
        except Exception as e:
            st.warning(f"Error parsing HTML for {current_url}: {e}")
            continue

        # --- Extract Links ---
        page_links = soup.find_all('a', href=True)
        for link_tag in page_links:
            href = link_tag['href']
            # Resolve relative URLs to absolute URLs
            absolute_href = urljoin(current_url, href)

            # Check if it's a WhatsApp group link
            if absolute_href.startswith(WHATSAPP_DOMAIN):
                found_links.add(absolute_href)

            # Check if it's an internal link for further crawling
            # Only add if it's a valid URL, internal, and we haven't seen its normalized form
            elif is_internal_link(base_url, absolute_href) and is_valid_url(absolute_href):
                normalized_href = normalize_url(absolute_href)
                if normalized_href not in visited_urls:
                    urls_to_visit.append(absolute_href)

    status_placeholder.success(f"Crawling finished. Visited {pages_crawled} pages.")
    return list(found_links)

# --- Main Application Function ---

def main():
    """Main function for the WhatsApp Group Validator app."""
    st.markdown('<h1 class="main-title">WhatsApp Group Validator 🚀</h1>', unsafe_allow_html=True)
    st.markdown('<p class="subtitle">Search, scrape, or validate WhatsApp group links with ease</p>', unsafe_allow_html=True)

    # --- Sidebar for Settings ---
    with st.sidebar:
        st.header("⚙️ Settings")
        st.markdown("Customize your experience")
        input_method = st.selectbox(
            "Input Method",
            [
                "Search and Scrape from Google",
                "Enter Links Manually",
                "Upload File (TXT/CSV)",
                "Scrape Entire Website"
            ],
            help="Choose how to input links"
        )

        if input_method == "Search and Scrape from Google":
            num_pages = st.slider("Google Pages to Scrape", min_value=1, max_value=10, value=3, help="More pages = more links, longer time")
        elif input_method == "Scrape Entire Website":
            max_pages = st.number_input("Max Pages to Crawl", min_value=1, value=50, step=10,
                                        help="Limit crawling depth. Set higher for larger sites (slower).")

    # --- Clear Results Button ---
    if st.button("🗑️ Clear Results", use_container_width=True):
        if 'results' in st.session_state:
            del st.session_state['results']
        st.success("Results cleared!")

    # --- Input Section ---
    with st.container():
        results = []
        if input_method == "Search and Scrape from Google":
            st.subheader("🔍 Google Search & Scrape")
            keyword = st.text_input("Search Query:", placeholder="e.g., 'whatsapp group links site:example.com'", help="Use Google search operators for better results")
            if st.button("Search, Scrape, and Validate", use_container_width=True):
                if not keyword:
                    st.warning("Please enter a search query.")
                    return
                with st.spinner("Searching Google..."):
                    search_results = google_search(keyword, num_pages)
                if not search_results:
                    st.info("No search results found.")
                    return
                st.success(f"Found {len(search_results)} unique webpages. Scraping for WhatsApp links...")

                # Scrape links from search results
                all_links = []
                progress_bar = st.progress(0)
                total_results = len(search_results)
                for idx, url in enumerate(search_results):
                    links = scrape_whatsapp_links(url)
                    all_links.extend(links)
                    progress_bar.progress((idx + 1) / total_results)
                
                unique_links = list(set(all_links)) # Remove duplicates from scraping
                if not unique_links:
                    st.warning("No WhatsApp group links found on the scraped pages.")
                    return
                st.success(f"Scraped {len(unique_links)} unique WhatsApp group links. Validating...")

                # Validate the unique links
                progress_bar = st.progress(0)
                status_text = st.empty()
                total_links = len(unique_links)
                for i, link in enumerate(unique_links):
                    result = validate_link(link)
                    results.append(result)
                    progress_bar.progress((i + 1) / total_links)
                    status_text.text(f"Validating: {i + 1}/{total_links}")
                status_text.empty() # Clear status text when done

        elif input_method == "Scrape Entire Website":
            st.subheader("🕷️ Scrape Entire Website")
            base_url = st.text_input("Base Website URL:", placeholder="e.g., https://example.com", help="Start crawling from this page")
            
            st.markdown(
                '<div class="warning-note"><b>⚠️ Important:</b> This method uses <code>requests</code> and <code>BeautifulSoup</code>. '
                'It <b>cannot execute JavaScript</b>. It will only find links present in the initial HTML. '
                'Links that appear after a delay (like 5-10s) via JavaScript <b>will not be found</b>.</div>',
                unsafe_allow_html=True
            )

            if st.button("Crawl, Scrape, and Validate", use_container_width=True):
                if not base_url:
                    st.warning("Please enter a base website URL.")
                    return

                status_placeholder = st.empty()
                try:
                    unique_links = scrape_entire_website(base_url, max_pages, status_placeholder)
                except Exception as e:
                    st.error(f"An error occurred during crawling: {e}")
                    return

                if not unique_links:
                    st.warning("No WhatsApp group links found during the crawl.")
                    return

                st.success(f"Scraped {len(unique_links)} unique WhatsApp group links. Validating...")
                
                # Validate the unique links found by crawling
                progress_bar = st.progress(0)
                status_text = st.empty()
                total_links = len(unique_links)
                for i, link in enumerate(unique_links):
                    result = validate_link(link)
                    results.append(result)
                    progress_bar.progress((i + 1) / total_links)
                    status_text.text(f"Validating: {i + 1}/{total_links}")
                status_text.empty() # Clear status text when done

        elif input_method == "Enter Links Manually":
            st.subheader("📝 Manual Link Entry")
            links_text = st.text_area("Enter WhatsApp Links (one per line):", height=200, placeholder="https://chat.whatsapp.com/...")
            if st.button("Validate Links", use_container_width=True):
                # Handle different line endings robustly
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
                    status_text.text(f"Validating: {i + 1}/{total_links}")
                status_text.empty() # Clear status text when done

        elif input_method == "Upload File (TXT/CSV)":
            st.subheader("📥 File Upload")
            uploaded_file = st.file_uploader("Upload TXT or CSV", type=["txt", "csv"], help="One link per line (TXT) or in the first column (CSV)")
            if uploaded_file and st.button("Validate File Links", use_container_width=True):
                links = load_links(uploaded_file)
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
                    status_text.text(f"Validating: {i + 1}/{total_links}")
                status_text.empty() # Clear status text when done

        # Store results in session state if any were generated
        if results:
            st.session_state['results'] = results

    # --- Results Section ---
    if 'results' in st.session_state:
        df = pd.DataFrame(st.session_state['results'])
        active_df = df[df['Status'] == 'Active']
        expired_df = df[df['Status'] == 'Expired']

        # Summary Metrics
        st.subheader("📊 Results Summary")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown('<div class="metric-card">', unsafe_allow_html=True)
            st.metric("Total Links", len(df))
            st.markdown('</div>', unsafe_allow_html=True)
        with col2:
            st.markdown('<div class="metric-card">', unsafe_allow_html=True)
            st.metric("Active Links", len(active_df))
            st.markdown('</div>', unsafe_allow_html=True)
        with col3:
            st.markdown('<div class="metric-card">', unsafe_allow_html=True)
            st.metric("Expired Links", len(expired_df))
            st.markdown('</div>', unsafe_allow_html=True)

        # Filter and Display Results
        with st.expander("🔎 View and Filter Results", expanded=True):
            status_filter = st.multiselect("Filter by Status", options=["Active", "Expired"], default=["Active"])
            # Apply filter if selections are made, otherwise show all
            filtered_df = df[df['Status'].isin(status_filter)] if status_filter else df
            
            st.dataframe(
                filtered_df,
                column_config={
                    "Group Link": st.column_config.LinkColumn("Invite Link", display_text="Join Group"),
                    "Logo URL": st.column_config.LinkColumn("Group Logo", display_text="🖼️")
                },
                height=400,
                use_container_width=True
            )

        # Download Buttons
        col_dl1, col_dl2 = st.columns(2)
        with col_dl1:
            csv_active = active_df.to_csv(index=False)
            st.download_button(
                "📥 Download Active Groups (CSV)",
                csv_active,
                "active_whatsapp_groups.csv",
                "text/csv",
                use_container_width=True
            )
        with col_dl2:
            csv_all = df.to_csv(index=False)
            st.download_button(
                "📥 Download All Results (CSV)",
                csv_all,
                "all_whatsapp_groups.csv",
                "text/csv",
                use_container_width=True
            )
    else:
        st.info("👈 Select an input method from the sidebar and start validating!", icon="ℹ️")

if __name__ == "__main__":
    main()
