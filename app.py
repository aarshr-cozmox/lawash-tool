from flask import Flask, request, jsonify
from flask_cors import CORS
import pandas as pd
import json
import os
import unicodedata
import logging
from difflib import SequenceMatcher
from word2number import w2n
import jellyfish
import re

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

STOPWORDS = [
    "what", "is", "the", "center", "centre", "id", "and", "code", "for", "my", "located", "at", "in",
    "show", "me", "tell", "give", "result", "query", "details", "poblacion", "province", "city",
    "de", "la", "el", "los", "las", "en", "y", "del", "a", "please", "por", "favor"
]

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Load data
location_index = {"city": [], "province": []}

def build_location_entries(values):
    entries = []
    seen = set()
    for val in values:
        if not isinstance(val, str):
            continue
        if not val or val in seen:
            continue
        seen.add(val)
        tokens = set(w for w in val.split() if w not in STOPWORDS)
        if not tokens:
            tokens = set(val.split())
        entries.append({"value": val, "tokens": tokens})
    return entries

df = pd.DataFrame()

def normalize_text(text):
    if not isinstance(text, str):
        return ""
    
    # Normalize unicode characters
    text = ''.join(c for c in unicodedata.normalize('NFD', text)
                  if unicodedata.category(c) != 'Mn').lower()
    
    # Convert number words to digits (e.g., "two hundred" -> "200")
    # Define number words to identify sequences
    number_words = {
        'zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine',
        'ten', 'eleven', 'twelve', 'thirteen', 'fourteen', 'fifteen', 'sixteen', 
        'seventeen', 'eighteen', 'nineteen', 'twenty', 'thirty', 'forty', 'fifty',
        'sixty', 'seventy', 'eighty', 'ninety', 'hundred', 'thousand', 'million', 'and'
    }
    
    try:
        words = text.split()
        new_words = []
        i = 0
        
        while i < len(words):
            # Check if current word is a number word
            if words[i] in number_words:
                # Collect consecutive number words (including 'and' as connector)
                number_sequence = []
                j = i
                while j < len(words) and words[j] in number_words:
                    number_sequence.append(words[j])
                    j += 1
                
                # Try to convert the sequence
                try:
                    num_str = " ".join(number_sequence)
                    num = w2n.word_to_num(num_str)
                    new_words.append(str(num))
                    i = j
                except ValueError:
                    # If conversion fails, keep the words as-is
                    new_words.extend(number_sequence)
                    i = j
            else:
                # Not a number word, keep as-is
                new_words.append(words[i])
                i += 1
        
        text = " ".join(new_words)
    except Exception:
        pass  # If conversion fails, keep original text
    
    # Common synonym/alias replacements to align user wording with dataset entries
    replacements = {
        "saint": "sant",
        "san": "sant",
        "andrews": "andreu",
        "andrew": "andreu",
        "andrea": "andreu",
        "andres": "andreu",
        "sardinia": "sardenya",
        "sardenia": "sardenya",
        "della": "de la",
        "dalla": "de la",
        "dela": "de la",
        "barca": "barca",
        "barka": "barca",
        "barqa": "barca",
        "tenerife": "tenerife",
        "tenerfaith": "tenerife"
    }
    for old, new in replacements.items():
        text = re.sub(rf"\b{old}\b", new, text)
        
    return text

def fuzzy_similarity(str1, str2):
    """Calculate similarity ratio between two strings (0.0 to 1.0)"""
    return SequenceMatcher(None, str1, str2).ratio()


def detect_location_candidates(query_tokens, query_string, entries):
    hints = set()
    if not entries or not query_tokens:
        return hints
    for entry in entries:
        tokens = entry['tokens']
        if not tokens:
            continue
        overlap = len(tokens & query_tokens)
        token_ratio = overlap / len(tokens) if tokens else 0
        if overlap == len(tokens) or (len(tokens) > 1 and token_ratio >= 0.6) or (len(tokens) == 1 and overlap == 1):
            hints.add(entry['value'])
            continue
        if overlap >= 1 and token_ratio >= 0.4:
            hints.add(entry['value'])
            continue
        if fuzzy_similarity(query_string, entry['value']) >= 0.88:
            hints.add(entry['value'])
    return hints


