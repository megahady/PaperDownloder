import csv
import os
import re
import threading
import time
import tkinter as tk
import urllib3
import warnings
from tkinter import filedialog, messagebox, ttk

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings("ignore", category=urllib3.exceptions.InsecureRequestWarning)
try:
    requests.packages.urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except Exception:
    pass

LEGACY_SCI_HUB_DOMAINS = [
    "https://sci-hub.ru",
    "https://sci-hub.st",
    "https://sci-hub.se",
    "https://sci-hub.ee",
    "https://sci-hub.ren",
    "https://sci-hub.box",
    "https://sci-hub.red",
    "https://sci-hub.al",
    "https://sci-hub.lu",
    "https://sci-hub.shop",
    "https://sci-hub.vg"
]

FALLBACK_SCI_HUB_DOMAINS = [
    "https://sci-hub.ru",
    "https://sci-hub.st",
    "https://sci-hub.su",
    "https://sci-hub.box",
    "https://sci-hub.red",
    "https://sci-hub.al",
    "https://sci-hub.mk",
    "https://sci-hub.ee"
]


def combine_sci_hub_domains(live_domains=None):
    seen = set()
    combined = []
    for domain_list in [LEGACY_SCI_HUB_DOMAINS, live_domains or FALLBACK_SCI_HUB_DOMAINS, FALLBACK_SCI_HUB_DOMAINS]:
        for domain in domain_list:
            if domain not in seen:
                seen.add(domain)
                combined.append(domain)
    return combined


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
            return combine_sci_hub_domains(links)
    except Exception as e:
        update_status(f"[!] Live mirror refresh failed: {e}")
    return combine_sci_hub_domains()


SCI_HUB_DOMAINS = combine_sci_hub_domains()

root = tk.Tk()
root.title("Reference Paper Downloader")
root.geometry("1000x700")

frame = tk.Frame(root, padx=20, pady=20)
frame.pack(fill="x")

lbl_path = tk.Label(frame, text="Reference file (CSV, TXT, BibTeX, RIS, RefWorks):")
lbl_path.pack(anchor="w")

path_var = tk.StringVar()
entry_path = tk.Entry(frame, textvariable=path_var, font=("Arial", 12))
entry_path.pack(fill="x", pady=5)

button_row = tk.Frame(frame)
button_row.pack(fill="x", pady=6)

btn_select = tk.Button(button_row, text="Browse reference file", command=lambda: select_reference_file())
btn_select.pack(side="left", padx=(0, 8))

btn_start = tk.Button(button_row, text="Process and Download", command=lambda: threading.Thread(target=process_reference_file_thread, daemon=True).start())
btn_start.pack(side="left", padx=(0, 8))

btn_retry = tk.Button(button_row, text="Retry failed entries", command=lambda: threading.Thread(target=retry_failed_entries_thread, daemon=True).start())
btn_retry.pack(side="left", padx=(0, 8))

btn_export_csv = tk.Button(button_row, text="Export CSV report", command=lambda: export_results_csv())
btn_export_csv.pack(side="left")

status_box = tk.Text(root, wrap="word", height=8)
status_box.pack(fill="both", padx=20, pady=(0, 8), expand=False)

results_columns = ("Title", "Authors", "DOI", "Status", "File")
results_table = ttk.Treeview(root, columns=results_columns, show="headings", height=12)
for col in results_columns:
    results_table.heading(col, text=col)
    results_table.column(col, width=180, anchor="w")
results_table.pack(fill="both", expand=True, padx=20, pady=(0, 10))

progress = ttk.Progressbar(root, mode="indeterminate")
progress.pack(fill="x", padx=20, pady=(0, 10))


def update_status(msg):
    status_box.insert("end", msg + "\n")
    status_box.see("end")
    root.update_idletasks()


def select_reference_file():
    file_path = filedialog.askopenfilename(
        title="Select reference file",
        filetypes=[
            ("All supported files", "*.csv *.txt *.bib *.ris *.risx *.refworks *.txt"),
            ("CSV files", "*.csv"),
            ("Text files", "*.txt"),
            ("BibTeX files", "*.bib"),
            ("RIS files", "*.ris"),
            ("RefWorks files", "*.refworks"),
            ("All files", "*.*"),
        ],
    )
    if file_path:
        path_var.set(file_path)
        update_status(f"Selected file: {file_path}")


