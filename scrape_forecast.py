import urllib.request
import urllib.parse
from bs4 import BeautifulSoup
import pandas as pd
import re
import time
import sys
import os
import pdfplumber
import io

def print_flush(msg):
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode('utf-8', errors='replace').decode('utf-8'))
    sys.stdout.flush()

HYD_INDEX_URL = "https://www.hyd.gov.hk/en/tender_notices/contracts/forecast_of_invitation/index.html"
CEDD_INDEX_URL = "https://www.cedd.gov.hk/eng/tender-notices/contracts/forecast-of-invitations-to-tender/index.html"

HYD_DOMAIN = "https://www.hyd.gov.hk"
CEDD_DOMAIN = "https://www.cedd.gov.hk"

def get_soup(url):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as response:
            html = response.read()
            return BeautifulSoup(html, 'html.parser')
    except Exception as e:
        print_flush(f"Error fetching {url}: {e}")
        return None

def get_pdf_content(url):
    try:
        # Properly encode the URL to handle spaces and special characters
        parts = list(urllib.parse.urlsplit(url))
        parts[2] = urllib.parse.quote(parts[2])
        url = urllib.parse.urlunsplit(parts)
        
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.read()
    except Exception as e:
        print_flush(f"Error fetching PDF from {url}: {e}")
        return None

def extract_hyd_pdf_url(soup):
    if not soup: return None
    for a in soup.find_all('a', href=True):
        if ('Forecast' in a.get_text() or 'HyD.pdf' in a['href']) and a['href'].endswith('.pdf'):
            href = a['href']
            if not href.startswith('http'):
                if href.startswith('/'):
                    return HYD_DOMAIN + href
                else:
                    return "/".join(HYD_INDEX_URL.split('/')[:-1]) + "/" + href
            return href
    return None

def extract_cedd_pdf_url(soup):
    if not soup: return None
    # CEDD forecast page usually has a link to PDF in a table
    table = soup.find('table')
    if table:
        for a in table.find_all('a', href=True):
            if a['href'].endswith('.pdf'):
                href = a['href']
                if not href.startswith('http'):
                    if href.startswith('/'):
                        return CEDD_DOMAIN + href
                    else:
                        return "/".join(CEDD_INDEX_URL.split('/')[:-1]) + "/" + href
                return href
    return None

def clean_description(text, contract_no):
    # Remove the contract no from the description
    text = text.replace(contract_no, "")
    # Remove multiple spaces and newlines
    text = re.sub(r'\s+', ' ', text).strip()
    # Remove common prefixes like "Contract No.:" or "合約編號:"
    text = re.sub(r'(?:Contract No\.|合約編號|Contract Title|合約名稱)\s*[:：]?\s*', '', text, flags=re.IGNORECASE)
    # Remove common Chinese/English boilerplate if it's at the start
    text = re.sub(r'^(?:PWP Item No\.|工程編號|Probable Date of Gazettal/ Inviting Tenders|憲報公告/ 招標暫定日期)\s*', '', text)
    return text.strip()

def parse_hyd_pdf(pdf_content):
    print_flush("Parsing HyD PDF...")
    all_data = []
    try:
        with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if not text: continue
                
                matches = re.finditer(r'(?:Contract No\.|合約編號)\s*[:：]?\s*([A-Z0-9/]+)', text)
                lines = text.split('\n')
                
                for match in matches:
                    contract_no = match.group(1)
                    description = ""
                    probable_date = ""
                    
                    for i, line in enumerate(lines):
                        if contract_no in line:
                            # Capture current line and next 2 lines for full title
                            relevant_lines = lines[i:i+3]
                            full_text = " ".join(relevant_lines)
                            
                            # Extract date
                            date_match = re.search(r'(20\d{2}\s*Q[1-4]|20\d{2}年\s*第\s*[1-4]\s*季)', full_text)
                            if date_match:
                                probable_date = date_match.group(1)
                                # Remove date from description
                                full_text = full_text.replace(probable_date, "")
                            
                            description = clean_description(full_text, contract_no)
                            break
                    
                    if contract_no:
                        all_data.append({
                            'Department': 'HyD',
                            'Contract No': contract_no,
                            'Description': description,
                            'Probable Date': probable_date
                        })
    except Exception as e:
        print_flush(f"Error parsing HyD PDF: {e}")
    return all_data

def parse_cedd_pdf(pdf_content):
    print_flush("Parsing CEDD PDF...")
    all_data = []
    try:
        with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if not text: continue
                
                matches = re.finditer(r'(?:Contract No\.|合約編號)\s*[:：]?\s*([A-Z0-9/]+)', text)
                lines = text.split('\n')
                
                for match in matches:
                    contract_no = match.group(1)
                    description = ""
                    probable_date = ""
                    
                    for i, line in enumerate(lines):
                        if contract_no in line:
                            relevant_lines = lines[i:i+3]
                            full_text = " ".join(relevant_lines)
                            
                            date_match = re.search(r'(20\d{2}\s*Q[1-4]|20\d{2}年\s*第\s*[1-4]\s*季|20\d{2}Q[1-4])', full_text)
                            if date_match:
                                probable_date = date_match.group(1)
                                full_text = full_text.replace(probable_date, "")
                            
                            description = clean_description(full_text, contract_no)
                            break
                    
                    if contract_no:
                        all_data.append({
                            'Department': 'CEDD',
                            'Contract No': contract_no,
                            'Description': description,
                            'Probable Date': probable_date
                        })
    except Exception as e:
        print_flush(f"Error parsing CEDD PDF: {e}")
    return all_data

def main():
    print_flush("Starting forecast scraping...")
    
    # HyD
    print_flush(f"Fetching HyD index: {HYD_INDEX_URL}")
    hyd_soup = get_soup(HYD_INDEX_URL)
    hyd_pdf_url = extract_hyd_pdf_url(hyd_soup)
    hyd_data = []
    if hyd_pdf_url:
        print_flush(f"Found HyD PDF: {hyd_pdf_url}")
        pdf_content = get_pdf_content(hyd_pdf_url)
        if pdf_content:
            hyd_data = parse_hyd_pdf(pdf_content)
    else:
        print_flush("Failed to find HyD PDF URL.")

    # CEDD
    print_flush(f"Fetching CEDD index: {CEDD_INDEX_URL}")
    cedd_soup = get_soup(CEDD_INDEX_URL)
    cedd_pdf_url = extract_cedd_pdf_url(cedd_soup)
    cedd_data = []
    if cedd_pdf_url:
        print_flush(f"Found CEDD PDF: {cedd_pdf_url}")
        pdf_content = get_pdf_content(cedd_pdf_url)
        if pdf_content:
            cedd_data = parse_cedd_pdf(pdf_content)
    else:
        print_flush("Failed to find CEDD PDF URL.")

    all_forecasts = hyd_data + cedd_data
    
    if all_forecasts:
        df = pd.DataFrame(all_forecasts)
        # Ensure static folder exists
        if not os.path.exists('static'):
            os.makedirs('static')
            
        df.to_csv('static/tender_forecast.csv', index=False)
        print_flush(f"Saved {len(all_forecasts)} forecast items to static/tender_forecast.csv")
        
        # Save last update time for forecast
        last_update = time.strftime('%Y-%m-%d %H:%M:%S')
        with open('static/last_forecast_update.txt', 'w') as f:
            f.write(last_update)
    else:
        print_flush("No forecast data found.")

if __name__ == "__main__":
    main()
