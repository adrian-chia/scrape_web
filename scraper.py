import argparse
import logging
import os
import random
import re
import subprocess
import time
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from markdownify import markdownify as md

# logger_initialized: A boolean flag to track whether the global logger has been configured.
#   - False: The logger hasn't been set up yet. This is the initial state.
#   - True: The logger is fully configured with its file handler and formatting, preventing duplicate handlers.
logger_initialized = False

start_time_global = None

def setup_logger(name):
    global logger_initialized
    if logger_initialized:
        return
    
    logs_dir = os.path.join(os.getcwd(), 'logs')
    if not os.path.exists(logs_dir):
        os.makedirs(logs_dir)
        
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = re.sub(r'[\\/*?:"<>|\n\r]+', '', name).strip().replace(' ', '_')
    if not safe_name:
        safe_name = "scraper"
    log_filename = f"{safe_name}_{timestamp}.log"
    log_filepath = os.path.join(logs_dir, log_filename)
    
    file_handler = logging.FileHandler(log_filepath, encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logger.addHandler(file_handler)
    
    logger_initialized = True
    logging.info(f"Logger initialized. File: {log_filepath}")
    if start_time_global:
        logging.info(f"Script started at: {start_time_global.strftime('%Y-%m-%d %H:%M:%S')}")

def ensure_logger(name="scraper"):
    if not logger_initialized:
        setup_logger(name)

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

def scrape_chapter(url, output_dir, should_print=True):
    """Scrapes a single chapter and saves it to a Markdown file. Returns a dict with result stats."""
    if should_print:
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
        msg = f"Failed to fetch {url}: {e}"
        print(f"Error: {msg}")
        ensure_logger("unknown_title")
        logging.error(msg)
        return {'status': 'UNSUCCESSFUL', 'url': url, 'reason': f"Request Failed: {e}"}

    try:
        soup = BeautifulSoup(response.text, 'html.parser')
        content_div = soup.find('div', id='content')
        
        if not content_div:
            msg = f"Error: Could not find <div id='content'> on {url}"
            print(msg)
            ensure_logger("unknown_title")
            logging.error(msg)
            return {'status': 'UNSUCCESSFUL', 'url': url, 'reason': "Missing <div id='content'>"}

        # Clean unwanted elements
        content_div = clean_html(content_div)

        # Convert to Markdown
        # We want a clean output, so we can convert the HTML inside the div to markdown directly
        markdown_content = md(str(content_div), strip=['a']).strip()

        # Determine file name and title from the HTML
        title_text = ""
        raw_title = ""
        # Try finding any heading tag that contains variations of "Chapter"
        heading = soup.find(lambda tag: tag.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6'] and tag.text and re.search(r'(?i)\b(chapters?|chater|s\s+\d+|bonus)\b', tag.text))
        
        if heading:
            raw_title = heading.text.strip()
        elif soup.title and soup.title.text:
            raw_title = soup.title.text.strip()

        original_extracted_title = ""
        if raw_title:
            # Clean title by removing trailing site names and redundant strings like "[ ... words ]"
            clean_title = re.sub(r'(?i)\s*[-|]\s*(Novel\s*Fire|Read.*Free|Online).*$', '', raw_title)
            clean_title = re.sub(r'\[.*?\]', '', clean_title).strip()
            
            # Try to extract the chapter-specific part
            m = re.search(r'(?i)\b(chapters?|chater|s\s+\d+|bonus)(.*?)$', clean_title)
            if m:
                original_extracted_title = m.group(0).strip()
            else:
                original_extracted_title = clean_title
            
            title_text = original_extracted_title
            
            # Normalize title
            norm_match = re.match(r'(?i)(?:chapters?|chater|s)\s+(\d+)\s*[:-]?\s*(.*)', title_text)
            if norm_match:
                chap_num = norm_match.group(1)
                rest_of_title = norm_match.group(2).strip()
                if rest_of_title:
                    title_text = f"Chapter {chap_num} - {rest_of_title}"
                else:
                    title_text = f"Chapter {chap_num}"
            else:
                # Handle Bonus cases like "Bonus 1" or "Bonus Chapter 1"
                bonus_match = re.match(r'(?i)(bonus.*?)\s+(\d+)\s*[:-]?\s*(.*)', title_text)
                if bonus_match:
                    bonus_type = bonus_match.group(1).title() # e.g. "Bonus", "Bonus Chapter"
                    chap_num = bonus_match.group(2)
                    rest_of_title = bonus_match.group(3).strip()
                    if rest_of_title:
                        title_text = f"{bonus_type} {chap_num} - {rest_of_title}"
                    else:
                        title_text = f"{bonus_type} {chap_num}"

        # Determine filename
        chapter_num_match = re.search(r'(?i)(?:chapters?|chater|s)\s+(\d+)', title_text)
        if not chapter_num_match:
            # Fallback for bonus chapters
            chapter_num_match = re.search(r'(?i)bonus.*?\s+(\d+)', title_text)
            
        if chapter_num_match and not title_text.lower().startswith('bonus'):
            chapter_num = chapter_num_match.group(1)
            filename = f"chapter_{int(chapter_num):04d}.md"
        elif title_text:
            # Fallback: use the actual chapter name/title as the filename, normalized to lowercase
            safe_title = re.sub(r'[\\/*?:"<>|\n\r]+', '', title_text)
            safe_title = safe_title.replace(' ', '_').lower()
            filename = f"{safe_title}.md"
        else:
            # Fallback if no chapter number in title
            chapter_num_match_url = re.search(r'chapter-(\d+)', url)
            if chapter_num_match_url:
                chapter_num = chapter_num_match_url.group(1)
                filename = f"chapter_{int(chapter_num):04d}.md"
            else:
                filename = "chapter_unknown.md"

        # Initialize logger with title if not already initialized
        ensure_logger(title_text if title_text else "unknown_title")

        # Unify heading indicators for the title
        if title_text:
            lines = markdown_content.splitlines()
            new_lines = []
            
            norm_title = re.sub(r'[\W_]+', '', title_text.lower())
            norm_orig = re.sub(r'[\W_]+', '', original_extracted_title.lower()) if original_extracted_title else ""
            
            # Strip out any existing title lines at the top (and any leading blank lines)
            skip_blanks = True
            for i, line in enumerate(lines):
                if i < 10:
                    line_lower = line.lower().strip()
                    norm_line = re.sub(r'[\W_]+', '', line_lower)
                    
                    is_duplicate = False
                    if norm_line and (norm_line.startswith(norm_title) or (norm_orig and norm_line.startswith(norm_orig))):
                        is_duplicate = True
                        
                    if not is_duplicate and chapter_num_match:
                        chap_num_str = chapter_num_match.group(1)
                        clean_line_no_bold = re.sub(r'^\*+|\*+$', '', re.sub(r'^#+\s*', '', line_lower)).strip()
                        header_match = re.match(r'(?i)^(?:chapters?|chater|s|bonus.*?)\s*[:-]?\s*(\d+)', clean_line_no_bold)
                        if header_match and header_match.group(1) == chap_num_str:
                            is_duplicate = True

                    if is_duplicate:
                        continue
                        
                # Also skip leading blank lines
                if skip_blanks and not line.strip():
                    continue
                
                skip_blanks = False
                new_lines.append(line)
            
            markdown_content = "\n".join(new_lines).lstrip()
            
            # Unconditionally enforce the standard ### heading
            markdown_content = f"### {title_text}\n\n{markdown_content}"

        filepath = os.path.join(output_dir, filename)
        
        # Handle filename collisions to prevent silent overwrites
        base_name, ext = os.path.splitext(filename)
        counter = 2
        duplicate_warned = False
        while os.path.exists(filepath):
            if not duplicate_warned:
                msg = f"Duplicate file detected for URL {url}. Modifying filename to prevent overwrite."
                print(f"Warning: {msg}")
                logging.warning(msg)
                duplicate_warned = True
            filepath = os.path.join(output_dir, f"{base_name}_{counter}{ext}")
            counter += 1

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(markdown_content.strip())
        
        if should_print:
            print(f"Saved: {filepath}")
        logging.info(f"Saved: {filepath}")

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
        msg = f"Unknown Error processing {url}: {e}"
        print(f"Error: {msg}")
        ensure_logger("unknown_title")
        logging.error(msg)
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
    global start_time_global
    start_time_global = datetime.now()
    start_str = start_time_global.strftime('%Y-%m-%d %H:%M:%S')
    print(f"Script started at: {start_str}")

    parser = argparse.ArgumentParser(description="Web Novel Scraper")
    parser.add_argument('--url', type=str, help="The starting URL of the chapter.")
    parser.add_argument('--chapters', type=str, help="Chapter range in format START-END (e.g., 123-456).")
    parser.add_argument('--delay', type=float, default=3.0, help="Delay between requests in seconds (default: 3).")
    parser.add_argument('--output-dir', type=str, default='.', help="Directory to save the Markdown files (default: current directory).")
    
    args = parser.parse_args()

    if args.output_dir != '.':
        ensure_logger(os.path.basename(os.path.abspath(args.output_dir)))

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

    # Mode 1: Targeted iteration (Range, Single, or List)
    if args.chapters:
        chapter_nums = []
        parts = args.chapters.split(',')
        for part in parts:
            part = part.strip()
            if not part: continue
            
            range_match = re.match(r'^(\d+)\s*-\s*(\d+)$', part)
            if range_match:
                start_c = int(range_match.group(1))
                end_c = int(range_match.group(2))
                chapter_nums.extend(range(start_c, end_c + 1))
            else:
                single_match = re.match(r'^(\d+)$', part)
                if single_match:
                    chapter_nums.append(int(single_match.group(1)))
                else:
                    print(f"Invalid format for --chapters part: '{part}'. Please use START-END (e.g., 123-456), a single number, or a comma-separated list.")
                    return
        
        # Remove duplicates while preserving order
        seen = set()
        chapter_nums = [x for x in chapter_nums if not (x in seen or seen.add(x))]
        
        # Base URL extraction (everything up to /chapter-)
        base_url_match = re.match(r'(.*?/chapter-)\d+', start_url)
        if not base_url_match:
            print("Could not parse base URL structure from the provided URL. Expected format: .../chapter-XYZ")
            return
        
        base_url_prefix = base_url_match.group(1)
        
        for i, chap_num in enumerate(chapter_nums):
            url = f"{base_url_prefix}{chap_num}"
            success_count = len([r for r in results if r['status'] == 'SUCCESS'])
            should_print = (success_count == 0 or (success_count + 1) % 10 == 0)
            
            res = scrape_chapter(url, args.output_dir, should_print)
            results.append(res)
            if i < len(chapter_nums) - 1:
                if should_print:
                    msg = f"Waiting {args.delay} seconds before next request..."
                    print(msg)
                    if logger_initialized: logging.info(msg)
                time.sleep(args.delay)

    # Mode 2: Auto-iteration based on 'Next' links
    else:
        current_url = start_url
        while current_url:
            success_count = len([r for r in results if r['status'] == 'SUCCESS'])
            should_print = (success_count == 0 or (success_count + 1) % 10 == 0)
            
            res = scrape_chapter(current_url, args.output_dir, should_print)
            results.append(res)
            if res['status'] == 'SUCCESS' and res.get('next_url'):
                if should_print:
                    msg = f"Waiting {args.delay} seconds before next request..."
                    print(msg)
                    if logger_initialized: logging.info(msg)
                time.sleep(args.delay)
                current_url = res['next_url']
            else:
                if res['status'] == 'SUCCESS':
                    print("No next chapter found. Finished scraping.")
                else:
                    print(f"Stopped due to error: {res.get('reason')}")
                break

    print_summary(results)
    
    end_time = datetime.now()
    duration = end_time - start_time_global
    
    # Format duration to HH:MM:SS
    total_seconds = int(duration.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    duration_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    
    end_str = (
        f"{'='*35}\n"
        f"Script Execution Summary\n"
        f"{'='*35}\n"
        f"Script started at: {start_str}\n"
        f"Script ended at:   {end_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"Duration:          {duration_str}"
    )
    print(f"\n{end_str}")
    
    if logger_initialized:
        logging.info(f"Script ended at: {end_time.strftime('%Y-%m-%d %H:%M:%S')} (Duration: {duration_str})")
        # Log non-successful URLs at the end too
        unsuccessful = [r for r in results if r['status'] == 'UNSUCCESSFUL']
        unknown = [r for r in results if r['status'] == 'UNKNOWN_ERROR']
        if unsuccessful or unknown:
            logging.info("--- Non-Successful URLs Summary ---")
            for r in unsuccessful + unknown:
                logging.info(f"[{r['status']}] {r['url']} - {r['reason']}")

if __name__ == '__main__':
    main()
