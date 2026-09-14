import tkinter as tk
from tkinter import messagebox, ttk
import threading
import time
import urllib3
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# -------------------------------
# Constants
# -------------------------------
FALLBACK_SCI_HUB_DOMAINS = [
    "https://sci-hub.ru",
    "https://sci-hub.st",
    "https://sci-hub.su",
    "https://sci-hub.box",
    "https://sci-hub.red",
    "https://sci-hub.al",
    "https://sci-hub.mk",
    "https://sci-hub.se",
    "https://sci-hub.ee",
    "https://sci-hub.lu",
    "https://sci-hub.ren",
    "https://sci-hub.shop",
    "https://sci-hub.vg"
]


def get_sci_hub_domains():
    try:
        page = requests.get("https://www.sci-hub.pub/", timeout=10, verify=False, headers=browser_headers())
        page.raise_for_status()
        soup = BeautifulSoup(page.text, "html.parser")
        links = []
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if href.startswith("https://") and "sci-hub" in href:
                normal = href.rstrip("/")
                if normal not in links:
                    links.append(normal)
        if links:
            return links
    except Exception as e:
        update_status(f"[!] Live mirror refresh failed: {e}")
    return FALLBACK_SCI_HUB_DOMAINS


SCI_HUB_DOMAINS = get_sci_hub_domains()

# -------------------------------
# UI Setup
# -------------------------------
root = tk.Tk()
root.title("Paper Finder & Downloader")
root.geometry("700x400")

frame = tk.Frame(root)
frame.pack(padx=20, pady=20, fill="x")

entry_label = tk.Label(frame, text="Enter DOI or Title:")
entry_label.pack(anchor="w")

entry_input = tk.Entry(frame, font=("Arial", 14))
entry_input.pack(fill="x", pady=5)

btn_search = tk.Button(frame, text="Search & Download", command=lambda: threading.Thread(target=main_search).start())
btn_search.pack(pady=10)

text_output = tk.Text(root, wrap="word", height=10)
text_output.pack(fill="both", expand=True, padx=20)

progress = ttk.Progressbar(root, mode="indeterminate")
progress.pack(fill="x", padx=20, pady=5)

pdf_url = tk.StringVar()

btn_download = tk.Button(root, text="Download PDF", command=lambda: threading.Thread(target=download_pdf).start())
btn_download.pack(pady=5)

# -------------------------------
# Helper Functions
# -------------------------------

def update_status(msg):
    text_output.insert("end", msg + "\n")
    text_output.see("end")

def resolve_title_to_doi(title):
    headers = {"User-Agent": "PaperFinderApp (mailto:youremail@example.com)"}

    # Try CrossRef
    try:
        res = requests.get("https://api.crossref.org/works", params={"query": title, "rows": 1}, headers=headers, timeout=10)
        res.raise_for_status()
        data = res.json()
        if data.get("message") and data["message"].get("items"):
            return data["message"]["items"][0].get("DOI")
    except Exception as e:
        update_status(f"[!] CrossRef search failed: {e}")

    # Fallback to OA.mg
    try:
        res = requests.get("https://api.oa.mg/v1/papers/search", params={"q": title}, headers=headers, timeout=10)
        res.raise_for_status()
        data = res.json()
        if data and isinstance(data, list) and 'doi' in data[0]:
            return data[0]['doi']
    except Exception as e:
        update_status(f"[!] OA.mg fallback failed: {e}")

    return None

def browser_headers(referrer=None):
    return {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": referrer or "https://sci-hub.st/",
        "Upgrade-Insecure-Requests": "1",
        "Connection": "keep-alive",
    }


def extract_pdf_from_html(html, base_url):
    soup = BeautifulSoup(html, "html.parser")
    iframe = soup.find("iframe")
    if iframe and iframe.get("src"):
        pdf_link = iframe["src"]
        if pdf_link.startswith("//"):
            pdf_link = "https:" + pdf_link
        elif pdf_link.startswith("/"):
            pdf_link = urljoin(base_url, pdf_link)
        return pdf_link

    pdf_link = None
    for tag in soup.select("embed[src], object[data], a[href]"):
        src = tag.get("src") or tag.get("data") or tag.get("href")
        if src and (src.lower().endswith(".pdf") or "/pdf" in src.lower() or ".pdf?" in src.lower()):
            pdf_link = src
            break

    if pdf_link and pdf_link.startswith("//"):
        pdf_link = "https:" + pdf_link
    elif pdf_link and pdf_link.startswith("/"):
        pdf_link = urljoin(base_url, pdf_link)

    return pdf_link


