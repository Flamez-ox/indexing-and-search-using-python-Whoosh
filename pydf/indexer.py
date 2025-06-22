from whoosh.index import create_in, open_dir, exists_in
from whoosh.fields import Schema, TEXT, ID, STORED, NUMERIC
import os
import subprocess
import shutil
import glob
import configparser
from os.path import basename, splitext
from bs4 import BeautifulSoup

# --- Helper Functions ---

def fileid(filepath):
    return splitext(basename(filepath))[0]

def parse_html(filename):
    with open(filename, encoding='utf-8') as infile:
        html = BeautifulSoup(infile, "html.parser")

        d = {}
        pre_tag = html.find('pre')
        d['text'] = pre_tag.text if pre_tag else '[No <pre> tag found in HTML]'
        d['title'] = html.title.text if html.title else 'Untitled'

        for meta in html.find_all('meta'):
            name = meta.get('name', '').lower()
            content = meta.get('content', '').strip()
            if name in ('author', 'title', 'year', 'language', 'doc_type'):
                d[name] = content

        # Ensure required fields have defaults
        d.setdefault('author', 'Unknown')
        d.setdefault('year', 0)
        d.setdefault('language', 'Unknown')
        d.setdefault('doc_type', 'Unknown')

        return d

def pdftotext(pdf, sourcedir='.', p2t='pdftotext', move=False):
    filename = fileid(pdf)
    htmlpath = os.path.join(sourcedir, filename + '.html')
    sourcepath = os.path.join(sourcedir, filename + '.pdf')

    if not os.path.exists(sourcedir):
        os.makedirs(sourcedir)

    # Convert PDF to HTML with meta tags
    subprocess.call([p2t, '-enc', 'UTF-8', '-htmlmeta', pdf, htmlpath])

    # Parse HTML and extract data
    data = parse_html(htmlpath)
    os.remove(htmlpath)

    # Move or copy PDF to source directory
    if os.path.abspath(pdf) != os.path.abspath(sourcepath):
        (shutil.move if move else shutil.copy)(pdf, sourcepath)

    data['source'] = sourcepath
    data['id'] = filename

    # Convert year to int or fallback to 0
    try:
        data['year'] = int(data.get('year', 0))
    except ValueError:
        data['year'] = 0

    return data

# --- Indexing Function ---

def index_collection(configpath):
    config = configparser.ConfigParser()
    config.read(configpath)

    recompile = config.getboolean("indexer.options", "recompile")
    index_dir = config.get("filepaths", "index directory")
    source_dir = config.get("filepaths", "source directory")
    pdf_dirs = config.get("filepaths", "pdf directory").split(';')
    pdftotext_path = config.get("programpaths", "pdftotext").strip("'\"")
    move_files = config.getboolean("indexer.options", "move")

    # Schema definition
    schema = Schema(
        id=ID(stored=True, unique=True),
        title=TEXT(stored=True),
        author=TEXT(stored=True),
        text=TEXT(stored=True),
        year=NUMERIC(stored=True),
        language=TEXT(stored=True),
        doc_type=TEXT(stored=True),
        source=STORED
    )

    # Initialize or open index
    if not exists_in(index_dir):
        os.makedirs(index_dir, exist_ok=True)
        ix = create_in(index_dir, schema=schema)
    else:
        ix = open_dir(index_dir)

    writer = ix.writer()
    indexed_ids = set()

    if not recompile:
        with ix.searcher() as searcher:
            for hit in searcher.all_stored_fields():
                indexed_ids.add(hit['id'])

    for directory in pdf_dirs:
        directory = directory.strip().strip('"')
        for filepath in glob.glob(os.path.join(directory, "*.pdf")):
            fid = fileid(filepath)
            if recompile or fid not in indexed_ids:
                try:
                    data = pdftotext(
                        filepath,
                        sourcedir=source_dir,
                        p2t=pdftotext_path,
                        move=move_files
                    )
                    writer.add_document(
                        id=data['id'],
                        title=data.get('title', ''),
                        author=data.get('author', ''),
                        text=data['text'],
                        year=data.get('year', ),
                        language=data.get('language', ''),
                        doc_type=data.get('doc_type', 'Unknown'),
                        source=data.get('source', '')
                    )
                    print(f"Indexed: {fid}")
                except Exception as error:
                    print(f"Error indexing {filepath}: {error}")
            else:
                print(f"Skipped (already indexed): {fid}")

    writer.commit()

# --- Run the Indexer ---

if __name__ == "__main__":
    index_collection("INI file path here")  # Replace with actual path to your config file
