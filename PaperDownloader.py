import tkinter as tk
from tkinter import messagebox, ttk
import threading
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# -------------------------------
# Constants
# -------------------------------
SCI_HUB_DOMAINS = [
    "https://sci-hub.ru",
    "https://sci-hub.se",
    "https://sci-hub.st",
    "https://sci-hub.box",
    "https://sci-hub.red",
    "https://sci-hub.al",
    "https://sci-hub.ee",
    "https://sci-hub.lu",
    "https://sci-hub.ren",
    "https://sci-hub.shop",
    "https://sci-hub.vg"
]

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

def search_sci_hub(query):
    headers = {"User-Agent": "Mozilla/5.0"}
    for domain in SCI_HUB_DOMAINS:
        try:
            url = f"{domain}/{query}"
            res = requests.get(url, headers=headers, timeout=10)
            res.raise_for_status()
            soup = BeautifulSoup(res.content, "html.parser")
            iframe = soup.find("iframe")
            if iframe and iframe.get("src"):
                pdf_link = iframe["src"]
                if pdf_link.startswith("//"):
                    pdf_link = "https:" + pdf_link
                elif pdf_link.startswith("/"):
                    pdf_link = urljoin(domain, pdf_link)
                return {
                    "title": f"Found via Sci-Hub at {domain}",
                    "authors": ["Unknown"],
                    "abstract": "PDF via Sci-Hub.",
                    "pdf_url": pdf_link
                }
        except Exception as e:
            update_status(f"[!] {domain} failed: {e}")
            continue
    return None

def main_search():
    progress.start()
    text_output.delete("1.0", tk.END)
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
        update_status("[!] No PDF found on any Sci-Hub domain.")

    progress.stop()

def download_pdf():
    url = pdf_url.get()
    if not url:
        messagebox.showerror("No PDF", "No PDF URL available to download.")
        return

    try:
        update_status("Downloading PDF...")
        filename = entry_input.get().strip().replace("/", "_") + ".pdf"
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, stream=True)
        res.raise_for_status()
        with open(filename, "wb") as f:
            for chunk in res.iter_content(chunk_size=8192):
                f.write(chunk)
        update_status(f"Download complete: {filename}")
        messagebox.showinfo("Success", f"Downloaded to {filename}")
    except Exception as e:
        update_status(f"Download failed: {e}")
        messagebox.showerror("Error", str(e))

# -------------------------------
# Start GUI
# -------------------------------
root.mainloop()
