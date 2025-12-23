import os
import csv
import yaml
import time
import requests
import concurrent.futures
from urllib.parse import quote
from difflib import SequenceMatcher
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_FALSE_DIR = BASE_DIR / "data-false"
CONFIG_FILE = BASE_DIR / "config" / "venues_top.yaml"

HEADERS = {
    "User-Agent": "mailto:your_email@example.com"
}

def load_config():
    if not CONFIG_FILE.exists():
        print(f"Config file not found: {CONFIG_FILE}")
        return set(), set()

    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    top_confs = set(conf.lower() for conf in config.get('top_conferences', []))
    top_journals = set(jour.lower() for jour in config.get('top_journals', []))
    
    return top_confs, top_journals

def is_top_venue(venue_name, top_list):
    if not venue_name:
        return False
    v = venue_name.lower()
    for top in top_list:
        if top in v:
            return True
    return False

def calculate_similarity(a, b):
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

def search_openalex(title):
    encoded_title = quote(title)
    url = f"https://api.openalex.org/works?filter=title.search:{encoded_title}&per-page=5" 
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code == 200:
            data = response.json()
            results = data.get('results', [])
            
            if not results:
                return None
                
            best_match = None
            highest_similarity = 0.0
            threshold = 0.85 
            
            for result in results:
                result_title = result.get('display_name', '')
                similarity = calculate_similarity(title, result_title)
                
                if similarity > highest_similarity:
                    highest_similarity = similarity
                    best_match = result
            
            if highest_similarity >= threshold:
                return best_match
            else:
                pass
                
    except Exception as e:
        print(f"Error searching OpenAlex for '{title}': {e}")
        
    return None

def get_citations_from_openalex(work_id):
    citations_data = [] 
    short_id = work_id.split('/')[-1]
    page = 1
    per_page = 200 
    
    while True:
        url = f"https://api.openalex.org/works?filter=cites:{short_id}&per-page={per_page}&page={page}&select=publication_year,primary_location"
        
        try:
            response = requests.get(url, headers=HEADERS, timeout=20)
            if response.status_code == 200:
                data = response.json()
                results = data.get('results', [])
                if not results:
                    break
                
                citations_data.extend(results)
                meta = data.get('meta', {})
                count = meta.get('count', 0)
                if len(citations_data) >= count:
                    break
                
                page += 1
                time.sleep(0.5) 
            else:
                print(f"Error fetching citations: {response.status_code}")
                break
        except Exception as e:
            print(f"Error fetching citations: {e}")
            break
            
    return citations_data

def process_single_paper(title, top_confs, top_journals):
    paper = search_openalex(title)
    
    if not paper:
        return None
    work_id = paper.get('id')
    citation_count = paper.get('cited_by_count', 0)
    if citation_count == 0:
        return {
            'paperId': work_id,
            'citationCount': 0,
            'top_conf_citations': 0,
            'top_journal_citations': 0,
            'year_counts': {y: 0 for y in range(2014, 2025)}
        }

    citing_works = get_citations_from_openalex(work_id)
    
    top_conf_count = 0
    top_journal_count = 0
    year_counts = {y: 0 for y in range(2014, 2025)}
    
    for work in citing_works:
        year = work.get('publication_year')
        if year and 2014 <= year <= 2024:
            year_counts[year] += 1
            
        loc = work.get('primary_location') or {}
        source = loc.get('source') or {}
        display_name = source.get('display_name')
        
        if display_name:
            if is_top_venue(display_name, top_confs):
                top_conf_count += 1
            elif is_top_venue(display_name, top_journals):
                top_journal_count += 1
                
    return {
        'paperId': work_id, 
        'citationCount': citation_count,
        'top_conf_citations': top_conf_count,
        'top_journal_citations': top_journal_count,
        'year_counts': year_counts
    }

def process_false_files():
    top_confs, top_journals = load_config()
    
    if not DATA_FALSE_DIR.exists():
        print(f"False data directory not found: {DATA_FALSE_DIR}")
        return

    txt_files = [f for f in os.listdir(DATA_FALSE_DIR) if f.endswith('.txt')]
    
    for txt_file in txt_files:
        print(f"\nProcessing false file: {txt_file}")
        txt_path = DATA_FALSE_DIR / txt_file
        csv_file = txt_file.replace('.txt', '.csv')
        csv_path = DATA_DIR / csv_file
        
        if not csv_path.exists():
            print(f"Warning: Corresponding CSV file {csv_file} not found.")
            continue
            
        with open(txt_path, 'r', encoding='utf-8') as f:
            titles_to_search = [line.strip() for line in f.readlines() if line.strip()]
            
        if not titles_to_search:
            print("No titles to search in this file.")
            continue
            
        print(f"Found {len(titles_to_search)} titles to retry with OpenAlex.")
        
        rows = []
        fieldnames = []
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            rows = list(reader)
        
        titles_found = []
        max_workers = 5
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_title = {
                executor.submit(process_single_paper, title, top_confs, top_journals): title
                for title in titles_to_search
            }
            
            for future in concurrent.futures.as_completed(future_to_title):
                title = future_to_title[future]
                try:
                    result = future.result()
                    if result:
                        print(f"  [✓] Found in OpenAlex: {title[:40]}...")
                        titles_found.append(title)
                        for row in rows:
                            if row['title'].strip() == title.strip():
                                row['paperId'] = result['paperId']
                                row['citationCount'] = result['citationCount']
                                row['top_conf_citations'] = result['top_conf_citations']
                                row['top_journal_citations'] = result['top_journal_citations']
                                for year, count in result['year_counts'].items():
                                    row[f'citations_{year}'] = count
                                break
                    else:
                        print(f"  [x] Not found in OpenAlex: {title[:40]}...")
                except Exception as e:
                    print(f"Error processing {title}: {e}")
        
        if titles_found:
            print(f"Updating {csv_file} with {len(titles_found)} new records...")
            with open(csv_path, 'w', encoding='utf-8', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            remaining_titles = [t for t in titles_to_search if t not in titles_found]
            with open(txt_path, 'w', encoding='utf-8') as f:
                for t in remaining_titles:
                    f.write(f"{t}\n")
            print(f"Removed found titles from {txt_file}. Remaining: {len(remaining_titles)}")
        else:
            print("No new papers found.")

if __name__ == "__main__":
    process_false_files()
