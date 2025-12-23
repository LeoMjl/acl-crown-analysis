import pandas as pd
from openai import OpenAI
import time
import json
import os
import glob

# Configuration for API Key and Base URL
# Please replace 'YOUR_API_KEY' with your actual API key
API_KEY = "YOUR_API_KEY"
BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

client = OpenAI(
    api_key=API_KEY,
    base_url=BASE_URL,
)

# Define categories
CATEGORIES = [
    "Machine Learning (including Deep Learning)",
    "Representation Learning and Optimization",
    "Probability, Statistics, and Inference",
    "Natural Language Processing",
    "Computer Vision",
    "Multimodal Learning",
    "AI Foundations and Theory",
    "Reinforcement Learning and Decision Making",
    "Interpretability, Fairness, and Applied Systems"
]

def clean_title(title):
    if not isinstance(title, str):
        return str(title)
    return title.replace('\\', ' ').replace('"', "'").replace('\n', ' ').strip()

def get_classifications(titles):
    cleaned_titles = [clean_title(t) for t in titles]
    
    prompt = f"""
As an AI expert, please classify the following papers into one of the categories below.
Select strictly from the provided list:
{', '.join(CATEGORIES)}

Return the result in JSON format as follows:
{{
    "results": [
        {{"title": "Paper Title 1", "category": "Category Name"}},
        ...
    ]
}}

Note:
1. The "title" field in the JSON must match the provided title exactly (including symbols).
2. If the title contains LaTeX formulas or special characters, keep them as is. Do not escape or modify them to ensure valid JSON.

Papers to classify:
"""
    for i, title in enumerate(cleaned_titles):
        prompt += f"{i+1}. {title}\n"

    max_retries = 3
    for attempt in range(max_retries):
        try:
            completion = client.chat.completions.create(
                model="deepseek-v3",
                messages=[
                    {'role': 'user', 'content': prompt}
                ],
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            
            content = completion.choices[0].message.content
            
            try:
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0]
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0]
                
                parsed_data = json.loads(content)
                return parsed_data.get("results", [])
            except json.JSONDecodeError:
                print(f"JSON parsing failed (Attempt {attempt + 1}/{max_retries}), raw content: {content[:100]}...")
                
        except Exception as e:
            print(f"API call error (Attempt {attempt + 1}/{max_retries}): {e}")
        
        if attempt < max_retries - 1:
            wait_time = 2 * (attempt + 1)
            print(f"Waiting {wait_time} seconds before retrying...")
            time.sleep(wait_time)
            
    return []

def process_file(file_path):
    print(f"\n{'='*50}")
    print(f"Processing file: {os.path.basename(file_path)}")
    print(f"{'='*50}")
    
    print(f"Reading file {file_path}...")
    df = pd.read_csv(file_path)
    
    if 'ai_category' not in df.columns:
        df['ai_category'] = None

    pending_mask = df['ai_category'].isna()
    pending_indices = df[pending_mask].index.tolist()
    
    total_pending = len(pending_indices)
    print(f"Total papers pending classification: {total_pending}")
    
    if total_pending == 0:
        print("All papers in this file have been classified!")
        return

    batch_size = 5
    save_interval = 10 
    
    for i in range(0, total_pending, batch_size):
        current_batch_indices = pending_indices[i : i + batch_size]
        batch_titles = df.loc[current_batch_indices, 'title'].tolist()
        print(f"Processing {i+1} to {min(i+batch_size, total_pending)} (Progress: {i}/{total_pending})...")
        
        results = get_classifications(batch_titles)
        
        if results and len(results) > 0:
            title_to_category = {item['title']: item['category'] for item in results}
            
            for idx, title in zip(current_batch_indices, batch_titles):
                cleaned_title = clean_title(title)
                category = title_to_category.get(title)
                
                if not category:
                    category = title_to_category.get(cleaned_title)

                if not category:
                    try:
                        relative_index = current_batch_indices.index(idx)
                        if relative_index < len(results):
                            category = results[relative_index].get('category')
                    except ValueError:
                        pass
                
                if category:
                     df.at[idx, 'ai_category'] = category
        else:
            print(f"Warning: No valid results obtained for this batch.")
        
        if (i // batch_size + 1) % save_interval == 0:
            print("Saving intermediate results to source file...")
            df.to_csv(file_path, index=False)
            
        time.sleep(1)
        
    df.to_csv(file_path, index=False)
    print(f"File processing complete! Results updated in: {file_path}")

def main():
    data_dir = "./data"
    
    if not os.path.exists(data_dir):
        print(f"Data directory '{data_dir}' does not exist. Please create it and add your CSV files.")
        return

    csv_files = glob.glob(os.path.join(data_dir, "*.final.csv"))
    
    print(f"Found {len(csv_files)} conference files to check/process...")
    
    for file_path in csv_files:
        process_file(file_path)

    print("\nAll files processed!")

if __name__ == "__main__":
    main()