def browser_search_sci_hub(domain, query):
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        update_status("[!] Playwright is not installed. Install it with: pip install playwright")
        return None

    try:
        url = f"{domain}/{query}"
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            page = browser.new_page(viewport={"width": 1440, "height": 1200})
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(2)

            for selector in ["text=No", "button:has-text(\"No\")", "text=Continue", "button:has-text(\"Continue\")"]:
                try:
                    page.click(selector, timeout=5000)
                    time.sleep(2)
                    break
                except Exception:
                    pass

            page.wait_for_load_state("networkidle", timeout=20000)
            html = page.content()
            pdf_link = extract_pdf_from_html(html, domain)
            browser.close()

            if pdf_link:
                return pdf_link
    except Exception as e:
        update_status(f"[!] Browser fallback failed for {domain}: {e}")
    return None


def search_sci_hub(query):
    headers = browser_headers()
    for domain in SCI_HUB_DOMAINS:
        try:
            url = f"{domain}/{query}"
            res = requests.get(url, headers=headers, timeout=15, allow_redirects=True, verify=False)
            res.raise_for_status()
            pdf_link = extract_pdf_from_html(res.text, domain)
            if pdf_link:
                return {
                    "title": f"Found via Sci-Hub at {domain}",
                    "authors": ["Unknown"],
                    "abstract": "PDF via Sci-Hub.",
                    "pdf_url": pdf_link
                }
        except Exception as e:
            update_status(f"[!] {domain} failed: {e}")
            browser_pdf = browser_search_sci_hub(domain, query)
            if browser_pdf:
                return {
                    "title": f"Found via browser fallback at {domain}",
                    "authors": ["Unknown"],
                    "abstract": "PDF via Sci-Hub browser fallback.",
                    "pdf_url": browser_pdf
                }
            continue
    return None

def main_search():
    global SCI_HUB_DOMAINS
    progress.start()
    text_output.delete("1.0", tk.END)
    SCI_HUB_DOMAINS = get_sci_hub_domains()
    update_status(f"[i] Using {len(SCI_HUB_DOMAINS)} live Sci-Hub mirrors.")
    user_input = entry_input.get().strip()

    if not user_input:
        update_status("Please enter a DOI or title.")
        progress.stop()
        return

    query = user_input
    if not user_input.lower().startswith("10."):  # Likely a title
        update_status("[i] Resolving title to DOI...")
        resolved_doi = resolve_title_to_doi(user_input)
        if not resolved_doi:
            update_status("[!] Could not resolve title to DOI.")
            progress.stop()
            return
        query = resolved_doi
        update_status(f"[+] Resolved DOI: {query}")

    update_status("[i] Searching Sci-Hub...")
    paper = search_sci_hub(query)
    if paper:
        update_status(f"Title: {paper['title']}")
        update_status(f"Authors: {', '.join(paper['authors'])}")
        update_status(f"Abstract: {paper['abstract']}")
        pdf_url.set(paper['pdf_url'])
        update_status("[+] PDF URL is ready.")
    else:
        update_status("[!] No PDF found on any Sci-Hub domain. This usually means the mirror list is stale or all available Sci-Hub hosts are blocked/unreachable.")

    progress.stop()

def download_pdf():
    url = pdf_url.get()
    if not url:
        messagebox.showerror("No PDF", "No PDF URL available to download.")
        return

    parsed = urlparse(url)
    base_domain = f"{parsed.scheme}://{parsed.netloc}"
    refs = [base_domain, "https://sci-hub.st/", "https://sci-hub.ru/"]

    try:
        update_status("Downloading PDF...")
        filename = entry_input.get().strip().replace("/", "_") + ".pdf"
        session = requests.Session()
        session.headers.update(browser_headers(refs[0]))

        last_error = None
        for referrer in refs:
            headers = browser_headers(referrer)
            session.headers.update(headers)
            try:
                res = session.get(url, headers=headers, stream=True, timeout=30, allow_redirects=True, verify=False)
                if res.status_code == 403:
                    last_error = Exception(f"403 Client Error: Forbidden for url: {url}")
                    update_status(f"[!] 403 from {referrer}; retrying with alternate headers...")
                    continue
                res.raise_for_status()
                with open(filename, "wb") as f:
                    for chunk in res.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                update_status(f"Download complete: {filename}")
                messagebox.showinfo("Success", f"Downloaded to {filename}")
                return
            except Exception as e:
                last_error = e
                update_status(f"[!] Download attempt failed: {e}")

        raise last_error or RuntimeError(f"Unable to download: {url}")
    except Exception as e:
        update_status(f"Download failed: {e}")
        messagebox.showerror("Error", str(e))

# -------------------------------
# Start GUI
# -------------------------------
root.mainloop()