def browser_headers(referrer=None):
    return {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": referrer or "https://sci-hub.st/",
        "Upgrade-Insecure-Requests": "1",
    }


def extract_pdf_from_html(html, base_url):
    soup = BeautifulSoup(html, "html.parser")

    iframe = soup.find("iframe")
    if iframe and iframe.get("src"):
        src = iframe["src"]
        if src.startswith("//"):
            src = "https:" + src
        elif src.startswith("/"):
            src = urljoin(base_url, src)
        return src

    for tag in soup.select("embed[src], object[data], a[href]"):
        src = tag.get("src") or tag.get("data") or tag.get("href")
        if src and (src.lower().endswith(".pdf") or "/pdf" in src.lower() or ".pdf?" in src.lower()):
            if src.startswith("//"):
                src = "https:" + src
            elif src.startswith("/"):
                src = urljoin(base_url, src)
            return src

    return None


def search_crossref_pdf(doi):
    try:
        url = "https://api.crossref.org/works"
        res = requests.get(url, params={"query.bibliographic": doi, "rows": 1}, headers=browser_headers(), timeout=15)
        res.raise_for_status()
        data = res.json()
        items = data.get("message", {}).get("items", [])
        if not items:
            return None

        item = items[0]
        for link in item.get("link", []):
            if link.get("content-type", "").lower() == "application/pdf":
                return link.get("URL")

        pdf_url = item.get("URL")
        if pdf_url and pdf_url.lower().endswith(".pdf"):
            return pdf_url

        return None
    except Exception as e:
        update_status(f"[!] CrossRef fallback failed for {doi}: {e}")
        return None


def search_sci_hub(doi):
    for domain in SCI_HUB_DOMAINS:
        try:
            url = f"{domain}/{doi}"
            headers = browser_headers(domain)
            res = requests.get(url, headers=headers, timeout=15, allow_redirects=True, verify=False)
            res.raise_for_status()

            pdf_link = extract_pdf_from_html(res.text, domain)
            if pdf_link:
                update_status(f"[+] DOI found: {doi}")
                update_status(f"[+] PDF URL: {pdf_link}")
                return pdf_link

            update_status(f"[!] No PDF found on {domain} for {doi}")
        except Exception as e:
            update_status(f"[!] {domain} failed for {doi}: {e}")

    alt_pdf = search_crossref_pdf(doi)
    if alt_pdf:
        update_status(f"[+] Alternative PDF source found for {doi}: {alt_pdf}")
        return alt_pdf

    return None


def download_pdf(url, filename):
    try:
        headers = browser_headers()
        res = requests.get(url, headers=headers, stream=True, timeout=30, allow_redirects=True, verify=False)
        res.raise_for_status()

        with open(filename, "wb") as f:
            for chunk in res.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        return True
    except Exception as e:
        update_status(f"[!] Download failed for {url}: {e}")
        return False


def clean_doi(raw):
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    text = text.replace("https://doi.org/", "").replace("http://doi.org/", "")
    text = text.replace("doi:", "").replace("DOI:", "")
    text = text.strip("{}[]()\"'")
    text = text.split()[0]
    if text.lower().startswith("10."):
        return text
    return None


