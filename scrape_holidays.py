import os
import io
import urllib.request
import cloudscraper
import pandas as pd
from bs4 import BeautifulSoup

# ==========================================
# Configuration Section
# Comment out any URL below to skip scraping that particular site
# ==========================================
URLS = {
    'nasdaq': 'https://www.nasdaqtrader.com/trader.aspx?id=calendar',
    'finra': 'https://www.finra.org/filing-reporting/market-transparency-reporting/holiday-calendar',
    'fed': 'https://www.stlouisfed.org/about-us/resources/legal-holiday-schedule'
}

def fetch_html(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
    with urllib.request.urlopen(req, timeout=15) as response:
        return response.read().decode('utf-8')

def main():
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
    os.makedirs(data_dir, exist_ok=True)

    # 1. Nasdaq
    if 'nasdaq' in URLS:
        print("Scraping Nasdaq Holidays...")
        try:
            html = fetch_html(URLS['nasdaq'])
            soup = BeautifulSoup(html, 'lxml')
            table = soup.select_one(".dataTable table")
            if table:
                df = pd.read_html(io.StringIO(str(table)))[0]
                df.columns = ['Date', 'Holiday', 'Status']
                # Filter out the misplaced header row
                df = df[df['Date'] != '2026']
                # Standardize date format to YYYYMMDD
                df['Date'] = pd.to_datetime(df['Date'], errors='coerce').dt.strftime('%Y%m%d')
                # Ensure Date is first
                cols = ['Date'] + [col for col in df.columns if col != 'Date']
                df = df[cols]
                df.to_csv(os.path.join(data_dir, 'nasdaq_holidays.csv'), index=False)
                print("Nasdaq holidays saved.")
            else:
                print("Failed to find Nasdaq table.")
        except Exception as e:
            print(f"Error scraping Nasdaq: {e}")

    # 2. FINRA
    if 'finra' in URLS:
        print("Scraping FINRA Holidays...")
        try:
            html = fetch_html(URLS['finra'])
            soup = BeautifulSoup(html, 'lxml')
            table = soup.select_one("table")
            if table:
                df = pd.read_html(io.StringIO(str(table)))[0]
                if len(df.columns) == 2:
                    df.columns = ['Date', 'Holiday']
                # Standardize date format to YYYYMMDD
                df['Date'] = pd.to_datetime(df['Date'], errors='coerce').dt.strftime('%Y%m%d')
                # Ensure Date is first
                cols = ['Date'] + [col for col in df.columns if col != 'Date']
                df = df[cols]
                df.to_csv(os.path.join(data_dir, 'finra_holidays.csv'), index=False)
                print("FINRA holidays saved.")
            else:
                print("Failed to find FINRA table.")
        except Exception as e:
            print(f"Error scraping FINRA: {e}")

    # 3. Fed
    if 'fed' in URLS:
        print("Scraping Fed Holidays...")
        try:
            scraper = cloudscraper.create_scraper()
            html = scraper.get(URLS['fed']).text
            soup = BeautifulSoup(html, 'lxml')
            tables = soup.select(".field-content table")
            if tables:
                all_dfs = []
                for idx, table in enumerate(tables):
                    try:
                        df = pd.read_html(io.StringIO(str(table)))[0]
                        df['Year'] = '2026' if idx == 0 else '2027' if idx == 1 else 'Unknown'
                        all_dfs.append(df)
                    except Exception as inner_e:
                        pass
                if all_dfs:
                    combined_df = pd.concat(all_dfs, ignore_index=True)
                    if 'Date' in combined_df.columns and 'Year' in combined_df.columns:
                        clean_dates = combined_df['Date'].astype(str).str.replace(r'\*+', '', regex=True)
                        combined_df['Date'] = pd.to_datetime(clean_dates + ', ' + combined_df['Year'], errors='coerce').dt.strftime('%Y%m%d')
                        combined_df = combined_df.drop(columns=['Year'])
                    
                    # Ensure Date is first
                    if 'Date' in combined_df.columns:
                        cols = ['Date'] + [col for col in combined_df.columns if col != 'Date']
                        combined_df = combined_df[cols]
                        
                    combined_df.to_csv(os.path.join(data_dir, 'fed_holidays.csv'), index=False)
                    print("Fed holidays saved.")
                else:
                    print("No valid tables parsed for Fed.")
            else:
                print("Failed to find Fed tables.")
        except Exception as e:
            print(f"Error scraping Fed: {e}")

if __name__ == "__main__":
    main()
