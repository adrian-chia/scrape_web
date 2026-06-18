import argparse
import pathlib
import re
import uuid
import sys
import markdown
from ebooklib import epub
from lxml import etree

# --- EpubNav Monkeypatch to reorder Guide/TOC ---
original_get_nav = epub.EpubWriter._get_nav

def custom_get_nav(self, item):
    xml_str = original_get_nav(self, item)
    root = etree.fromstring(xml_str)
    namespaces = {'xhtml': 'http://www.w3.org/1999/xhtml', 'epub': 'http://www.idpf.org/2007/ops'}
    body = root.find('.//xhtml:body', namespaces=namespaces)
    if body is not None:
        landmarks = None
        toc = None
        for child in body:
            if child.tag == '{http://www.w3.org/1999/xhtml}nav':
                epub_type = child.get('{http://www.idpf.org/2007/ops}type')
                if epub_type == 'landmarks':
                    landmarks = child
                elif epub_type == 'toc':
                    toc = child
        if landmarks is not None and toc is not None:
            body.remove(landmarks)
            toc_index = body.index(toc)
            body.insert(toc_index, landmarks)
    return etree.tostring(root, pretty_print=True, encoding="utf-8", xml_declaration=True)

epub.EpubWriter._get_nav = custom_get_nav
# ------------------------------------------------

def natural_sort_key(path):
    """Sorts alphabetically but numerically within strings (e.g., 2 before 10).
    Bonus chapters are sorted to appear at the end."""
    is_bonus = path.name.lower().startswith('bonus')
    parts = [int(text) if text.isdigit() else text.lower()
             for text in re.split(r'(\d+)', path.name)]
    return (is_bonus, parts)

def extract_title(content, fallback_name):
    """Extract the first Markdown header or Chapter heading as the title."""
    title = None
    
    # Try markdown header first
    match = re.search(r'^#{1,6}\s+(.*)$', content, re.MULTILINE)
    if match:
        title = match.group(1).strip()
    else:
        # Fallback to finding a line starting with Chapter or Chapters
        match = re.search(r'^(Chapters?\s+\d+.*)$', content, re.MULTILINE | re.IGNORECASE)
        if match:
            title = match.group(1).strip()
            
    if title:
        # Correct 'Chapters' to 'Chapter'
        if title.lower().startswith('chapters'):
            title = 'Chapter' + title[8:]
        elif title.lower().startswith('chapter'):
            title = 'Chapter' + title[7:]
        return title

    # Remove zero padding from fallback name (e.g., chapter_0002 -> Chapter 2)
    match = re.search(r'^chapter_0*(\d+)(.*)$', fallback_name, re.IGNORECASE)
    if match:
        suffix = match.group(2).replace('_', ' ').strip()
        if suffix:
            return f"Chapter {match.group(1)} {suffix}"
        return f"Chapter {match.group(1)}"
        
    return fallback_name

def determine_output_filename(inputs, output_arg):
    if output_arg:
        return output_arg
    
    # If not provided, try to derive from the input
    if len(inputs) == 1:
        p = inputs[0]
        if p.is_dir():
            return f"{p.name}.epub"
        else:
            return f"{p.stem}.epub"
    
    return "output.epub"

def format_book_title(raw_title):
    """Format title by removing hyphens/underscores and applying Title Case."""
    clean_title = raw_title.replace("-", " ").replace("_", " ")
    stop_words = {"a", "an", "the", "and", "but", "or", "for", "nor", "on", "at", "to", "from", "by", "of", "in"}
    words = clean_title.split()
    capitalized_words = []
    for i, word in enumerate(words):
        if i == 0 or word.lower() not in stop_words:
            capitalized_words.append(word.capitalize())
        else:
            capitalized_words.append(word.lower())
    return " ".join(capitalized_words)

