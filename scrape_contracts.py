import urllib.request
from bs4 import BeautifulSoup
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import re
import time
import sys

def print_flush(msg):
    print(msg)
    sys.stdout.flush()

BASE_URL = "https://www.cedd.gov.hk/eng/tender-notices/contracts/contracts-awarded/index.html"
DOMAIN = "https://www.cedd.gov.hk"

def get_soup(url):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            html = response.read()
            return BeautifulSoup(html, 'html.parser')
    except Exception as e:
        print_flush(f"Error fetching {url}: {e}")
        return None

def extract_contract_links(soup):
    links = []
    # Look for the table with "Contracts Awarded in Past 6 Months"
    # Based on the WebFetch output, it's a table.
    table = soup.find('table')
    if not table:
        return links
    
    for row in table.find_all('tr')[1:]: # Skip header
        cols = row.find_all('td')
        if len(cols) > 0:
            link_tag = cols[0].find('a')
            if link_tag and link_tag.get('href'):
                href = link_tag.get('href')
                if not href.startswith('http'):
                    # Handle relative paths
                    if href.startswith('/'):
                        href = DOMAIN + href
                    else:
                        # Handle relative to current page
                        href = "/".join(BASE_URL.split('/')[:-1]) + "/" + href
                links.append(href)
    return links

def extract_contract_details(url):
    print_flush(f"Fetching details from {url}...")
    soup = get_soup(url)
    if not soup:
        return None
    
    details = {}
    
    # Try searching for labels in the text
    content = soup.get_text(separator='\n')
    lines = content.split('\n')
    
    for i, line in enumerate(lines):
        line_clean = line.strip().lower()
        # More specific matching for Contractor
        if 'contractor' in line_clean and 'address' not in line_clean and ':' in line_clean:
            parts = line.split(':', 1)
            if len(parts) > 1 and parts[1].strip():
                details['company'] = parts[1].strip()
            elif i + 1 < len(lines):
                details['company'] = lines[i+1].strip()
        
        # More specific matching for Sum/Amount
        if ('awarded sum' in line_clean or 'contract sum' in line_clean or 'contract value' in line_clean) and ':' in line_clean:
            parts = line.split(':', 1)
            amount_val = ""
            if len(parts) > 1 and parts[1].strip():
                amount_val = parts[1].strip()
            elif i + 1 < len(lines):
                amount_val = lines[i+1].strip()
            
            if amount_val:
                details['amount_str'] = amount_val
                if '(million)' in line_clean:
                    details['is_million'] = True
                else:
                    details['is_million'] = False

    # If not found by line splitting, try searching the whole text with regex
    if 'company' not in details:
        match = re.search(r'Contractor\s*:\s*(.*)', content, re.IGNORECASE)
        if match:
            details['company'] = match.group(1).strip()
            
    if 'amount_str' not in details:
        match = re.search(r'Awarded Sum\s*(?:\(million\))?\s*:\s*(.*)', content, re.IGNORECASE)
        if match:
            details['amount_str'] = match.group(1).strip()
            if '(million)' in match.group(0).lower():
                details['is_million'] = True

    return details

def clean_amount(details):
    amount_str = details.get('amount_str', '')
    if not amount_str:
        return 0.0
    
    # Remove currency symbols, commas, and other non-numeric chars except decimal point
    match = re.search(r'([\d,]+\.?\d*)', amount_str)
    if not match:
        return 0.0
    
    cleaned = match.group(1).replace(',', '')
    try:
        val = float(cleaned)
        # Heuristic: if val > 10,000, it's likely the full amount already, 
        # even if the label says "(million)".
        if details.get('is_million') and val < 10000:
            val *= 1_000_000
            
        return val
    except ValueError:
        return 0.0

def clean_company_name(name):
    if not name:
        return ""
    # Replace common mis-encoded characters or special symbols
    name = name.replace('û', '-')
    name = name.replace('\xa0', ' ') # Non-breaking space
    name = name.replace('–', '-') # En dash
    name = name.replace('—', '-') # Em dash
    # Remove extra whitespace
    name = re.sub(r'\s+', ' ', name).strip()
    return name

