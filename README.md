# acl-crown-analysis
Natural Language Processing, Scientometrics, Conference Impact Analysis
# Project Scripts Documentation

With the explosion of Large Language Models (LLMs), the volume of submissions and acceptances at AI/NLP conferences has grown exponentially. However, this "boom" has raised widespread concerns in the community about the quality of peer review, academic integrity, and the dilution of impact. Existing studies tend to be qualitative discussions or localized evaluations, lacking long-term, cross-conference quantitative analysis.

We employed a multi-source retrieval strategy to ensure high data fidelity and coverage:
**Conference Metadata**: Raw paper lists (titles and publication years) were scraped directly from official conference websites and proceedings (e.g., ACL Anthology).
**Citation Records**: Detailed citation metrics were retrieved programmatically using:
*   **Semantic Scholar API**: Our primary source for fine-grained, time-sliced citation metadata (covering 99.3% of papers).
*   **OpenAlex API**: Used as a supplementary source to resolve missing entries and cross-validate statistics (covering the remaining 0.7%).

It is recommended to run the scripts in the following order to complete data acquisition, completion, and classification.

**Note**: The data currently in the `data` directory has already been processed. If you need to re-acquire it, please clear the contents of the files in `data` first, but make sure to keep the paper titles and publication years.

---

## 1. `fetch_from_Ss.py` (Semantic Scholar Data Acquisition)

### Function Introduction
This script is used to retrieve detailed citation data for papers from the Semantic Scholar API. It reads a CSV file containing paper titles, searches for paper IDs, retrieves citation counts, and calculates annual citation statistics as well as the number of citations from top conferences/journals.

### Input/Output
- **Input File**: CSV files in the `data/` directory (e.g., `AAAI.final.csv`). The file must contain a `title` column.
- **Configuration File**: `config/venues_top.yaml`, containing lists of top conferences (`top_conferences`) and top journals (`top_journals`).
- **Output Result**: Directly updates the CSV files in the `data/` directory, filling in the citation data columns.
- **Failure Record**: For papers not found, their titles are recorded in the corresponding `.txt` file in the `data-false/` directory (e.g., `AAAI.final.txt`).

### Key Features
- **Data Completion**: Automatically searches for papers with missing `paperId` and citation data.
- **Citation Statistics**: Calculates annual citation counts from 2014 to 2024.
- **Quality Analysis**: Counts citations from top conferences and journals based on the configuration file.
- **Multi-threaded Acceleration**: Uses a thread pool for concurrent processing to improve data scraping efficiency.

### Usage
1.  **Configure API Key**: Set the `API_KEY` (Semantic Scholar API Key) in the script.
2.  **Run Script**:
    ```bash
    python fetch_from_Ss.py
    ```

---

## 2. `fetch_from_openalex.py` (OpenAlex Data Acquisition - Supplementary Search)

### Function Introduction
This script serves as a supplementary tool to `fetch_from_Ss.py`, specifically designed to handle papers that Semantic Scholar failed to find. It reads the failure records from the `data-false/` directory, attempts to find these papers in the OpenAlex database, and retrieves the corresponding citation data.

### Input/Output
- **Input File**: `.txt` files in the `data-false/` directory (containing titles of papers not found).
- **Target File**: Original CSV files in the `data/` directory.
- **Output Result**:
    - Upon successfully finding a paper, it directly updates the CSV file in `data/`.
    - Successfully processed titles are removed from the `.txt` file in `data-false/`.

### Key Features
- **Secondary Search**: Performs a "cleanup" search for papers missed by Semantic Scholar.
- **Fuzzy Matching**: Uses a string similarity algorithm (SequenceMatcher) to match paper titles, improving precision.
- **Data Synchronization**: Automatically updates the original CSV file and clears failure records upon finding data.
- **Detailed Statistics**: Also supports annual citation statistics and top conference/journal citation analysis.

### Usage
1.  **Prerequisites**: Run `fetch_from_Ss.py` first to generate the failure list in the `data-false` directory.
2.  **Run Script**:
    ```bash
    python fetch_from_openalex.py
    ```

---

## 3. `classify_papers.py` (Paper Field Classification)

### Function Introduction
This script uses a Large Language Model (DeepSeek-V3) to automatically classify paper titles. It reads CSV files that have already acquired basic information and classifies them into 9 predefined AI fields (e.g., Machine Learning, Natural Language Processing, Computer Vision, etc.) based on the paper title.

### Input/Output
- **Input File**: CSV files in the `data/` directory.
- **Output Result**: Directly adds or updates the `ai_category` column in the CSV file.

### Key Features
- **Automatic Classification**: Calls the Alibaba Cloud Bailian API to intelligently determine the paper's field.
- **Batch Processing**: Automatically scans all `.final.csv` files in the specified directory.
- **Resume from Breakpoint**: Supports continuing processing after interruption, automatically skipping already classified papers.
- **Error Retry**: Built-in automatic retry mechanism to handle network fluctuations or API limits.
- **Title Cleaning**: Automatically handles special characters in titles (e.g., LaTeX formulas) to improve model parsing success rate.

### Usage
1.  **Configure Environment**: Ensure `pandas` and `openai` libraries are installed.
    ```bash
    pip install pandas openai
    ```
2.  **Configure API Key**: Open the script and replace the `API_KEY` variable with your own Alibaba Cloud API Key.
3.  **Run Script**:
    ```bash
    python classify_papers.py
    ```

---

## Directory Structure Example
```
project/
├── classify_papers.py
├── data/
│   ├── AAAI.final.csv
│   └── ...
├── data-false/           # Failure records generated by fetch_from_Ss.py
│   ├── AAAI.final.txt
│   └── ...
├── config/
│   └── venues_top.yaml   # Top conference/journal configuration file
├── semantic_scholar_and_openalex/
│   ├── fetch_from_Ss.py
│   └── fetch_from_openalex.py
└── README.md
```