DATA_FILE = os.path.join(os.path.dirname(__file__), "centers.json")


def load_data():
    global df, location_index
    try:
        with open(DATA_FILE, 'r') as f:
            data = json.load(f)
        df_local = pd.DataFrame(data.get('centers', []))
        if df_local.empty:
            df = df_local
            location_index["city"] = []
            location_index["province"] = []
            logger.warning("Centers dataset is empty.")
            return
        df_local['norm_nombre'] = df_local['nombre'].apply(lambda x: normalize_text(x))
        df_local['norm_poblacion'] = df_local['poblacion'].apply(lambda x: normalize_text(x))
        df_local['norm_provincia'] = df_local['provincia'].apply(lambda x: normalize_text(x))
        if 'direccion' in df_local.columns:
            df_local['norm_direccion'] = df_local['direccion'].apply(lambda x: normalize_text(x))
        else:
            df_local['norm_direccion'] = ""
        df = df_local
        location_index["city"] = build_location_entries(df['norm_poblacion'].dropna().unique())
        location_index["province"] = build_location_entries(df['norm_provincia'].dropna().unique())
        logger.info("Data loaded successfully. %d centers found.", len(df))
    except Exception as e:
        logger.error(f"Error loading data: {e}")
        df = pd.DataFrame()
        location_index["city"] = []
        location_index["province"] = []


load_data()

