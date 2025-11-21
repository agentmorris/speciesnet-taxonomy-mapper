from flask import Flask, render_template, request, Response, send_file
import io
import csv
import os
import sys
from taxonomy import TaxonomyLoader
from matcher import Matcher

app = Flask(__name__)

# Configuration
# Allow overriding via env var for Docker/Deployment
TAXONOMY_FILE = os.environ.get("TAXONOMY_PATH", "taxonomy_release.txt")

# Global objects
taxonomy = None
matcher = None

def init_app():
    global taxonomy, matcher

    # Verify taxonomy file exists before proceeding
    if not os.path.exists(TAXONOMY_FILE):
        print(f"ERROR: Required taxonomy file not found: {TAXONOMY_FILE}", file=sys.stderr)
        print(f"Please ensure 'taxonomy_release.txt' is in the current directory,", file=sys.stderr)
        print(f"or set the TAXONOMY_PATH environment variable to point to the file.", file=sys.stderr)
        sys.exit(1)

    print(f"Loading taxonomy from: {TAXONOMY_FILE}")
    taxonomy = TaxonomyLoader(TAXONOMY_FILE)
    matcher = Matcher(taxonomy)
    print("Taxonomy loaded successfully.")

# Initialize on module load (for dev server)
init_app()

@app.route('/')
def index():
    return render_template('index.html', gemini_available=matcher.is_available())

@app.route('/process', methods=['POST'])
def process():
    input_text = request.form.get('input_text', '')
    location = request.form.get('location', '')
    user_api_key = request.form.get('user_api_key', '').strip()
    
    results = matcher.process_input(input_text, location=location, user_api_key=user_api_key)
    
    # Generate CSV
    output = io.StringIO()
    writer = csv.writer(output)
    # Header: latin,common,original_latin,original_common
    writer.writerow(['latin', 'common', 'original_latin', 'original_common'])
    
    for row in results:
        writer.writerow([
            row['latin'],
            row['common'],
            row['original_latin'],
            row['original_common']
        ])
    
    output.seek(0)
    
    return Response(
        output.getvalue(),
        mimetype="text/plain"
    )

if __name__ == '__main__':
    app.run(debug=True, port=5000)
