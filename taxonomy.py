import os
import csv

class TaxonomyLoader:
    def __init__(self, taxonomy_path):
        self.taxonomy_path = taxonomy_path
        self.latin_to_row = {}
        self.common_to_row = {}
        self.valid_latin_names = set()
        self.load()

    def load(self):
        if not os.path.exists(self.taxonomy_path):
            print(f"Warning: Taxonomy file not found at {self.taxonomy_path}")
            return

        with open(self.taxonomy_path, 'r', encoding='utf-8') as f:
            # The file is semicolon delimited, no header based on 'head' output
            # Format: GUID;class;order;family;genus;species;common
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(';')
                if len(parts) < 7:
                    continue

                # Extract parts
                guid = parts[0]
                # class_ = parts[1] # Reserved word
                # order = parts[2]
                # family = parts[3]
                genus = parts[4]
                species_epithet = parts[5]
                common_name = parts[6]

                # Construct standard Latin name
                if species_epithet:
                    latin_name = f"{genus} {species_epithet}".lower()
                elif genus:
                    latin_name = genus.lower()
                elif parts[3]: # Family
                    latin_name = parts[3].lower()
                elif parts[2]: # Order
                    latin_name = parts[2].lower()
                elif parts[1]: # Class
                    latin_name = parts[1].lower()
                else:
                    continue # Should not happen for valid rows

                # Store mapping
                # We store the whole row (parts) or a structured dict to retrieve canonical casing later
                entry = {
                    "latin": latin_name, # standardized lowercase
                    "common": common_name, # canonical common name
                    "line_parts": parts
                }

                self.latin_to_row[latin_name] = entry
                self.valid_latin_names.add(latin_name)

                if common_name:
                    self.common_to_row[common_name.lower()] = entry

    def get_by_latin(self, latin_name):
        return self.latin_to_row.get(latin_name.lower().strip())

    def get_by_common(self, common_name):
        return self.common_to_row.get(common_name.lower().strip())

    def get_by_hierarchy(self, tax_class=None, tax_order=None, tax_family=None, tax_genus=None, tax_species=None):
        """
        Try to find a match in the taxonomy by searching hierarchically from species up to class.
        Returns a tuple: (matched_entry, taxonomic_level) or (None, None) if no match.
        taxonomic_level is one of: 'species', 'genus', 'family', 'order', 'class'
        """
        # Normalize inputs to lowercase
        if tax_class: tax_class = tax_class.lower().strip()
        if tax_order: tax_order = tax_order.lower().strip()
        if tax_family: tax_family = tax_family.lower().strip()
        if tax_genus: tax_genus = tax_genus.lower().strip()
        if tax_species: tax_species = tax_species.lower().strip()

        # Try species level first (genus + species)
        if tax_genus and tax_species:
            species_name = f"{tax_genus} {tax_species}"
            entry = self.get_by_latin(species_name)
            if entry:
                return (entry, 'species')

        # Try genus level
        if tax_genus:
            entry = self.get_by_latin(tax_genus)
            if entry:
                return (entry, 'genus')

        # Try family level
        if tax_family:
            entry = self.get_by_latin(tax_family)
            if entry:
                return (entry, 'family')

        # Try order level
        if tax_order:
            entry = self.get_by_latin(tax_order)
            if entry:
                return (entry, 'order')

        # Try class level
        if tax_class:
            entry = self.get_by_latin(tax_class)
            if entry:
                return (entry, 'class')

        return (None, None)
