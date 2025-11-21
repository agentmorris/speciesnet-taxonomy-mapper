# SpeciesNet Taxonomy Mapper

A web-based tool to assist ecologists in mapping user-defined species lists to the [SpeciesNet](https://github.com/google/cameratrapai) taxonomy. It uses exact matching, heuristic parsing, and Google Gemini (LLM) for soft matching of unknown terms.

## Features

*   **Input Handling**: Supports single names or "Common, Latin" / "Latin, Common" pairs.
*   **Interactive & Iterative Workflow**:
    *   View mapped results in an interactive preview panel.
    *   Each output row is editable, allowing for manual corrections.
    *   **Row Locking**: Lock correct mappings to prevent them from being changed.
    *   **Partial Reprocessing**: When you re-run the tool, only unlocked rows are sent for processing, saving time and API calls.
*   **Gemini Integration**:
    *   Uses Google's Gemini models to suggest mappings for ambiguous or unknown terms.
    *   Accepts a server-default API key or a **custom, user-provided key** for a specific session.
*   **Location Context**: Accepts a study area (e.g., "Alberta, Canada") to improve LLM disambiguation.

## Workflow

The UI is designed for an iterative workflow where you can refine your results efficiently.

1.  **Initial Processing**: Paste your species list into the left-hand input panel and click "Process Input".
2.  **Review & Lock**: The right-hand panel will populate with the mapped results. Review each line. If a line is correct, click the **Unlock icon** (<i class="bi bi-unlock"></i>) next to it. The icon will change to a **Lock icon** (<i class="bi bi-lock-fill"></i>), and the row will be protected from future changes.
3.  **Correct & Edit**: For any incorrect mappings, go back to the left-hand input panel and edit the corresponding line to be more specific. You can also directly edit the text in the unlocked output rows on the right.
4.  **Reprocess**: Click "Process Input" again. Only the information for the unlocked rows will be sent to the backend. Your locked rows will remain untouched.
5.  **Download**: Once you are satisfied with all the mappings, click "Download CSV".

## Prerequisites

*   Python 3.9+
*   A SpeciesNet taxonomy file (e.g., `taxonomy_release.txt`) - **Required**
*   (Optional) Google Gemini API Key

## Setup & Local Execution

1.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

2.  **Place Taxonomy File**:
    Copy or symlink your `taxonomy_release.txt` file to the project root directory. This file is **required** - the app will not start without it.
    *(Alternatively, set the `TAXONOMY_PATH` environment variable to point to the file location)*.

3.  **Configure API Key (Server Default)**:
    Create a file named `gemini-key.txt` in the project root and paste your Google Gemini API key into it. This will be the default key.
    *(Alternatively, set the `GOOGLE_API_KEY` environment variable)*.

4.  **Run the Application**:
    ```bash
    python app.py
    ```
    Access the app at [http://127.0.0.1:5000](http://127.0.0.1:5000).

## Docker Deployment

The application is containerized for easy deployment on Linux servers.

1.  **Prepare Configuration**:
    *   Place `taxonomy_release.txt` in the project root directory (**required**).
    *   Ensure `gemini-key.txt` is present in the project root.

2.  **Build and Run**:
    ```bash
    docker-compose up --build
    ```

The `docker-compose.yml` is pre-configured to mount both files from the current directory. If you need to use a different location for the taxonomy file, you can either modify the volume mount in `docker-compose.yml` or set the `TAXONOMY_PATH` environment variable in the Docker configuration.

## Command-Line Testing Interface

The `matcher.py` script can be run directly from the command line to test individual species mappings:

```bash
# Single query
python matcher.py --query "brown creeper"

# Multiple queries (semicolon-delimited)
python matcher.py --query "brown creeper; american three-toed woodpecker; weasel"

# With location context
python matcher.py --query "deer; elk; moose" --location "British Columbia"

# Verbose mode for detailed debugging
python matcher.py --query "brown creeper" --location "British Columbia" --verbose
```

**Verbose mode** shows:
- How the input was parsed
- What Gemini suggested (including full taxonomic hierarchy)
- Which taxonomic level matched (species/genus/family/order/class)
- Why matches might fail

This is useful for debugging mapping issues and understanding how species are being matched to the taxonomy.

## Hierarchical Matching

The app supports hierarchical taxonomic matching when a species is not in the SpeciesNet taxonomy but a higher-level taxon is available:

1. **Gemini provides full taxonomy**: For each candidate match, Gemini returns the complete taxonomic hierarchy (class, order, family, genus, species)

2. **Hierarchical search**: If the species isn't found, the app tries matching at genus level, then family, order, and class

3. **Uniqueness checking**: After processing all inputs:
   - If only one input matches a higher-level taxon (e.g., "Picoides") → the match is kept
   - If multiple inputs match the same taxon → all are marked as failed (ambiguous)

For example, "american three-toed woodpecker" might not be in SpeciesNet as a species, but if the genus "Picoides" is present and no other input also maps to "Picoides", the mapping will succeed with "picoides" in the Latin column.

## Debugging Gemini Models

If you encounter errors regarding the Gemini model version (e.g., "404 model not found"):

1.  Ensure your API key is correct in `gemini-key.txt`.
2.  Run the debug script to list valid models for your account:
    ```bash
    python list_models.py
    ```
3.  Update the model name in `matcher.py` if necessary.

## TODO

1. Consider replacing calls to Gemini with an in-browser, open-weights LLM, e.g. via transfomers.js .