@app.route('/api/chat', methods=['POST'])
def chat():
    user_message = request.json.get('message', '').lower()
    
    if df.empty:
        return jsonify({"response": "Sorry, I couldn't get the data."})

    # Normalize query
    normalized_query = normalize_text(user_message)
    
    # Remove stopwords
    raw_words = normalized_query.split()
    raw_clean_tokens = [re.sub(r'[^a-z0-9]', '', w) for w in raw_words]
    query_words = [w for w in raw_words if w not in STOPWORDS]
    machine_keywords = {"machine", "machines", "lavadora", "lavadoras", "washer", "washers", "secadora", "secadoras", "dryer", "dryers", "equipment"}
    machine_info_requested = any(kw in raw_words for kw in machine_keywords)
    code_terms = {"code", "codigo", "codigo", "cod"}
    id_terms = {"id", "identifier", "identificador", "identificacion", "identification"}
    code_requested = any(token in code_terms for token in raw_clean_tokens if token)
    id_requested = any(token in id_terms for token in raw_clean_tokens if token)
    
    if not query_words:
        return jsonify({"response": "Please specify a center name, city, or province."})

    # Pre-calculate normalized columns if not already done
    if 'norm_nombre' not in df.columns and not df.empty:
        df['norm_nombre'] = df['nombre'].apply(normalize_text)
        df['norm_poblacion'] = df['poblacion'].apply(normalize_text)
        df['norm_provincia'] = df['provincia'].apply(normalize_text)
        if 'direccion' in df.columns:
            df['norm_direccion'] = df['direccion'].apply(normalize_text)
        else:
            df['norm_direccion'] = ""
        location_index["city"] = build_location_entries(df['norm_poblacion'].dropna().unique())
        location_index["province"] = build_location_entries(df['norm_provincia'].dropna().unique())

    # Fuzzy matching logic with hybrid scoring
    matches = []  # Store all potential matches with their scores
    query_string = " ".join(query_words)
    query_tokens = set(query_words)
    detected_city_hints = detect_location_candidates(query_tokens, normalized_query, location_index["city"]) if location_index["city"] else set()
    detected_province_hints = detect_location_candidates(query_tokens, normalized_query, location_index["province"]) if location_index["province"] else set()
    filter_by_city = len(detected_city_hints) > 0
    filter_by_province = len(detected_province_hints) > 0
    # Additional normalized versions of tokens for code/id detection
    clean_token = lambda t: re.sub(r'[^a-z0-9]', '', t)
    query_tokens_clean = {clean_token(t) for t in query_tokens if clean_token(t)}
    normalized_query_compact = clean_token(normalized_query)
    
    # Pre-calculate phonetic codes for query tokens
    query_phonetics = {qt: jellyfish.metaphone(qt) for qt in query_tokens if len(qt) > 2}
    
    for _, row in df.iterrows():
        if filter_by_city and row['norm_poblacion'] not in detected_city_hints:
            continue
        if filter_by_province and row['norm_provincia'] not in detected_province_hints:
            continue
        row_id = str(row['id_centro']).lower()
        row_code = str(row['codigo']).lower()
        row_id_clean = clean_token(row_id)
        row_code_clean = clean_token(row_code)
        # 1. Direct Code/ID Match (Highest Priority)
        # Check if any query token exactly matches id_centro or codigo (case-insensitive)
        is_id_match = (row_id in query_tokens or row_id_clean in query_tokens_clean)
        is_code_match = (row_code in query_tokens or row_code_clean in query_tokens_clean)
        
        # Apply strict matching based on user intent
        if id_requested and is_id_match:
            # User asked for ID and we found an ID match
            matches.append({
                "row": row,
                "score": 1.0,
                "reason": "Direct ID match",
                "location_score": 1.0
            })
            continue
        elif code_requested and is_code_match:
            # User asked for Code and we found a Code match
            matches.append({
                "row": row,
                "score": 1.0,
                "reason": "Direct Code match",
                "location_score": 1.0
            })
            continue
        elif not id_requested and not code_requested and (is_id_match or is_code_match):
            # User didn't specify, so match either
            matches.append({
                "row": row,
                "score": 1.0,
                "reason": "Direct Code/ID match",
                "location_score": 1.0
            })
            continue
            
        # Token overlap scoring - must have at least some overlap
        # Remove stopwords from row data for better overlap calculation
        row_nombre_tokens = set([w for w in row['norm_nombre'].split() if w not in STOPWORDS])
        row_poblacion_tokens = set([w for w in row['norm_poblacion'].split() if w not in STOPWORDS])
        row_provincia_tokens = set([w for w in row['norm_provincia'].split() if w not in STOPWORDS])
        row_direccion_tokens = set([w for w in row.get('norm_direccion', '').split() if w not in STOPWORDS])
        
        # Fallback to original tokens if filtering removed everything
        if not row_nombre_tokens: row_nombre_tokens = set(row['norm_nombre'].split())
        if not row_poblacion_tokens: row_poblacion_tokens = set(row['norm_poblacion'].split())
        if not row_provincia_tokens: row_provincia_tokens = set(row['norm_provincia'].split())
        if not row_direccion_tokens and row.get('norm_direccion'):
            row_direccion_tokens = set(row['norm_direccion'].split())
        
        # Check for any token overlap
        nombre_overlap = len(query_tokens & row_nombre_tokens)
        poblacion_overlap = len(query_tokens & row_poblacion_tokens)
        provincia_overlap = len(query_tokens & row_provincia_tokens)
        direccion_overlap = len(query_tokens & row_direccion_tokens)
        # Token-level fuzzy matches to catch close spellings (e.g., "sardinia" vs "sardenya")
        def token_fuzzy_match(target_tokens):
            for qt in query_tokens:
                if len(qt) <= 2:
                    continue
                for tt in target_tokens:
                    if len(tt) <= 2:
                        continue
                    if jellyfish.jaro_winkler_similarity(qt, tt) >= 0.88:
                        return True
            return False
        nombre_token_fuzzy = token_fuzzy_match(row_nombre_tokens)
        poblacion_token_fuzzy = token_fuzzy_match(row_poblacion_tokens)
        provincia_token_fuzzy = token_fuzzy_match(row_provincia_tokens)
        direccion_token_fuzzy = token_fuzzy_match(row_direccion_tokens)
        
        # Phonetic matching
        # Check if query phonetics match row phonetics
        row_nombre_phonetics = {w: jellyfish.metaphone(w) for w in row_nombre_tokens if len(w) > 2}
        row_poblacion_phonetics = {w: jellyfish.metaphone(w) for w in row_poblacion_tokens if len(w) > 2}
        row_provincia_phonetics = {w: jellyfish.metaphone(w) for w in row_provincia_tokens if len(w) > 2}
        row_direccion_phonetics = {w: jellyfish.metaphone(w) for w in row_direccion_tokens if len(w) > 2}
        
        nombre_phonetic_match = any(qp in row_nombre_phonetics.values() for qp in query_phonetics.values())
        poblacion_phonetic_match = any(qp in row_poblacion_phonetics.values() for qp in query_phonetics.values())
        provincia_phonetic_match = any(qp in row_provincia_phonetics.values() for qp in query_phonetics.values())
        direccion_phonetic_match = any(qp in row_direccion_phonetics.values() for qp in query_phonetics.values())
        
        # Also check for substring matches (e.g., "sebastian" in "san sebastian")
        nombre_substring_match = any(
            qt in row['norm_nombre'] or row['norm_nombre'] in qt 
            for qt in query_tokens if len(qt) > 3
        )
        poblacion_substring_match = any(
            qt in row['norm_poblacion'] or row['norm_poblacion'] in qt 
            for qt in query_tokens if len(qt) > 3
        )
        provincia_substring_match = any(
            qt in row['norm_provincia'] or row['norm_provincia'] in qt 
            for qt in query_tokens if len(qt) > 3
        )
        direccion_substring_match = any(
            qt in row.get('norm_direccion', '') or row.get('norm_direccion', '') in qt 
            for qt in query_tokens if len(qt) > 3
        )
        
        # Pre-calculate fuzzy scores for guard and reuse later
        nombre_fuzzy_full = fuzzy_similarity(query_string, row['norm_nombre'])
        poblacion_fuzzy_full = fuzzy_similarity(query_string, row['norm_poblacion'])
        provincia_fuzzy_full = fuzzy_similarity(query_string, row['norm_provincia'])
        direccion_fuzzy_full = fuzzy_similarity(query_string, row.get('norm_direccion', ''))
        fuzzy_override_match = max(nombre_fuzzy_full, poblacion_fuzzy_full, provincia_fuzzy_full, direccion_fuzzy_full) >= 0.7
        
        # Skip if there's no overlap, phonetic match, substring match, token fuzzy, or strong fuzzy match
        if (not fuzzy_override_match and
            nombre_overlap == 0 and poblacion_overlap == 0 and provincia_overlap == 0 and direccion_overlap == 0 and
            not nombre_phonetic_match and not poblacion_phonetic_match and not provincia_phonetic_match and not direccion_phonetic_match and
            not nombre_substring_match and not poblacion_substring_match and not provincia_substring_match and not direccion_substring_match and
            not nombre_token_fuzzy and not poblacion_token_fuzzy and not provincia_token_fuzzy and not direccion_token_fuzzy):
            continue
        
        # Calculate fuzzy similarity for fields with some overlap
        # Only calculate fuzzy if there is some relevance to save computation and reduce noise
        nombre_fuzzy = nombre_fuzzy_full if (nombre_overlap > 0 or nombre_phonetic_match or nombre_substring_match or fuzzy_override_match) else 0
        poblacion_fuzzy = poblacion_fuzzy_full if (poblacion_overlap > 0 or poblacion_phonetic_match or poblacion_substring_match or fuzzy_override_match) else 0
        provincia_fuzzy = provincia_fuzzy_full if (provincia_overlap > 0 or provincia_phonetic_match or provincia_substring_match or fuzzy_override_match) else 0
        direccion_fuzzy = direccion_fuzzy_full if (direccion_overlap > 0 or direccion_phonetic_match or direccion_substring_match or direccion_token_fuzzy or fuzzy_override_match) else 0
        
        # Normalized overlap scores - use Jaccard-like ratio but favor query coverage
        nombre_overlap_score = (nombre_overlap / len(row_nombre_tokens)) if row_nombre_tokens else 0
        poblacion_overlap_score = (poblacion_overlap / len(row_poblacion_tokens)) if row_poblacion_tokens else 0
        provincia_overlap_score = (provincia_overlap / len(row_provincia_tokens)) if row_provincia_tokens else 0
        direccion_overlap_score = (direccion_overlap / len(row_direccion_tokens)) if row_direccion_tokens else 0
        nombre_overlap_score = min(nombre_overlap_score, 1.0)
        poblacion_overlap_score = min(poblacion_overlap_score, 1.0)
        provincia_overlap_score = min(provincia_overlap_score, 1.0)
        direccion_overlap_score = min(direccion_overlap_score, 1.0)
        
        # Boost for phonetic or token-level fuzzy matches
        if nombre_phonetic_match or nombre_token_fuzzy: nombre_overlap_score = max(nombre_overlap_score, 0.6)
        if poblacion_phonetic_match or poblacion_token_fuzzy: poblacion_overlap_score = max(poblacion_overlap_score, 0.6)
        if provincia_phonetic_match or provincia_token_fuzzy: provincia_overlap_score = max(provincia_overlap_score, 0.6)
        if direccion_phonetic_match or direccion_token_fuzzy: direccion_overlap_score = max(direccion_overlap_score, 0.6)

        # Hybrid score: combine fuzzy and overlap, with overlap being more important
        nombre_score = (nombre_fuzzy * 0.3) + (nombre_overlap_score * 0.7)
        poblacion_score = (poblacion_fuzzy * 0.3) + (poblacion_overlap_score * 0.7)
        provincia_score = (provincia_fuzzy * 0.3) + (provincia_overlap_score * 0.7)
        direccion_score = (direccion_fuzzy * 0.4) + (direccion_overlap_score * 0.6)
        
        # Check if this is a strong address match (e.g., "Peru 38")
        # This happens when both nombre and direccion have high scores
        is_strong_address_match = (nombre_score > 0.6 and direccion_score > 0.6) or (nombre_overlap_score > 0.7 and direccion_overlap_score > 0.7)
        
        # Calculate final score based on what matched
        # CRITICAL: If both city AND province have decent matches, give massive boost
        if (poblacion_score > 0.35 and provincia_score > 0.35) or (direccion_score > 0.35 and (poblacion_score > 0.3 or provincia_score > 0.3)):
            # Both location fields match - this is very likely the right center
            # But if nombre also has a good match, prioritize it
            if is_strong_address_match:
                # EXACT ADDRESS MATCH - highest priority (e.g., "Peru 38" in Barcelona)
                final_score = (poblacion_score + provincia_score + direccion_score + nombre_score * 3) / 2.0
            elif nombre_score > 0.5 or direccion_score > 0.5:
                # Strong name match with location match - high priority
                final_score = (poblacion_score + provincia_score + direccion_score + nombre_score * 2) / 2.5
            else:
                # Location match without strong name match
                final_score = (poblacion_score + provincia_score + direccion_score) * 1.1
        elif is_strong_address_match:
            # Strong address match without location - still very high priority
            final_score = max(nombre_score, direccion_score) * 1.2
        elif nombre_score > 0.5 or direccion_score > 0.5:
            # Strong name match alone
            final_score = max(nombre_score, direccion_score) * 0.95
        elif poblacion_score > 0.5 or provincia_score > 0.5:
            # Strong location match
            final_score = max(poblacion_score, provincia_score) * 0.8
        else:
            # Weak matches - combine all signals
            final_score = max(
                nombre_score * 0.7,
                poblacion_score * 0.8,
                provincia_score * 0.7,
                direccion_score * 0.7,
                (poblacion_score + provincia_score + direccion_score) / 3 * 0.85
            )
        
        # Only collect matches with meaningful scores
        minimum_score = 0.35 if (filter_by_city or filter_by_province) else 0.4
        if final_score >= minimum_score:
            matches.append({
                'row': row,
                'score': final_score,
                'location_score': max(poblacion_score, provincia_score, direccion_score),
                'nombre_score': nombre_score
            })
            continue
        # fallback scoring using combined fields for partial combos
        combined_fields = [
            row['norm_nombre'],
            row['norm_poblacion'],
            row['norm_provincia'],
            row.get('norm_direccion', '')
        ]
        combined_text = " ".join([cf for cf in combined_fields if isinstance(cf, str)])
        combined_similarity = fuzzy_similarity(normalized_query, combined_text)
        if combined_similarity >= 0.82:
            matches.append({
                'row': row,
                'score': combined_similarity * 0.7,
                'location_score': max(poblacion_score, provincia_score, direccion_score, combined_similarity),
                'nombre_score': max(nombre_score, combined_similarity)
            })
    
    # Sort matches by score in descending order
    matches.sort(key=lambda x: x['score'], reverse=True)
    
    # Prioritize matches that strongly hit the requested location
    location_threshold = 0.35 if (filter_by_city or filter_by_province) else 0.4
    location_strong_matches = [m for m in matches if m['location_score'] >= location_threshold]
    if location_strong_matches:
        matches = location_strong_matches
    elif filter_by_city or filter_by_province:
        # fallback to best matches sorted even if location score slightly lower
        matches = sorted(matches, key=lambda x: (x['location_score'], x['score']), reverse=True)
    
    if not matches:
        response = "I couldn't find a center matching your description."
    elif len(matches) == 1:
        # Single match - return it directly
        best_match = matches[0]['row']
        response = f"I believe you're referring to **{best_match['nombre']}** in {best_match['poblacion']}.<br>"
        detail_lines = []
        if id_requested and not code_requested:
            detail_lines.append(f"Center ID: {best_match['id_centro']}")
        elif code_requested and not id_requested:
            detail_lines.append(f"Center Code: {best_match['codigo']}")
        else:
            detail_lines.append(f"Center ID: {best_match['id_centro']}")
            detail_lines.append(f"Center Code: {best_match['codigo']}")
        detail_lines.append(f"Location: {best_match['direccion']}")
        response += "<br>".join(detail_lines)
        if machine_info_requested:
            response += "<br>Machine details aren't available in the system yet. Please contact support if you need an exact count."
    else:
        # Multiple matches - check if top match is significantly better
        top_score = matches[0]['score']
        second_score = matches[1]['score']
        
        # If the top match is significantly better (>15% difference), return it
        if top_score - second_score > 0.15:
            best_match = matches[0]['row']
            response = f"I believe you're referring to **{best_match['nombre']}** in {best_match['poblacion']}.<br>"
            detail_lines = []
            if id_requested and not code_requested:
                detail_lines.append(f"Center ID: {best_match['id_centro']}")
                detail_lines.append(f"Center Code: {best_match['codigo']}")
            elif code_requested and not id_requested:
                detail_lines.append(f"Center Code: {best_match['codigo']}")
                detail_lines.append(f"Center ID: {best_match['id_centro']}")
            else:
                detail_lines.append(f"Center ID: {best_match['id_centro']}")
                detail_lines.append(f"Center Code: {best_match['codigo']}")
            detail_lines.append(f"Location: {best_match['direccion']}")
            response += "<br>".join(detail_lines)
            if machine_info_requested:
                response += "<br>Machine details aren't available in the system yet. Please contact support if you need an exact count."
        else:
            # Multiple similar matches - ask for clarification
            # Limit to top 10 results to avoid overwhelming the user
            max_results = 10
            response = f"I found {len(matches)} centers matching your query. "
            if len(matches) > max_results:
                response += f"Here are the top {max_results}. "
            response += "Please specify which one you're referring to:<br><br>"
            
            for i, match in enumerate(matches[:max_results], 1):
                row = match['row']
                line = f"{i}. **{row['nombre']}** – {row['provincia']}"
                
                details = []
                if id_requested and not code_requested:
                    details.append(f"ID: {row['id_centro']}")
                elif code_requested and not id_requested:
                    details.append(f"Code: {row['codigo']}")
                else:
                    details.append(f"Code: {row['codigo']}")
                    details.append(f"ID: {row['id_centro']}")
                
                line += f" ({', '.join(details)})<br>"
                response += line

    return jsonify({"response": response})

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy", "service": "lawash-tool"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000)