def main():
    parser = argparse.ArgumentParser(description="Convert Markdown files to EPUB.")
    parser.add_argument('-i', '--input', nargs='+', required=True, type=pathlib.Path,
                        help="Input file(s) or directory containing Markdown files.")
    parser.add_argument('-o', '--output', type=str,
                        help="Optional output EPUB filename.")
    
    args = parser.parse_args()

    # Gather files
    md_files = []
    for p in args.input:
        if p.is_file() and p.suffix.lower() == '.md':
            md_files.append(p)
        elif p.is_dir():
            md_files.extend([f for f in p.iterdir() if f.is_file() and f.suffix.lower() == '.md'])
        else:
            if not p.exists():
                print(f"Warning: Path '{p}' does not exist.", file=sys.stderr)
            elif p.is_file():
                print(f"Warning: File '{p}' is not a .md file.", file=sys.stderr)
            
    if not md_files:
        print("Error: No Markdown files found in the specified inputs.", file=sys.stderr)
        sys.exit(1)

    # Sort files naturally (chronologically based on numbers in filename)
    md_files.sort(key=natural_sort_key)

    # Determine Output filename
    output_filename = determine_output_filename(args.input, args.output)

    # Determine raw book title from inputs
    if len(args.input) == 1:
        p = args.input[0]
        raw_book_title = p.name if p.is_dir() else p.stem
    else:
        raw_book_title = pathlib.Path(output_filename).stem
        
    formatted_book_title = format_book_title(raw_book_title)

    # 1. Initialize the EPUB Book
    book = epub.EpubBook()
    
    book.set_identifier(str(uuid.uuid4()))
    book.set_title(formatted_book_title)
    book.set_language('en')

    # Create the HTML for the Text-Only Cover/Title Page
    title_html = f"""
    <div style="display: flex; flex-direction: column; justify-content: center; align-items: center; height: 100vh; text-align: center;">
        <h1 style="font-size: 3em; margin-bottom: 0.2em;">{formatted_book_title}</h1>
    </div>
    """
    
    # Turn it into an EPUB chapter object
    title_page = epub.EpubHtml(title='Title Page', file_name='title.xhtml', lang='en')
    title_page.content = title_html
    
    # Add it to the book
    book.add_item(title_page)

    chapters = []
    toc_links = []
    
    for i, file_path in enumerate(md_files):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            print(f"Error reading {file_path}: {e}", file=sys.stderr)
            continue
            
        # Extract title from markdown headers, or fallback to filename
        chapter_title = extract_title(content, file_path.stem)
        
        # Convert Markdown to HTML
        html_content = markdown.markdown(content)
        
        # Create EPUB chapter
        file_name = f'chap_{i:04d}.xhtml'
        chapter = epub.EpubHtml(title=chapter_title, file_name=file_name, lang='en')
        chapter.content = html_content
        
        book.add_item(chapter)
        chapters.append(chapter)
        
        # Add to TOC links
        toc_links.append(epub.Link(file_name, chapter_title, file_name.replace('.xhtml', '')))
        
    if not chapters:
        print("Error: No valid chapters to add.", file=sys.stderr)
        sys.exit(1)

    # Define the Table of Contents (TOC)
    # Include the Title Page and the TOC itself in the system navigation menu
    title_link = epub.Link('title.xhtml', 'Title Page', 'title_page')
    nav_link = epub.Link('nav.xhtml', 'Table of Contents', 'toc_link')
    book.toc = (title_link, nav_link) + tuple(toc_links)

    # Add the Required Navigational Files (TOC menu)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    # Set the Guide so e-reader buttons know where important pages are
    book.guide = [
        {"type": "title-page", "title": "Title Page", "href": "title.xhtml"},
        {"type": "toc", "title": "Table of Contents", "href": "nav.xhtml"}
    ]
    
    # Define the Spine (Reading order)
    book.spine = [title_page, 'nav'] + chapters

    # Compile and write the EPUB file
    try:
        epub.write_epub(output_filename, book, {})
        print(f"Successfully created EPUB: {output_filename}")
        print(f"Added {len(chapters)} chapters.")
    except Exception as e:
        print(f"Error writing EPUB: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()
