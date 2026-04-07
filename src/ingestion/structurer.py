# src/ingestion/structurer.py

import json
from pathlib import Path
from bs4 import BeautifulSoup
import re
from config.settings import DATA_RAW_SYMPTOM_DIR, DATA_RAW_CONDITIONS_DIR, DATA_PROCESSED_DIR
from src.utils.helpers import clean_text, infer_risk_level
from tqdm import tqdm


def extract_figure_images(soup: BeautifulSoup) -> list:
    """Extract high-quality NHS images with captions + alt text + best resolution"""

    def get_best_src(img_tag):
        """Pick highest resolution from srcset if available"""
        srcset = img_tag.get("srcset")

        if srcset:
            try:
                candidates = []
                for item in srcset.split(","):
                    parts = item.strip().split(" ")
                    if len(parts) == 2 and parts[1].endswith("w"):
                        url = parts[0]
                        width = int(parts[1].replace("w", ""))
                        candidates.append((width, url))

                if candidates:
                    return sorted(candidates, key=lambda x: x[0], reverse=True)[0][1]
            except:
                pass

        return img_tag.get("src") or img_tag.get("data-src")

    images = []

    for figure in soup.find_all("figure", class_=re.compile("nhsuk-image")):
        img = figure.find("img")
        if not img:
            continue

        src = get_best_src(img)
        if not src:
            continue

        # Convert relative → absolute
        if src.startswith("/"):
            src = "https://www.nhs.uk" + src

        if not src.startswith("http"):
            continue

        caption_tag = figure.find("figcaption")
        caption = clean_text(caption_tag.get_text()) if caption_tag else ""

        alt_text = clean_text(img.get("alt", ""))

        # Combine caption + alt intelligently
        full_caption = caption or alt_text
        if caption and alt_text and alt_text not in caption:
            full_caption = f"{caption} ALT({alt_text})"

        images.append({
            "url": src,
            "caption": full_caption
        })

    # Deduplicate
    seen = set()
    unique_images = []
    for img in images:
        if img["url"] not in seen:
            seen.add(img["url"])
            unique_images.append(img)

    return unique_images[:5]


def extract_key_sections(soup: BeautifulSoup, page_type: str, url: str):
    sections = {
        "condition": "",
        "overview": "",
        "symptoms": [],
        "causes": [],
        "self_care": [],
        "treatment": [],
        "prevention": [],
        "lifestyle_tips": [],
        "when_to_seek_help": [],
        "last_reviewed": "",
        "next_review_due": "",
        "images": []  # ✅ NEW
    }

    # Title
    h1 = soup.find("h1")
    if h1:
        sections["condition"] = clean_text(h1.get_text())

    # Extract images early
    sections["images"] = extract_figure_images(soup)

    # Review dates
    for p in soup.find_all("p"):
        text = p.get_text()
        if "Page last reviewed:" in text:
            match = re.search(r"Page last reviewed:\s*(\d{1,2}\s+\w+\s+\d{4})", text)
            if match:
                sections["last_reviewed"] = match.group(1)
        if "Next review due:" in text:
            match = re.search(r"Next review due:\s*(\d{1,2}\s+\w+\s+\d{4})", text)
            if match:
                sections["next_review_due"] = match.group(1)

    # Section extraction
    for h2 in soup.find_all(["h2", "h3"]):
        heading = clean_text(h2.get_text()).lower()
        content = []

        elem = h2.find_next_sibling()
        while elem and elem.name not in ["h2", "h3"]:
            if elem.name in ["p", "ul", "ol"]:
                if elem.name in ["ul", "ol"]:
                    items = [clean_text(li.get_text()) for li in elem.find_all("li") if clean_text(li.get_text())]
                    content.extend(items)
                else:
                    text = clean_text(elem.get_text())
                    if text and len(text) > 3:
                        content.append(text)
            elem = elem.find_next_sibling()

        if not content:
            continue

        if any(k in heading for k in ["symptom", "sign"]):
            sections["symptoms"].extend(content)

        elif any(k in heading for k in ["self-care", "do", "don't", "relief", "ease"]):
            sections["self_care"].extend(content)

        elif any(k in heading for k in ["when to", "urgent", "emergency", "call", "999", "a&e", "seek"]):
            sections["when_to_seek_help"].extend(content)

        elif any(k in heading for k in ["cause", "why"]):
            sections["causes"].extend(content)

        elif any(k in heading for k in ["treat", "medicine", "pharmacist"]):
            sections["treatment"].extend(content)
            sections["self_care"].extend(content)

        elif any(k in heading for k in ["prevent", "avoid", "lifestyle", "diet", "exercise"]):
            sections["prevention"].extend(content)
            sections["lifestyle_tips"].extend(content)

    return sections


