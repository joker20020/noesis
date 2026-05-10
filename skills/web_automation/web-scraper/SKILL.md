---
name: web-scraper
description: Scrape web pages using Python requests and BeautifulSoup. Use when the user asks to extract data from websites, crawl pages, or parse HTML content.
category: web_automation
stage: "SOP"
version: 1
---

# Web Scraper

## Overview
Extract structured data from web pages using `requests` and `beautifulsoup4`. Handles common scraping patterns: static pages, pagination, table extraction, and data export.

## When to Use
- User asks to scrape data from a website
- Need to extract tables, lists, or structured content from HTML
- Want to monitor a page for changes
- Need to collect data from multiple pages

## Core Pattern

### Prerequisites
```bash
pip install requests beautifulsoup4
```

### Steps

1. **Fetch the page**
```bash
python -c "
import requests
url = 'TARGET_URL'
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
resp = requests.get(url, headers=headers, timeout=10)
resp.raise_for_status()
print(resp.text[:500])
"
```

2. **Parse with BeautifulSoup**
```bash
python -c "
from bs4 import BeautifulSoup
import requests
url = 'TARGET_URL'
resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
soup = BeautifulSoup(resp.text, 'html.parser')
# Extract elements
for item in soup.select('CSS_SELECTOR'):
    print(item.get_text(strip=True))
"
```

3. **Extract structured data** — write a script to iterate and collect:
```bash
python -c "
from bs4 import BeautifulSoup
import requests, json
url = 'TARGET_URL'
soup = BeautifulSoup(requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}).text, 'html.parser')
results = []
for row in soup.select('table tr'):
    cols = row.find_all('td')
    if cols:
        results.append({f'col_{i}': c.get_text(strip=True) for i, c in enumerate(cols)})
print(json.dumps(results, indent=2, ensure_ascii=False)[:3000])
"
```

4. **Handle pagination** — loop through pages:
```bash
python -c "
import requests
from bs4 import BeautifulSoup
base = 'URL_WITH_PAGE_PARAM'
for page in range(1, 6):
    url = f'{base}?page={page}'
    soup = BeautifulSoup(requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}).text, 'html.parser')
    items = soup.select('ITEM_SELECTOR')
    print(f'Page {page}: {len(items)} items')
    if not items:
        break
"
```

5. **Save results** — write collected data to file:
```bash
python -c "
import json
data = [{'title': 'example', 'url': 'https://...'}]
with open('workspace/scraped_data.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
print(f'Saved {len(data)} records')
"
```

## Quick Reference

| Step | Tool | Key Parameters |
|------|------|---------------|
| Fetch page | code_run | `python -c "import requests; ..."` |
| Parse HTML | code_run | `soup.select('CSS_SELECTOR')` |
| Extract data | code_run | Loop + collect as list of dicts |
| Save output | code_run | `json.dump(data, file)` |
| Read saved data | file_read | `path="workspace/scraped_data.json"` |

## Common Mistakes
- Always set a `User-Agent` header — many sites block default Python requests
- Add `timeout=10` to requests to avoid hanging
- Use `resp.raise_for_status()` to catch HTTP errors early
- Check `robots.txt` before scraping aggressively
- Respect rate limits — add `time.sleep(1)` between paginated requests
- Large pages: use `soup.select()` with specific CSS selectors instead of traversing entire DOM
