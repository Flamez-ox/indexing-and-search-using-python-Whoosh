from flask import Flask, render_template, request, jsonify, send_from_directory
from whoosh.index import open_dir
from whoosh.qparser import MultifieldParser
from html import escape
import os

app = Flask(__name__, template_folder='')

INDEX_DIR = 'INDEX FOLDER PATH HERE'  # Replace with your actual index directory path
PDF_DIR = 'SOURCE FOLDER PATH HERE'  # Replace with your actual PDF directory path

@app.route('/')
def index():
    return render_template('index.html')# Replace with your actual HTML FILE

@app.route('/pdfs/<path:filename>')
def serve_pdf(filename):
    return send_from_directory(PDF_DIR, filename)

def search(query, year_filter=None, year1=None, year2=None, language=None, doc_type=None):
    ix = open_dir(INDEX_DIR)
    with ix.searcher() as searcher:
        parser = MultifieldParser(["text", "title", "author"], schema=ix.schema)
        parsed = parser.parse(query)
        results = searcher.search(parsed, limit=None)

        filtered = []
        for hit in results:
            # Year filter logic
            pub_year = hit.get('year')
            if pub_year:
                try:
                    pub_year = int(pub_year)
                    y1 = int(year1) if year1 else None
                    y2 = int(year2) if year2 else None

                    if year_filter == 'only' and y1 is not None and pub_year != y1:
                        continue
                    elif year_filter == 'before' and y1 is not None and pub_year > y1:
                        continue
                    elif year_filter == 'after' and y1 is not None and pub_year < y1:
                        continue
                    elif year_filter == 'between' and (y1 is None or y2 is None or not (y1 <= pub_year <= y2)):
                        continue
                except ValueError:
                    continue  # skip if year parsing fails

            # Language filter (case-insensitive)
            if language and hit.get('language', '').lower() != language.lower():
                continue

            # Document type filter (case-insensitive)
            if doc_type and hit.get('doc_type', '').lower() != doc_type.lower():
                continue

            # Add highlighted snippet
            snippet = hit.highlights("text") or hit.get("text", "")[:500] + "..."
            d = dict(hit)
            d['snippet'] = snippet
            filtered.append(d)

        return filtered

def to_html(result):
    title = result.get('title') or result.get('id', 'No Title')
    author = result.get('author', '')
    source = result.get('source', '#')
    snippet = result.get('snippet', '')

    pdf_filename = os.path.basename(source)
    pdf_url = f"/static/pdfs/{pdf_filename}"

    title_esc = escape(title)
    author_esc = escape(author)
    snippet_esc = snippet
    pdf_url_esc = escape(pdf_url)

    return f"""
    <div class="search-result">
      <div class="result-title"><a href="{pdf_url_esc}">{title_esc}</a></div>
      <div class="result-author">{author_esc}</div>
      <p class="result-snippet">{snippet_esc}</p>
      <iframe src="{pdf_url_esc}" width="100%" height="200px" style="border: 1px solid #ccc; margin-top: 1rem;"></iframe>
    </div>
    """

@app.route('/searchbox', methods=['POST'])
def searchbox():
    query = request.form.get('q', '').strip()
    language = request.form.get('language', '').strip()
    year_filter = request.form.get('year_filter', '').strip()
    year1 = request.form.get('year1', '').strip()
    year2 = request.form.get('year2', '').strip()
    doc_type = request.form.get('doc_type', '').strip()

    if not query:
        return jsonify({'html': '<p>Please enter a search term.</p>'})

    hits = search(
        query=query,
        year_filter=year_filter or None,
        year1=year1 or None,
        year2=year2 or None,
        language=language or None,
        doc_type=doc_type or None
    )

    html_results = '\n'.join(map(to_html, hits))
    return jsonify({'html': html_results})

if __name__ == '__main__':
    app.run(debug=True, host='localhost', port=5000)
