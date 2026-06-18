import argparse
import os
import random
import re
import subprocess
import time
import requests
from bs4 import BeautifulSoup
from markdownify import markdownify as md

def get_browser_url():
    """Attempts to get the active URL from Google Chrome or Safari on macOS."""
    try:
        # Try Google Chrome
        script_chrome = 'tell application "Google Chrome" to return URL of active tab of front window'
        url = subprocess.check_output(['osascript', '-e', script_chrome], stderr=subprocess.DEVNULL).decode('utf-8').strip()
        if url.startswith('http'):
            return url
    except Exception:
        pass

    try:
        # Try Safari
        script_safari = 'tell application "Safari" to return URL of front document'
        url = subprocess.check_output(['osascript', '-e', script_safari], stderr=subprocess.DEVNULL).decode('utf-8').strip()
        if url.startswith('http'):
            return url
    except Exception:
        pass

    return None

def clean_html(soup):
    """Removes unwanted elements like images, menus, navigation bars, sidebars, tracking scripts, comment sections."""
    unwanted_tags = ['img', 'script', 'style', 'nav', 'iframe', 'header', 'footer', 'aside', 'form', 'noscript']
    for tag in soup.find_all(unwanted_tags):
        tag.decompose()
    
    # Also attempt to remove specific classes that might be comments or ads if any
    for div in soup.find_all("div", class_=re.compile("comment|sidebar|menu|ad|tracking")):
        div.decompose()
        
    return soup

