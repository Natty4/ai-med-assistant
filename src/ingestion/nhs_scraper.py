# # src/ingestion/nhs_scraper.py


import requests
from bs4 import BeautifulSoup
from tqdm import tqdm
import time
import json
from pathlib import Path
from config.settings import (
    DATA_RAW_SYMPTOM_DIR, 
    DATA_RAW_CONDITIONS_DIR, 
    NHS_SYMPTOM_BASE_URL, 
    NHS_CONDITIONS_BASE_URL
)

def get_symptom_urls(limit: int = 50):
    url = NHS_SYMPTOM_BASE_URL
    return _get_urls_from_index(url, "/symptoms/", limit)

def get_condition_urls(limit: int = 800):
    url = NHS_CONDITIONS_BASE_URL
    return _get_urls_from_index(url, "/conditions/", limit)

def _get_urls_from_index(base_url: str, href_prefix: str, limit: int):
    headers = {"User-Agent": "PersonalMedicalAssistant/1.0"}
    resp = requests.get(base_url, headers=headers, timeout=15)
    soup = BeautifulSoup(resp.text, "html.parser")
    urls = []
    for a in soup.select(f'a[href^="{href_prefix}"]'):
        href = a.get("href")
        if href and "#" not in href:
            full = "https://www.nhs.uk" + href if not href.startswith("http") else href
            if full not in urls:
                urls.append(full)
    return urls[:limit]

def scrape_page(url: str, page_type: str):
    try:
        headers = {"User-Agent": "PersonalMedicalAssistant/1.0"}
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup.find_all(["nav", "footer", "aside", "script", "style"]):
            tag.decompose()
        title = soup.find("h1").get_text(strip=True) if soup.find("h1") else "Unknown"
        return {
            "url": url,
            "title": title,
            "page_type": page_type,
            "raw_content": str(soup)
        }
    except Exception as e:
        print(f"⚠️ Failed {url}: {e}")
        return None

def run_scrape_symptoms(limit: int = 1000, overwrite: bool = False):
    DATA_RAW_SYMPTOM_DIR.mkdir(parents=True, exist_ok=True)
    _run_scrape(get_symptom_urls, DATA_RAW_SYMPTOM_DIR, "symptom", limit, overwrite)

def run_scrape_conditions(limit: int = 800, overwrite: bool = False):
    DATA_RAW_CONDITIONS_DIR.mkdir(parents=True, exist_ok=True)
    _run_scrape(get_condition_urls, DATA_RAW_CONDITIONS_DIR, "condition", limit, overwrite)

def _run_scrape(url_getter, raw_dir: Path, page_type: str, limit: int, overwrite: bool):
    urls = url_getter(limit)
    print(f"🚀 Scraping {len(urls)} NHS {page_type} pages...")
    saved = skipped = 0
    for url in tqdm(urls, desc=f"Scraping {page_type}s"):
        filename = Path(url.rstrip("/")).name or "page"
        filepath = raw_dir / f"{filename}.json"
        if filepath.exists() and not overwrite:
            skipped += 1
            continue
        data = scrape_page(url, page_type)
        if data:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            saved += 1
        time.sleep(0.7)  # polite
    print(f"✅ {page_type.capitalize()} scraping completed. Saved: {saved} | Skipped: {skipped}\n")
    