def main():
    print_flush(f"Fetching main page: {BASE_URL}")
    main_soup = get_soup(BASE_URL)
    if not main_soup:
        print_flush("Failed to fetch main page.")
        return
    
    # Debug: print some of the soup to see if it's correct
    print_flush(f"Soup length: {len(str(main_soup))}")
    print_flush(f"Title: {main_soup.title.string if main_soup.title else 'No Title'}")
    
    links = extract_contract_links(main_soup)
    print_flush(f"Found {len(links)} contract links.")
    
    if not links:
        # Try a different extraction method if the table isn't found
        print_flush("Trying fallback link extraction...")
        for a in main_soup.find_all('a', href=True):
            if '/contracts-awarded/' in a['href'] and 'index.html' not in a['href']:
                href = a['href']
                if not href.startswith('http'):
                    if href.startswith('/'):
                        href = DOMAIN + href
                    else:
                        href = "/".join(BASE_URL.split('/')[:-1]) + "/" + href
                if href not in links:
                    links.append(href)
        print_flush(f"Found {len(links)} links using fallback.")
    
    all_data = []
    for link in links:
        details = extract_contract_details(link)
        if details and 'company' in details and 'amount_str' in details:
            details['company'] = clean_company_name(details['company'])
            details['amount'] = clean_amount(details)
            all_data.append(details)
        time.sleep(0.5)
        
    if not all_data:
        print_flush("No data extracted.")
        return
    
    df = pd.DataFrame(all_data)
    
    # Aggregate by company
    summary = df.groupby('company')['amount'].sum().reset_index()
    summary = summary.sort_values(by='amount', ascending=False)
    
    # Use millions for readability
    summary['Amount (HK$ Million)'] = summary['amount'] / 1_000_000
    
    print_flush("\nSummary of Awarded Contracts:")
    # Format the table for display
    display_summary = summary[['company', 'Amount (HK$ Million)']].copy()
    display_summary['Amount (HK$ Million)'] = display_summary['Amount (HK$ Million)'].map('{:,.2f}'.format)
    print_flush(str(display_summary))
    
    # Plotting
    plt.figure(figsize=(14, 10))
    sns.set_theme(style="whitegrid")
    
    # Filter out companies with 0 amount
    plot_data = summary[summary['amount'] > 0].copy()
    
    # Create the bar chart with hue to avoid warning
    ax = sns.barplot(
        x='Amount (HK$ Million)', 
        y='company', 
        data=plot_data, 
        palette='viridis',
        hue='company',
        legend=False
    )
    
    plt.xlabel('Total Amount (HK$ Million)')
    plt.ylabel('Awarded Company')
    plt.title('Total Contract Amount Awarded per Company (Past 6 Months)\n(Data from CEDD Website)')
    
    # Add values on bars
    for i, v in enumerate(plot_data['Amount (HK$ Million)']):
        ax.text(v + (plot_data['Amount (HK$ Million)'].max() * 0.01), i, f"{v:,.2f}M", va='center', fontweight='bold')
        
    plt.tight_layout()
    plt.savefig('static/contract_summary_barchart.png')
    print_flush("\nBarchart saved as 'static/contract_summary_barchart.png'")
    
    # Pie chart for distribution
    plt.figure(figsize=(10, 10))
    top_n = summary.head(10).copy()
    others_sum = summary['amount'].iloc[10:].sum()
    if others_sum > 0:
        others_df = pd.DataFrame([{'company': 'Others', 'amount': others_sum}])
        top_n = pd.concat([top_n, others_df], ignore_index=True)
    
    plt.pie(top_n['amount'], labels=top_n['company'], autopct='%1.1f%%', startangle=140, colors=sns.color_palette('viridis', len(top_n)))
    plt.title('Distribution of Contract Amounts (Top 10 + Others)')
    plt.savefig('static/contract_summary_piechart.png')
    print_flush("Pie chart saved as 'static/contract_summary_piechart.png'")
    
    # Also save to CSV
    summary.to_csv('static/contract_summary.csv', index=False)
    print_flush("Summary data saved as 'static/contract_summary.csv'")
    
    # Save the last update time
    last_update = time.strftime('%Y-%m-%d %H:%M:%S')
    with open('static/last_update.txt', 'w') as f:
        f.write(last_update)
    print_flush(f"Last update time saved: {last_update}")

if __name__ == "__main__":
    main()