def find_doi_from_text(text):
    if not text:
        return None
    patterns = [
        r"10\.\d{4,9}/[-._;()/:A-Z0-9]+",
        r"DOI\s*[:=]\s*10\.\d{4,9}/[-._;()/:A-Z0-9]+",
        r"https?://(?:dx\.)?doi\.org/10\.\d{4,9}/[-._;()/:A-Z0-9]+",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return clean_doi(match.group(0))
    return None


def extract_record_doi(record):
    if isinstance(record, dict):
        for key in ["doi", "DOI", "Doi", "ID", "identifier", "Identifiers"]:
            if key in record:
                doi = clean_doi(record.get(key))
                if doi:
                    return doi
        for value in record.values():
            doi = find_doi_from_text(str(value))
            if doi:
                return doi
        return None
    return find_doi_from_text(str(record))


def parse_csv_file(file_path):
    records = []
    with open(file_path, "r", encoding="utf-8", errors="ignore", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames:
            for row in reader:
                records.append(row)
            return records
        f.seek(0)
        for line in f:
            if line.strip():
                records.append({"raw": line.strip()})
    return records


def parse_txt_file(file_path):
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()
    return [{"raw": text}]


def parse_bib_file(file_path):
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
    except Exception as e:
        raise RuntimeError(f"Could not open file: {e}")

    entries = []
    pos = 0
    while pos < len(text):
        start = text.find("@", pos)
        if start == -1:
            break
        type_start = start + 1
        while type_start < len(text) and text[type_start].isspace():
            type_start += 1
        type_end = type_start
        while type_end < len(text) and (text[type_end].isalpha() or text[type_end] == "_"):
            type_end += 1
        if type_end == type_start:
            pos = start + 1
            continue

        open_pos = text.find("{", type_end)
        if open_pos == -1:
            break

        depth = 1
        i = open_pos + 1
        while i < len(text) and depth > 0:
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    item = text[open_pos + 1:i]
                    fields = {}
                    j = 0
                    while j < len(item):
                        while j < len(item) and item[j].isspace():
                            j += 1
                        if j >= len(item):
                            break
                        if item[j] == ",":
                            j += 1
                            continue

                        key_start = j
                        while j < len(item) and (item[j].isalnum() or item[j] == "_"):
                            j += 1
                        key = item[key_start:j].strip()
                        if not key:
                            j += 1
                            continue

                        while j < len(item) and item[j].isspace():
                            j += 1
                        if j < len(item) and item[j] == "=":
                            j += 1
                            while j < len(item) and item[j].isspace():
                                j += 1
                            if j < len(item) and item[j] == "{":
                                val_depth = 1
                                value_start = j + 1
                                j += 1
                                while j < len(item) and val_depth > 0:
                                    if item[j] == "{":
                                        val_depth += 1
                                    elif item[j] == "}":
                                        val_depth -= 1
                                    j += 1
                                value = item[value_start:j - 1] if j > value_start else ""
                                fields[key] = value.strip()
                            elif j < len(item) and item[j] == '"':
                                j += 1
                                value_start = j
                                while j < len(item) and item[j] != '"':
                                    j += 1
                                value = item[value_start:j]
                                fields[key] = value.strip()
                                if j < len(item) and item[j] == '"':
                                    j += 1
                            else:
                                value_start = j
                                while j < len(item) and item[j] != ",":
                                    j += 1
                                fields[key] = item[value_start:j].strip()

                        while j < len(item) and item[j] != ",":
                            j += 1
                        if j < len(item) and item[j] == ",":
                            j += 1

                    entries.append(fields)
                    pos = i + 1
                    break
            i += 1

    if not entries:
        raise RuntimeError("No BibTeX entries were found.")

    return entries


def parse_ris_file(file_path):
    entries = []
    current = {}
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip():
                if current:
                    entries.append(current)
                    current = {}
                continue
            if len(line) >= 6 and line[2:6].strip() == "":
                continue
            if len(line) >= 6 and line[2:6].strip() and line[0:2].isalpha():
                tag = line[0:2].strip()
                value = line[6:].strip() if len(line) > 6 else ""
                if tag == "ER":
                    if current:
                        entries.append(current)
                        current = {}
                else:
                    current[tag] = value
    if current:
        entries.append(current)
    return entries


def parse_refworks_file(file_path):
    entries = []
    current = {}
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.rstrip("\n")
            if line.startswith("%0"):
                if current:
                    entries.append(current)
                    current = {}
                continue
            if "|" in line:
                parts = line.split("|", 1)
                if len(parts) == 2:
                    key, value = parts
                    current[key.strip()] = value.strip()
    if current:
        entries.append(current)
    return entries


def parse_reference_file(file_path):
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".csv":
        return parse_csv_file(file_path)
    if ext == ".bib":
        return parse_bib_file(file_path)
    if ext == ".ris":
        return parse_ris_file(file_path)
    if ext in (".refworks", ".txt"):
        if ext == ".refworks":
            return parse_refworks_file(file_path)
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
            if "@" in text and "bib" in file_path.lower():
                return parse_bib_file(file_path)
            if "TY  -" in text or "ER  -" in text:
                return parse_ris_file(file_path)
            if "|" in text:
                return parse_refworks_file(file_path)
            return parse_txt_file(file_path)
        except Exception:
            return parse_txt_file(file_path)
    return parse_txt_file(file_path)


def resolve_record_to_doi(record):
    if isinstance(record, dict):
        for key in ["doi", "DOI", "Doi", "DOI:", "identifier"]:
            if key in record:
                doi = clean_doi(record.get(key))
                if doi:
                    return doi

        for value in record.values():
            doi = clean_doi(value)
            if doi:
                return doi

        for value in record.values():
            doi = find_doi_from_text(str(value))
            if doi:
                return doi

        text_blob = " ".join(str(v) for v in record.values())
        return find_doi_from_text(text_blob)

    return extract_record_doi(record)


def resolve_title_to_doi(title):
    try:
        res = requests.get("https://api.crossref.org/works", params={"query.title": title, "rows": 1}, headers=browser_headers(), timeout=15)
        res.raise_for_status()
        data = res.json()
        items = data.get("message", {}).get("items", [])
        if items:
            doi = items[0].get("DOI")
            if doi:
                return doi
    except Exception as e:
        update_status(f"[!] CrossRef title resolution failed for '{title}': {e}")
    return None


def normalize_author_list(value):
    if value is None:
        return "Unknown"
    if isinstance(value, list):
        return "; ".join(str(v).strip() for v in value if str(v).strip()) or "Unknown"
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return "Unknown"
        text = text.replace(" and ", "; ")
        text = text.replace(" AND ", "; ")
        return text or "Unknown"
    return str(value)


def extract_title_and_authors(record):
    if not isinstance(record, dict):
        return "Unknown title", "Unknown"

    title = (
        record.get("title") or record.get("TI") or record.get("T1") or record.get("Title")
        or record.get("TITLE") or record.get("raw")
    )
    if isinstance(title, list):
        title = " ".join(str(x) for x in title if str(x).strip())
    if title is None:
        title = "Unknown title"

    authors = (
        record.get("author") or record.get("AU") or record.get("A1") or record.get("Author")
        or record.get("authors") or record.get("Authors")
    )
    if isinstance(authors, list):
        author_text = normalize_author_list(authors)
    else:
        author_text = normalize_author_list(authors)
    return str(title).strip() or "Unknown title", author_text or "Unknown"


def build_report(results):
    lines = []
    lines.append("Reference Download Report")
    lines.append("=" * 80)
    lines.append(f"Total records processed: {results['total_records']}")
    lines.append(f"Successful downloads: {results['successful']}")
    lines.append(f"Failed downloads: {results['failed']}")
    lines.append(f"Skipped records: {results['skipped']}")
    lines.append(f"Date: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    for item in results["items"]:
        lines.append(f"- Record: {item['label']}")
        lines.append(f"  DOI: {item['doi'] or 'N/A'}")
        lines.append(f"  Status: {item['status']}")
        lines.append(f"  Detail: {item['detail']}")
        lines.append(f"  File: {item['file'] or 'N/A'}")
        lines.append("")
    return "\n".join(lines)


def save_report(results):
    default_name = "reference_download_report.txt"
    report_path = filedialog.asksaveasfilename(
        title="Save report",
        initialfile=default_name,
        defaultextension=".txt",
        filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
    )
    if not report_path:
        return None
    report_text = build_report(results)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_text)
    return report_path


def export_results_csv():
    if not globals().get("last_results"):
        messagebox.showwarning("No results", "There are no results to export yet.")
        return
    target = filedialog.asksaveasfilename(
        title="Save CSV report",
        initialfile="reference_download_report.csv",
        defaultextension=".csv",
        filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
    )
    if not target:
        return
    with open(target, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Title", "Authors", "DOI", "Status", "Detail", "File"])
        for row in globals()["last_results"]["items"]:
            writer.writerow([
                row.get("title", ""),
                row.get("authors", ""),
                row.get("doi", ""),
                row.get("status", ""),
                row.get("detail", ""),
                row.get("file", ""),
            ])
    messagebox.showinfo("CSV saved", f"CSV report saved to:\n{target}")


def safe_cell_text(value, default=""):
    if value is None:
        return default
    return str(value)[:120]


def refresh_results_table(results):
    for row in results_table.get_children():
        results_table.delete(row)
    for item in results.get("items", []):
        results_table.insert("", "end", values=(
            safe_cell_text(item.get("title", "Unknown title"), "Unknown title"),
            safe_cell_text(item.get("authors", "Unknown"), "Unknown"),
            safe_cell_text(item.get("doi", "N/A"), "N/A"),
            safe_cell_text(item.get("status", "unknown"), "unknown"),
            safe_cell_text(item.get("file", ""), ""),
        ))


def initialize_sci_hub_domains():
    global SCI_HUB_DOMAINS
    try:
        sci_hub_domains = get_sci_hub_domains()
        if sci_hub_domains:
            SCI_HUB_DOMAINS = sci_hub_domains
            update_status(f"[i] Using {len(SCI_HUB_DOMAINS)} live Sci-Hub mirrors.")
        else:
            SCI_HUB_DOMAINS = FALLBACK_SCI_HUB_DOMAINS
            update_status("[i] Using fallback Sci-Hub mirror list.")
    except Exception as e:
        SCI_HUB_DOMAINS = FALLBACK_SCI_HUB_DOMAINS
        update_status(f"[!] Mirror refresh failed, using fallback list: {e}")


def process_reference_file_thread():
    global SCI_HUB_DOMAINS
    progress.start()
    status_box.delete("1.0", tk.END)
    initialize_sci_hub_domains()

    ref_path = path_var.get().strip()
    if not ref_path:
        update_status("Please select a reference file first.")
        progress.stop()
        return

    try:
        raw_records = parse_reference_file(ref_path)
        if not raw_records:
            raise RuntimeError("No records were found in the uploaded file.")

        output_dir = os.path.join(os.path.dirname(ref_path), "downloads")
        os.makedirs(output_dir, exist_ok=True)
        update_status(f"Downloads will be saved in: {output_dir}")

        results = {
            "total_records": 0,
            "successful": 0,
            "failed": 0,
            "skipped": 0,
            "items": []
        }

        for idx, record in enumerate(raw_records, start=1):
            if isinstance(record, dict):
                title, authors = extract_title_and_authors(record)
                label = title if title != "Unknown title" else (record.get("raw") or f"Record {idx}")
            else:
                title, authors = extract_title_and_authors(record)
                label = title or str(record)[:100] or f"Record {idx}"

            doi = resolve_record_to_doi(record)
            if not doi:
                if isinstance(record, dict):
                    title_candidate = record.get("title") or record.get("TI") or record.get("T1") or record.get("Title")
                    if title_candidate:
                        doi = resolve_title_to_doi(str(title_candidate))
                if not doi:
                    results["total_records"] += 1
                    results["skipped"] += 1
                    results["items"].append({
                        "label": label,
                        "title": title,
                        "authors": authors,
                        "doi": None,
                        "status": "skipped",
                        "detail": "No DOI found in record and title-based DOI resolution failed.",
                        "file": None,
                    })
                    update_status(f"[!] Record {idx}: no DOI found; skipped.")
                    continue

            results["total_records"] += 1
            update_status(f"\n--- Processing {idx}/{len(raw_records)}: {doi} ---")
            pdf_url = search_sci_hub(doi)

            if not pdf_url:
                results["failed"] += 1
                results["items"].append({
                    "label": label,
                    "title": title,
                    "authors": authors,
                    "doi": doi,
                    "status": "failed",
                    "detail": "No PDF found via Sci-Hub or alternative metadata lookup.",
                    "file": None,
                })
                update_status(f"[!] Could not find PDF for {doi}; skipped.")
            else:
                safe_name = doi.replace("/", "_").replace(".", "_") + ".pdf"
                full_path = os.path.join(output_dir, safe_name)
                success = download_pdf(pdf_url, full_path)
                if success:
                    results["successful"] += 1
                    results["items"].append({
                        "label": label,
                        "title": title,
                        "authors": authors,
                        "doi": doi,
                        "status": "downloaded",
                        "detail": "PDF downloaded successfully.",
                        "file": full_path,
                    })
                    update_status(f"[+] Saved: {full_path}")
                else:
                    results["failed"] += 1
                    results["items"].append({
                        "label": label,
                        "title": title,
                        "authors": authors,
                        "doi": doi,
                        "status": "failed",
                        "detail": "PDF download failed after lookup.",
                        "file": None,
                    })
                    update_status(f"[!] Download failed for {doi}; skipped.")

            if idx < len(raw_records):
                update_status("[i] Waiting 5 seconds before the next download...")
                time.sleep(5)

        globals()["last_results"] = results
        refresh_results_table(results)
        update_status("\n[i] Finished processing all records.")
        update_status(f"[i] Summary: {results['successful']} downloaded, {results['failed']} failed, {results['skipped']} skipped.")

        save_report_file = messagebox.askyesno("Save report", "Would you like to save the detailed download report?")
        if save_report_file:
            saved_path = save_report(results)
            if saved_path:
                update_status(f"[+] Report saved to: {saved_path}")
                messagebox.showinfo("Report saved", f"Report saved to:\n{saved_path}")
            else:
                update_status("[!] Report save cancelled by user.")
        messagebox.showinfo("Done", f"Finished processing {results['total_records']} records.")
    except Exception as e:
        update_status(f"[!] Error: {e}")
        messagebox.showerror("Error", str(e))
    finally:
        progress.stop()


def retry_failed_entries_thread():
    if not globals().get("last_results"):
        messagebox.showwarning("No results", "There are no previous results to retry.")
        return

    failed_only = [item for item in globals()["last_results"].get("items", []) if item.get("status") in {"failed", "skipped"} and item.get("doi")]
    if not failed_only:
        messagebox.showinfo("No retry items", "There are no failed or skipped records to retry.")
        return

    progress.start()
    update_status("[i] Retrying failed or skipped entries...")
    output_dir = os.path.join(os.path.dirname(path_var.get()), "downloads")
    os.makedirs(output_dir, exist_ok=True)

    for idx, item in enumerate(failed_only, start=1):
        doi = item.get("doi")
        if not doi:
            continue
        update_status(f"\n--- Retrying {idx}/{len(failed_only)}: {doi} ---")
        pdf_url = search_sci_hub(doi)
        if not pdf_url:
            item["status"] = "failed"
            item["detail"] = "Retry attempt failed; no PDF found." 
            update_status(f"[!] Retry failed for {doi}.")
        else:
            safe_name = doi.replace("/", "_").replace(".", "_") + ".pdf"
            full_path = os.path.join(output_dir, safe_name)
            success = download_pdf(pdf_url, full_path)
            if success:
                item["status"] = "downloaded"
                item["file"] = full_path
                item["detail"] = "PDF downloaded successfully on retry."
                update_status(f"[+] Retry succeeded: {full_path}")
            else:
                item["status"] = "failed"
                item["detail"] = "Retry download failed."
                update_status(f"[!] Retry failed for {doi}.")
        time.sleep(5)

    globals()["last_results"]["successful"] = sum(1 for item in globals()["last_results"]["items"] if item.get("status") == "downloaded")
    globals()["last_results"]["failed"] = sum(1 for item in globals()["last_results"]["items"] if item.get("status") == "failed")
    globals()["last_results"]["skipped"] = sum(1 for item in globals()["last_results"]["items"] if item.get("status") == "skipped")
    refresh_results_table(globals()["last_results"])
    update_status("[i] Retry process complete.")
    progress.stop()


root.mainloop()