def scrape_chapter(url, output_dir):
    """Scrapes a single chapter and saves it to a Markdown file. Returns a dict with result stats."""
    print(f"Scraping: {url}")
    
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 14.3; rv:122.0) Gecko/20100101 Firefox/122.0',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/121.0.2277.112',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15'
    ]
    
    headers = {
        'User-Agent': random.choice(user_agents),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'en-US,en;q=0.9',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Cache-Control': 'max-age=0'
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Failed to fetch {url}: {e}")
        return {'status': 'UNSUCCESSFUL', 'url': url, 'reason': f"Request Failed: {e}"}

    try:
        soup = BeautifulSoup(response.text, 'html.parser')
        content_div = soup.find('div', id='content')
        
        if not content_div:
            print(f"Error: Could not find <div id='content'> on {url}")
            return {'status': 'UNSUCCESSFUL', 'url': url, 'reason': "Missing <div id='content'>"}

        # Clean unwanted elements
        content_div = clean_html(content_div)

        # Convert to Markdown
        # We want a clean output, so we can convert the HTML inside the div to markdown directly
        markdown_content = md(str(content_div), strip=['a']).strip()

        # Determine file name and title from the HTML
        title_text = ""
        # Try finding any heading tag that contains "Chapter"
        heading = soup.find(lambda tag: tag.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6'] and tag.text and re.search(r'(?i)chapter\s+\d+', tag.text))
        
        if heading:
            raw_title = heading.text.strip()
            m = re.search(r'(?i)(chapters?\s+\d+.*?)(?:\s*[-|]\s*|$)', raw_title)
            if m:
                title_text = m.group(1).strip()
            else:
                title_text = raw_title
        elif soup.title and soup.title.text:
            # Fallback to the page's <title> tag
            m = re.search(r'(?i)(chapters?\s+\d+.*?)(?:\s*[-|]\s*|$)', soup.title.text)
            if m:
                title_text = m.group(1).strip()
            else:
                title_text = soup.title.text.strip()

        # Clean up redundant strings like "[ ... words ]" from the title
        if title_text:
            title_text = re.sub(r'\[.*?\]', '', title_text).strip()
                
        chapter_num_match = re.search(r'(?i)chapters?\s+(\d+)', title_text)
        
        if chapter_num_match:
            chapter_num = chapter_num_match.group(1)
            filename = f"chapter_{int(chapter_num):04d}.md"
        elif title_text:
            # Fallback: use the actual chapter name/title as the filename, normalized to lowercase
            safe_title = re.sub(r'[\\/*?:"<>|\n\r]+', '', title_text)
            safe_title = safe_title.replace(' ', '_').lower()
            if safe_title.startswith('chapters'):
                safe_title = 'chapter' + safe_title[8:]
            filename = f"{safe_title}.md"
        else:
            # Fallback if no chapter number in title
            chapter_num_match_url = re.search(r'chapter-(\d+)', url)
            if chapter_num_match_url:
                chapter_num = chapter_num_match_url.group(1)
                filename = f"chapter_{int(chapter_num):04d}.md"
            else:
                filename = "chapter_unknown.md"

        # Unify heading indicators for the title
        if title_text:
            lines = markdown_content.splitlines()
            new_lines = []
            title_removed = False
            
            chap_str = f"chapter {chapter_num_match.group(1)}" if chapter_num_match else title_text.lower()
            
            # Strip out any existing title lines at the top with inconsistent headers (#, ##, ####, etc)
            for i, line in enumerate(lines):
                if i < 5 and not title_removed:
                    line_lower = line.lower()
                    if chap_str in line_lower and (line.strip().startswith('#') or chap_str == line_lower.strip() or title_text.lower() in line_lower):
                        title_removed = True
                        continue
                new_lines.append(line)
            
            markdown_content = "\n".join(new_lines).lstrip()
            
            # Unconditionally enforce the standard ### heading
            markdown_content = f"### {title_text}\n\n{markdown_content}"

        filepath = os.path.join(output_dir, filename)
        
        # Handle filename collisions to prevent silent overwrites
        base_name, ext = os.path.splitext(filename)
        counter = 2
        while os.path.exists(filepath):
            filepath = os.path.join(output_dir, f"{base_name}_{counter}{ext}")
            counter += 1

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(markdown_content.strip())
        
        print(f"Saved: {filepath}")

        # Find the next chapter link
        next_url = None
        next_link = soup.find('a', rel='next')
        if next_link and next_link.get('href'):
            next_url = next_link['href']
            # Handle relative URLs
            if next_url.startswith('/'):
                from urllib.parse import urlparse
                parsed_url = urlparse(url)
                base = f"{parsed_url.scheme}://{parsed_url.netloc}"
                next_url = base + next_url
                
        return {'status': 'SUCCESS', 'url': url, 'next_url': next_url}

    except Exception as e:
        print(f"Unknown Error processing {url}: {e}")
        return {'status': 'UNKNOWN_ERROR', 'url': url, 'reason': str(e)}

def print_summary(results):
    total = len(results)
    success = [r for r in results if r['status'] == 'SUCCESS']
    unsuccessful = [r for r in results if r['status'] == 'UNSUCCESSFUL']
    unknown = [r for r in results if r['status'] == 'UNKNOWN_ERROR']

    print("\n" + "="*80)
    print(f"{'SCRAPING SUMMARY':^80}")
    print("="*80)
    print(f"Total Webpages Processed : {total}")
    print(f"Successful               : {len(success)}")
    print(f"Unsuccessful             : {len(unsuccessful)}")
    print(f"Unknown Errors           : {len(unknown)}")
    print("="*80)

    if unsuccessful:
        print("\n--- UNSUCCESSFUL TABLE ---")
        print(f"{'Reason':<40} | {'URL'}")
        print("-" * 80)
        for r in unsuccessful:
            print(f"{r['reason'][:38]:<40} | {r['url']}")
            
    if unknown:
        print("\n--- UNKNOWN ERRORS TABLE ---")
        print(f"{'Error':<40} | {'URL'}")
        print("-" * 80)
        for r in unknown:
            print(f"{r['reason'][:38]:<40} | {r['url']}")
    
    print("\n")

def main():
    parser = argparse.ArgumentParser(description="Web Novel Scraper")
    parser.add_argument('--url', type=str, help="The starting URL of the chapter.")
    parser.add_argument('--chapters', type=str, help="Chapter range in format START-END (e.g., 123-456).")
    parser.add_argument('--delay', type=float, default=3.0, help="Delay between requests in seconds (default: 3).")
    parser.add_argument('--output-dir', type=str, default='.', help="Directory to save the Markdown files (default: current directory).")
    
    args = parser.parse_args()

    # Determine starting URL
    start_url = args.url
    if not start_url:
        print("No --url provided. Attempting to detect URL from active browser...")
        start_url = get_browser_url()
        if start_url:
            print(f"Detected browser URL: {start_url}")
        else:
            start_url = input("Could not detect browser URL. Please enter the starting URL: ").strip()
            if not start_url:
                print("No URL provided. Exiting.")
                return

    if not os.path.exists(args.output_dir):
        os.makedirs(args.output_dir)

    results = []

    # Mode 1: Range based iteration
    if args.chapters:
        match = re.match(r'(\d+)\s*-\s*(\d+)', args.chapters)
        if not match:
            print("Invalid format for --chapters. Please use START-END (e.g., 123-456).")
            return
        
        start_chap = int(match.group(1))
        end_chap = int(match.group(2))
        
        # Base URL extraction (everything up to /chapter-)
        base_url_match = re.match(r'(.*?/chapter-)\d+', start_url)
        if not base_url_match:
            print("Could not parse base URL structure from the provided URL. Expected format: .../chapter-XYZ")
            return
        
        base_url_prefix = base_url_match.group(1)
        
        for chap_num in range(start_chap, end_chap + 1):
            url = f"{base_url_prefix}{chap_num}"
            res = scrape_chapter(url, args.output_dir)
            results.append(res)
            if chap_num < end_chap:
                print(f"Waiting {args.delay} seconds before next request...")
                time.sleep(args.delay)

    # Mode 2: Auto-iteration based on 'Next' links
    else:
        current_url = start_url
        while current_url:
            res = scrape_chapter(current_url, args.output_dir)
            results.append(res)
            if res['status'] == 'SUCCESS' and res.get('next_url'):
                print(f"Waiting {args.delay} seconds before next request...")
                time.sleep(args.delay)
                current_url = res['next_url']
            else:
                if res['status'] == 'SUCCESS':
                    print("No next chapter found. Finished scraping.")
                else:
                    print(f"Stopped due to error: {res.get('reason')}")
                break

    print_summary(results)

if __name__ == '__main__':
    main()
