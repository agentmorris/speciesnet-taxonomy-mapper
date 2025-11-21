import re
import os
import google.generativeai as genai
from taxonomy import TaxonomyLoader

# Configure Gemini
API_KEY = os.environ.get("GOOGLE_API_KEY")

# Try reading from gemini-key.txt
if not API_KEY and os.path.exists("gemini-key.txt"):
    try:
        with open("gemini-key.txt", "r") as f:
            API_KEY = f.read().strip()
    except Exception as e:
        print(f"Error reading gemini-key.txt: {e}")

if API_KEY:
    genai.configure(api_key=API_KEY)

class Matcher:
    def __init__(self, taxonomy_loader: TaxonomyLoader):
        self.taxonomy = taxonomy_loader
        self.model = None
        if API_KEY:
            try:
                # User requested gemini-2.5-flash
                # Note: If this model doesn't exist, run list_models.py to find valid names
                self.model = genai.GenerativeModel('gemini-2.5-flash')
            except Exception as e:
                print(f"Failed to initialize Gemini: {e}")

    def is_available(self):
        return self.model is not None

    def process_input(self, input_text, location=None, user_api_key=None):
        """
        Process a full block of text and return list of result rows.
        Result row: { 'latin': ..., 'common': ..., 'original_latin': ..., 'original_common': ... }
        """
        lines = input_text.splitlines()
        results = []

        # First pass: Exact matching and parsing
        unknown_lines = []

        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue

            result = self.match_single_line_exact(line)
            if result['latin']:
                results.append(result)
            else:
                # If no exact match, mark for Gemini processing
                # We still create a result entry, but it might be incomplete
                unknown_lines.append((i, line, result))
                results.append(result) # Placeholder, will update later

        # Second pass: Batch Gemini processing for unknowns
        if unknown_lines and (self.model or user_api_key):
            self.batch_process_with_gemini(unknown_lines, results, location, user_api_key)

        # Third pass: Resolve ambiguous higher-level matches
        self.resolve_ambiguous_matches(results)

        return results

    def match_single_line_exact(self, line):
        """
        Attempts to match a single line against the taxonomy using exact string matching.
        """
        parts = [p.strip() for p in line.split(',')]
        
        original_latin = ""
        original_common = ""
        mapped_latin = ""
        mapped_common = ""
        
        match_found = False

        # Case 1: Single token
        if len(parts) == 1:
            token = parts[0]
            # Try as Latin
            row = self.taxonomy.get_by_latin(token)
            if row:
                match_found = True
                original_latin = token
                mapped_latin = row['latin']
                mapped_common = row['common']
            else:
                # Try as Common
                row = self.taxonomy.get_by_common(token)
                if row:
                    match_found = True
                    original_common = token
                    mapped_latin = row['latin']
                    mapped_common = row['common']
                else:
                    # Unknown single token
                    # Default to original_common as a fallback for single strings
                    original_common = token

        # Case 2: Two tokens (A, B)
        elif len(parts) >= 2:
            # We only consider the first two for matching logic for now
            p0 = parts[0]
            p1 = parts[1]
            
            row0_l = self.taxonomy.get_by_latin(p0)
            row0_c = self.taxonomy.get_by_common(p0)
            row1_l = self.taxonomy.get_by_latin(p1)
            row1_c = self.taxonomy.get_by_common(p1)

            # Heuristic: Latin, Common
            if row0_l and not row1_l:
                 # p0 is Latin.
                 match_found = True
                 original_latin = p0
                 original_common = p1 # Assume p1 is common
                 mapped_latin = row0_l['latin']
                 mapped_common = row0_l['common']
            
            # Heuristic: Common, Latin
            elif row1_l and not row0_l:
                match_found = True
                original_latin = p1
                original_common = p0
                mapped_latin = row1_l['latin']
                mapped_common = row1_l['common']

            # Heuristic: Common, Common (ambiguous, pick first valid?)
            elif row0_c:
                 match_found = True
                 original_common = p0
                 # p1 might be original latin but unmatched?
                 if not self.is_likely_latin(p1):
                     original_latin = "" # p1 is just extra info?
                 else:
                     original_latin = p1
                 
                 mapped_latin = row0_c['latin']
                 mapped_common = row0_c['common']
            
            elif row1_c:
                 match_found = True
                 original_common = p1
                 if self.is_likely_latin(p0):
                     original_latin = p0
                 
                 mapped_latin = row1_c['latin']
                 mapped_common = row1_c['common']

            else:
                # Neither matched
                original_common = line # fallback? Or split?
                # Let's try to preserve structure
                # Assume Common, Latin if unsure? Or just keep full line?
                # User said: "unmatched text should be placed in original common/latin"
                # Let's dump everything in original_common for now, or try to guess.
                # If it looks like "Name, Latin", split it.
                original_common = p0
                original_latin = p1

        return {
            'latin': mapped_latin,
            'common': mapped_common,
            'original_latin': original_latin,
            'original_common': original_common,
            'raw_input': line
        }

    def is_likely_latin(self, text):
        # Very basic heuristic: 1 or 2 words, no special chars usually
        # Latin names are usually "Genus" or "Genus species"
        words = text.split()
        return len(words) <= 2

    def batch_process_with_gemini(self, unknown_items, results_list, location=None, user_api_key=None):
        """
        unknown_items: list of (index, line_text, result_dict)
        """
        model_to_use = self.model
        
        if user_api_key:
            try:
                # Configure a temporary client for this request
                temp_genai = genai.GenerativeModel(
                    model_name='gemini-2.5-flash',
                    safety_settings=None, # Or configure as needed
                    generation_config=None,
                    tools=None,
                    request_options={'api_key': user_api_key}
                )
                model_to_use = temp_genai
            except Exception as e:
                print(f"Failed to initialize Gemini with user-provided key: {e}")
                # Fallback to default model or just return
                if not model_to_use:
                    return
        
        if not model_to_use:
            print("Gemini processing skipped: no model available.")
            return

        # Construct prompt
        prompt_lines = ["Map the following biological terms to their standard scientific (Latin) name and Common name."]
        if location:
             prompt_lines.append(f"Context: The species are observed in {location}.")
        prompt_lines.append("For each term, provide multiple candidate identifications in order of likelihood, as different taxonomies may use different names.")
        prompt_lines.append("For each candidate, include the full taxonomic hierarchy (class, order, family, genus, species).")
        prompt_lines.append("Return the result as a JSON list of objects with keys:")
        prompt_lines.append("  - 'input_text': the original input")
        prompt_lines.append("  - 'candidates': array of candidate objects, each with:")
        prompt_lines.append("      - 'class': taxonomic class")
        prompt_lines.append("      - 'order': taxonomic order")
        prompt_lines.append("      - 'family': taxonomic family")
        prompt_lines.append("      - 'genus': taxonomic genus")
        prompt_lines.append("      - 'species': species epithet (not the full binomial, just the species part)")
        prompt_lines.append("  - 'suggested_common': the most common English name")
        prompt_lines.append("If you cannot identify a term, set candidates to an empty array.")
        prompt_lines.append("Items:")
        
        batch_mapping = {} # index -> input_text
        
        for idx, text, _ in unknown_items:
            prompt_lines.append(f"- {text}")
            batch_mapping[idx] = text

        prompt = "\n".join(prompt_lines)

        try:
            response = model_to_use.generate_content(prompt)
            # Parse JSON response. Gemini might wrap in ```json ... ```
            content = response.text
            # Basic cleanup
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            
            import json
            data = json.loads(content)
            
            # Update results
            # We need to map back. The list order should be preserved, but let's use string matching if possible or just order.
            # Actually, asking for 'input_text' back is safer.
            
            for item in data:
                inp = item.get('input_text')
                candidates = item.get('candidates', [])

                # Backward compatibility: support old format with candidate_latin_names
                if not candidates and item.get('candidate_latin_names'):
                    candidates = [{'genus': name.split()[0] if ' ' in name else name,
                                   'species': name.split()[1] if ' ' in name and len(name.split()) > 1 else None}
                                  for name in item.get('candidate_latin_names', [])]

                if not inp:
                    continue

                matched_entry = None
                matched_level = None

                # Try each candidate with hierarchical matching
                for candidate in candidates:
                    if not candidate:
                        continue

                    entry, level = self.taxonomy.get_by_hierarchy(
                        tax_class=candidate.get('class'),
                        tax_order=candidate.get('order'),
                        tax_family=candidate.get('family'),
                        tax_genus=candidate.get('genus'),
                        tax_species=candidate.get('species')
                    )

                    if entry:
                        matched_entry = entry
                        matched_level = level
                        break

                # If no hierarchical match, try the common name as fallback
                if not matched_entry:
                    s_common_gemini = item.get('suggested_common')
                    if s_common_gemini:
                        matched_entry = self.taxonomy.get_by_common(s_common_gemini)
                        if matched_entry:
                            matched_level = 'common_name_fallback'

                # Update the corresponding result in results_list
                # Find the result with raw_input == inp
                for res in results_list:
                    if res['raw_input'] == inp and not res['latin']:
                        if matched_entry:
                            res['latin'] = matched_entry['latin']
                            res['common'] = matched_entry['common']
                            res['match_level'] = matched_level  # Store for uniqueness checking
                        break

        except Exception as e:
            print(f"Gemini Batch Error: {e}")
            # Fallback: Do nothing, results remain empty

    def resolve_ambiguous_matches(self, results):
        """
        Post-processing step to handle ambiguous higher-level matches.
        If multiple inputs matched to the same genus/family/order/class, mark them all as failed.
        If only one input matched to a higher-level taxon, keep it.
        Species-level matches are always kept.
        """
        # Group results by matched taxon (latin name) and match level
        # Only consider higher-level matches (not species or exact matches)
        higher_level_matches = {}  # latin_name -> list of result indices

        for i, result in enumerate(results):
            match_level = result.get('match_level')
            latin = result.get('latin')

            # Only consider higher-level matches (genus, family, order, class)
            if match_level and match_level in ['genus', 'family', 'order', 'class'] and latin:
                if latin not in higher_level_matches:
                    higher_level_matches[latin] = []
                higher_level_matches[latin].append(i)

        # For each higher-level taxon that has multiple matches, clear those results
        for latin_name, indices in higher_level_matches.items():
            if len(indices) > 1:
                # Multiple inputs matched to the same higher-level taxon - ambiguous!
                for idx in indices:
                    results[idx]['latin'] = ''
                    results[idx]['common'] = ''
                    results[idx]['match_level'] = 'ambiguous'  # Mark as ambiguous for debugging