def map_to_schema(sections: dict, url: str, page_type: str):
    return {
        "condition": sections["condition"] or "Unknown",
        "page_type": page_type,
        "overview": sections["overview"],
        "symptoms": list(dict.fromkeys(sections["symptoms"]))[:12],
        "causes": list(dict.fromkeys(sections["causes"]))[:10],
        "self_care": list(dict.fromkeys(sections["self_care"]))[:20],
        "treatment": list(dict.fromkeys(sections["treatment"]))[:15],
        "prevention": list(dict.fromkeys(sections["prevention"]))[:10],
        "lifestyle_tips": list(dict.fromkeys(sections["lifestyle_tips"]))[:10],
        "when_to_seek_help": list(dict.fromkeys(sections["when_to_seek_help"]))[:15],
        "images": sections.get("images", []),  # ✅ ONLY used in JSON
        "last_reviewed": sections["last_reviewed"],
        "next_review_due": sections["next_review_due"],
        "risk_level": infer_risk_level(" ".join(str(v) for v in sections.values()).lower()),
        "source_url": url
    }



def build_symptom_lexicon(entries: list) -> list[str]:
    """Collect unique symptom phrases from all structured entries."""
    symptoms_set = set()
    for entry in entries:
        for symptom in entry.get("symptoms", []):
            if isinstance(symptom, str) and symptom.strip():
                symptoms_set.add(symptom.strip())
    return sorted(list(symptoms_set))

def run_structuring():
    DATA_PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    output_file = DATA_PROCESSED_DIR / "nhs_structured.jsonl"
    json_output = DATA_PROCESSED_DIR / "nhs_structured.json"
    lexicon_file = DATA_PROCESSED_DIR / "symptom_lexicon.json"
    
    all_entries = []
    if output_file.exists():
        output_file.unlink()
    
    count = 0
    for raw_dir, page_type in [
        (DATA_RAW_SYMPTOM_DIR, "symptom"),
        (DATA_RAW_CONDITIONS_DIR, "condition")
    ]:
        for file in tqdm(list(raw_dir.glob("*.json")), desc=f"Structuring {page_type}s"):
            try:
                with open(file, encoding="utf-8") as f:
                    page = json.load(f)
                soup = BeautifulSoup(page["raw_content"], "html.parser")
                sections = extract_key_sections(soup, page.get("page_type", page_type), page["url"])
                entry = map_to_schema(sections, page["url"], page.get("page_type", page_type))
                
                # JSONL (no images)
                entry_no_images = {k: v for k, v in entry.items() if k != "images"}
                with open(output_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry_no_images, ensure_ascii=False) + "\n")
                
                all_entries.append(entry)
                count += 1
            except Exception as e:
                print(f"⚠️ Failed to process {file}: {e}")
                continue
    
    # Save full JSON with images
    with open(json_output, "w", encoding="utf-8") as f:
        json.dump(all_entries, f, indent=2, ensure_ascii=False)
    
    # === NEW: Auto-create symptom lexicon ===
    lexicon = build_symptom_lexicon(all_entries)
    with open(lexicon_file, "w", encoding="utf-8") as f:
        json.dump(lexicon, f, ensure_ascii=False)
    print(f"✅ Created symptom_lexicon.json with {len(lexicon)} unique symptoms")
    
    print(f"✅ Structured {count} entries (with images in JSON only)")
    return count

