import os
import csv
import yaml
import time
import requests
import concurrent.futures
from pathlib import Path

API_KEY = "YOUR_API_KEY_HERE"

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_FALSE_DIR = BASE_DIR / "data-false"
CONFIG_FILE = BASE_DIR / "config" / "venues_top.yaml"

HEADERS = {"x-api-key": API_KEY}

def request_with_retry(url, params=None, max_retries=5):
    for i in range(max_retries):
        try:
            response = requests.get(url, params=params, headers=HEADERS, timeout=15)
            if response.status_code == 200:
                return response
            elif response.status_code == 429:
                wait_time = 5 * (i + 1)
                print(f"Rate limit exceeded (429). Waiting {wait_time}s... (Attempt {i+1}/{max_retries})")
                time.sleep(wait_time)
                continue
            elif 500 <= response.status_code < 600:
                print(f"Server error ({response.status_code}). Retrying... (Attempt {i+1}/{max_retries})")
                time.sleep(2)
                continue
            else:
                return response
        except requests.exceptions.RequestException as e:
            print(f"Network error: {e}. Retrying... (Attempt {i+1}/{max_retries})")
            time.sleep(2)
            
    print(f"Failed to fetch {url} after {max_retries} attempts.")
    return None

def load_config():
    if not CONFIG_FILE.exists():
        print(f"Config file not found: {CONFIG_FILE}")
        return set(), set()

    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    top_confs = set(conf.lower() for conf in config.get('top_conferences', []))
    top_journals = set(jour.lower() for jour in config.get('top_journals', []))
    
    return top_confs, top_journals

def search_paper(title):
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {
        "query": title,
        "limit": 1,
        "fields": "paperId,title,year"
    }
    
    response = request_with_retry(url, params)
    
    if response and response.status_code == 200:
        data = response.json()
        if data.get('data'):
            return data['data'][0]
    elif response:
        print(f"Error searching paper: {response.status_code} - {response.text}")
        
    return None

def get_citations(paper_id):
    citations = []
    offset = 0
    limit = 1000
    total = 0
    
    detail_url = f"https://api.semanticscholar.org/graph/v1/paper/{paper_id}"
    r = request_with_retry(detail_url, params={"fields": "citationCount"})
    
    if r and r.status_code == 200:
        total = r.json().get('citationCount', 0)
    else:
        return [], 0

    if total == 0:
        return [], 0

    print(f"Fetching {total} citations for paper {paper_id}...")
    
    while True:
        url = f"https://api.semanticscholar.org/graph/v1/paper/{paper_id}/citations"
        params = {
            "fields": "year,venue",
            "offset": offset,
            "limit": limit
        }
        
        response = request_with_retry(url, params)
        
        if response and response.status_code == 200:
            data = response.json()
            batch = data.get('data', [])
            if not batch:
                break
            
            citations.extend(batch)
            offset += len(batch)
            
            if offset >= total or len(batch) < limit:
                break
            
            time.sleep(1.0)
        else:
            print(f"Error fetching citations page.")
            break
            
    return citations, total

def is_top_venue(venue_name, top_list):
    if not venue_name:
        return False
    v = venue_name.lower()
    for top in top_list:
        if top in v:
            return True
    return False

def process_single_row(row, top_confs, top_journals):
    title = row.get('title')
    if not title:
        return None, None

    paper_info = search_paper(title)
    
    if paper_info:
        paper_id = paper_info['paperId']
        row['paperId'] = paper_id
        
        citations, count = get_citations(paper_id)
        row['citationCount'] = count
        
        top_conf_count = 0
        top_journal_count = 0
        year_counts = {y: 0 for y in range(2014, 2025)}
        
        for cit in citations:
            citing_paper = cit.get('citingPaper', {})
            if not citing_paper:
                continue
                
            year = citing_paper.get('year')
            if year and 2014 <= year <= 2024:
                year_counts[year] += 1
            
            venue = citing_paper.get('venue')
            if is_top_venue(venue, top_confs):
                top_conf_count += 1
            elif is_top_venue(venue, top_journals):
                top_journal_count += 1
        
        row['top_conf_citations'] = top_conf_count
        row['top_journal_citations'] = top_journal_count
        for year in range(2014, 2025):
            row[f'citations_{year}'] = year_counts[year]
        
        return row, True
    else:
        return row, False

def process_files():
    top_confs, top_journals = load_config()
    
    if not DATA_DIR.exists():
        print(f"Data directory not found: {DATA_DIR}")
        return

    files = [f for f in os.listdir(DATA_DIR) if f.endswith('.csv')]
    
    for filename in files:
        file_path = DATA_DIR / filename
        false_file_path = DATA_FALSE_DIR / filename.replace('.csv', '.txt')
        
        DATA_FALSE_DIR.mkdir(parents=True, exist_ok=True)
        
        print(f"\nProcessing file: {filename}")
        
        not_found_papers = []
        fieldnames = []
        
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            rows = list(reader)
        
        if false_file_path.exists():
            with open(false_file_path, 'r', encoding='utf-8') as f:
                not_found_papers = [line.strip() for line in f.readlines()]

        total_rows = len(rows)
        batch_size = 10
        max_workers = 3
        
        indices_to_process = []
        for i, row in enumerate(rows):
            if row.get('title') and not (row.get('paperId') and row.get('citationCount')):
                indices_to_process.append(i)
        
        print(f"Total rows: {total_rows}, Rows to process: {len(indices_to_process)}")

        for i in range(0, len(indices_to_process), batch_size):
            batch_indices = indices_to_process[i:i + batch_size]
            
            print(f"Processing batch {i//batch_size + 1}/{(len(indices_to_process) + batch_size - 1)//batch_size} (Rows {batch_indices[0]+1}-{batch_indices[-1]+1})...")

            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_index = {
                    executor.submit(process_single_row, rows[idx], top_confs, top_journals): idx 
                    for idx in batch_indices
                }
                
                for future in concurrent.futures.as_completed(future_to_index):
                    idx = future_to_index[future]
                    try:
                        updated_row, found = future.result()
                        if updated_row:
                            rows[idx] = updated_row
                            title = updated_row.get('title')
                            
                            if found:
                                print(f"  [✓] Found: {title[:40]}...")
                                if title in not_found_papers:
                                    not_found_papers.remove(title)
                            else:
                                print(f"  [x] Not Found: {title[:40]}...")
                                if title not in not_found_papers:
                                    not_found_papers.append(title)
                    except Exception as exc:
                        print(f"Row {idx} generated an exception: {exc}")

            print(f"Saving progress after batch...")
            with open(file_path, 'w', encoding='utf-8', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            
            if not_found_papers:
                with open(false_file_path, 'w', encoding='utf-8') as f:
                    for t in not_found_papers:
                        f.write(f"{t}\n")
            
            time.sleep(1)

if __name__ == "__main__":
    process_files()