if __name__ == '__main__':
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description='Test taxonomy matching from command line',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  python matcher.py --query "brown creeper"
  python matcher.py --query "weasel, mustela; bear, ursus"
  python matcher.py --query "brown creeper" --verbose
  python matcher.py --query "deer; elk; moose" --location "Alberta, Canada"
        '''
    )
    parser.add_argument('--query', required=True,
                        help='Semicolon-delimited list of species queries (each may contain commas)')
    parser.add_argument('--location', default=None,
                        help='Study area location for context (e.g., "Alberta, Canada")')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Show detailed matching information and debug output')

    args = parser.parse_args()

    # Load taxonomy
    taxonomy_file = os.environ.get("TAXONOMY_PATH", "taxonomy_release.txt")
    if not os.path.exists(taxonomy_file):
        print(f"ERROR: Taxonomy file not found: {taxonomy_file}", file=sys.stderr)
        print(f"Please ensure 'taxonomy_release.txt' is in the current directory.", file=sys.stderr)
        sys.exit(1)

    print(f"Loading taxonomy from: {taxonomy_file}")
    taxonomy = TaxonomyLoader(taxonomy_file)
    matcher = Matcher(taxonomy)

    if not matcher.is_available():
        print("WARNING: Gemini is not available. Only exact matching will be performed.", file=sys.stderr)
        print("To enable Gemini: Set GOOGLE_API_KEY environment variable or create gemini-key.txt", file=sys.stderr)

    # Parse queries (semicolon-delimited)
    queries = [q.strip() for q in args.query.split(';') if q.strip()]

    if args.verbose:
        print(f"\n{'='*60}")
        print(f"Processing {len(queries)} quer{'y' if len(queries) == 1 else 'ies'}")
        print(f"{'='*60}\n")

    # Process queries
    input_text = '\n'.join(queries)

    # For verbose mode, we need to intercept the matching process
    if args.verbose:
        # Process each query individually for detailed output
        for i, query in enumerate(queries, 1):
            print(f"Query {i}: '{query}'")
            print("-" * 60)

            # Try exact matching first
            result = matcher.match_single_line_exact(query)

            print(f"  Input parsing:")
            print(f"    Original Latin:  '{result['original_latin']}'")
            print(f"    Original Common: '{result['original_common']}'")

            if result['latin']:
                print(f"\n  ✓ EXACT MATCH FOUND")
                print(f"    Mapped Latin:  {result['latin']}")
                print(f"    Mapped Common: {result['common']}")
            else:
                print(f"\n  ✗ No exact match found")

                # Try individual lookups for debugging
                parts = [p.strip() for p in query.split(',')]
                for part in parts:
                    latin_row = taxonomy.get_by_latin(part)
                    common_row = taxonomy.get_by_common(part)
                    if latin_row:
                        print(f"    '{part}' found as Latin: {latin_row['latin']} ({latin_row['common']})")
                    elif common_row:
                        print(f"    '{part}' found as Common: {common_row['latin']} ({common_row['common']})")
                    else:
                        print(f"    '{part}' not found in taxonomy")

                # Try Gemini if available
                if matcher.is_available():
                    print(f"\n  Attempting Gemini lookup...")

                    # Make a direct call to see what Gemini suggests
                    try:
                        import json

                        # Build prompt (same as batch processing)
                        prompt_lines = ["Map the following biological terms to their standard scientific (Latin) name and Common name."]
                        if args.location:
                            prompt_lines.append(f"Context: The species are observed in {args.location}.")
                        prompt_lines.append("For each term, provide multiple candidate identifications in order of likelihood, as different taxonomies may use different names.")
                        prompt_lines.append("For each candidate, include the full taxonomic hierarchy (class, order, family, genus, species).")
                        prompt_lines.append("Return the result as a JSON list of objects with keys:")
                        prompt_lines.append("  - 'input_text': the original input")
                        prompt_lines.append("  - 'candidates': array of candidate objects, each with:")
                        prompt_lines.append("      - 'class': taxonomic class")
                        prompt_lines.append("      - 'order': taxonomic order")
                        prompt_lines.append("      - 'family': taxonomic family")
                        prompt_lines.append("      - 'genus': taxonomic genus")
                        prompt_lines.append("      - 'species': species epithet (not the full binomial, just the species part)")
                        prompt_lines.append("  - 'suggested_common': the most common English name")
                        prompt_lines.append("If you cannot identify a term, set candidates to an empty array.")
                        prompt_lines.append("Items:")
                        prompt_lines.append(f"- {query}")
                        prompt = "\n".join(prompt_lines)

                        response = matcher.model.generate_content(prompt)
                        content = response.text

                        print(f"  Gemini raw response:")
                        print(f"    {content[:400]}{'...' if len(content) > 400 else ''}")

                        # Parse response
                        if "```json" in content:
                            content = content.split("```json")[1].split("```")[0]
                        elif "```" in content:
                            content = content.split("```")[1].split("```")[0]

                        data = json.loads(content.strip())

                        if data and len(data) > 0:
                            suggestion = data[0]
                            candidates = suggestion.get('candidates', [])
                            suggested_common = suggestion.get('suggested_common')

                            print(f"\n  Gemini suggestions:")
                            print(f"    Suggested Common: {suggested_common}")
                            print(f"    Candidates (in order):")

                            if candidates:
                                for i, candidate in enumerate(candidates, 1):
                                    tax_class = candidate.get('class', '')
                                    tax_order = candidate.get('order', '')
                                    tax_family = candidate.get('family', '')
                                    tax_genus = candidate.get('genus', '')
                                    tax_species = candidate.get('species', '')

                                    full_name = f"{tax_genus} {tax_species}" if tax_species else tax_genus
                                    print(f"      {i}. {full_name}")
                                    print(f"         Hierarchy: {tax_class} > {tax_order} > {tax_family} > {tax_genus}" + (f" > {tax_species}" if tax_species else ""))
                            else:
                                print(f"      (none)")

                            # Try hierarchical matching for each candidate
                            matched_entry = None
                            matched_level = None
                            match_index = None

                            for i, candidate in enumerate(candidates, 1):
                                if candidate:
                                    entry, level = taxonomy.get_by_hierarchy(
                                        tax_class=candidate.get('class'),
                                        tax_order=candidate.get('order'),
                                        tax_family=candidate.get('family'),
                                        tax_genus=candidate.get('genus'),
                                        tax_species=candidate.get('species')
                                    )
                                    if entry:
                                        matched_entry = entry
                                        matched_level = level
                                        match_index = i
                                        break

                            if matched_entry:
                                print(f"\n  ✓ MATCH FOUND IN TAXONOMY (candidate #{match_index})")
                                print(f"    Matched at: {matched_level.upper()} level")
                                print(f"    Mapped Latin:  {matched_entry['latin']}")
                                print(f"    Mapped Common: {matched_entry['common']}")

                                if matched_level != 'species':
                                    print(f"    Note: Matched at {matched_level} level (not species)")
                                    print(f"          This match may be rejected if other inputs also match to '{matched_entry['latin']}'")
                            else:
                                print(f"\n  ✗ No hierarchical match found in taxonomy")

                                # Try the common name as fallback
                                if suggested_common:
                                    row_by_common = taxonomy.get_by_common(suggested_common)
                                    if row_by_common:
                                        print(f"    However, suggested common name IS in taxonomy:")
                                        print(f"      {row_by_common['latin']} ({row_by_common['common']})")
                                    else:
                                        print(f"    Common name also not found in taxonomy.")
                        else:
                            print(f"\n  ✗ Gemini could not identify this species")

                    except Exception as e:
                        print(f"  Error querying Gemini: {e}")
                        import traceback
                        traceback.print_exc()

            print()
    else:
        # Normal mode - process all at once
        results = matcher.process_input(input_text, location=args.location)

        print(f"\n{'Input':<30} {'Latin':<30} {'Common':<30}")
        print("=" * 90)

        for result in results:
            input_display = result['raw_input'][:28] + '..' if len(result['raw_input']) > 30 else result['raw_input']
            latin_display = result['latin'][:28] + '..' if len(result['latin']) > 30 else result['latin']
            common_display = result['common'][:28] + '..' if len(result['common']) > 30 else result['common']

            status = '✓' if result['latin'] else '✗'
            print(f"{status} {input_display:<28} {latin_display:<30} {common_display:<30}")
