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

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Load data
try:
    with open('centers.json', 'r') as f:
        data = json.load(f)
    df = pd.DataFrame(data['centers'])
    logger.info("Data loaded successfully. %d centers found.", len(df))
except Exception as e:
    logger.error(f"Error loading data: {e}")
    df = pd.DataFrame()


def normalize_text(text):
    if not isinstance(text, str):
        return ""
    
    # Normalize unicode characters
    text = ''.join(c for c in unicodedata.normalize('NFD', text)
                  if unicodedata.category(c) != 'Mn').lower()
    
    # Convert number words to digits (e.g., "two hundred" -> "200")
    try:
        # Extract potential number words sequences
        # This is a simple approach; for complex sentences it might need more care
        # but w2n.word_to_num is robust enough for "two hundred"
        words = text.split()
        new_words = []
        i = 0
        while i < len(words):
            # Try to convert chunks of words
            chunk_converted = False
            for j in range(len(words), i, -1):
                chunk = " ".join(words[i:j])
                try:
                    num = w2n.word_to_num(chunk)
                    new_words.append(str(num))
                    i = j
                    chunk_converted = True
                    break
                except ValueError:
                    continue
            
            if not chunk_converted:
                new_words.append(words[i])
                i += 1
        text = " ".join(new_words)
    except Exception:
        pass  # If conversion fails, keep original text
        
    return text

def fuzzy_similarity(str1, str2):
    """Calculate similarity ratio between two strings (0.0 to 1.0)"""
    return SequenceMatcher(None, str1, str2).ratio()

@app.route('/api/chat', methods=['POST'])
def chat():
    user_message = request.json.get('message', '').lower()
    
    if df.empty:
        return jsonify({"response": "Sorry, I couldn't get the data."})

    # Normalize query
    normalized_query = normalize_text(user_message)
    
    # Remove stopwords
    stopwords = [
        "what", "is", "the", "center", "centre", "id", "and", "code", "for", "my", "located", "at", "in", 
        "show", "me", "tell", "give", "result", "query", "details", "poblacion", "province", "city",
        "de", "la", "el", "los", "las", "en", "y", "del", "a"
    ]
    query_words = [w for w in normalized_query.split() if w not in stopwords]
    
    if not query_words:
        return jsonify({"response": "Please specify a center name, city, or province."})

    # Pre-calculate normalized columns if not already done
    if 'norm_nombre' not in df.columns:
        df['norm_nombre'] = df['nombre'].apply(normalize_text)
        df['norm_poblacion'] = df['poblacion'].apply(normalize_text)
        df['norm_provincia'] = df['provincia'].apply(normalize_text)

    # Fuzzy matching logic with hybrid scoring
    matches = []  # Store all potential matches with their scores
    query_string = " ".join(query_words)
    query_tokens = set(query_words)
    # Additional normalized versions of tokens for code/id detection
    clean_token = lambda t: re.sub(r'[^a-z0-9]', '', t)
    query_tokens_clean = {clean_token(t) for t in query_tokens if clean_token(t)}
    normalized_query_compact = clean_token(normalized_query)
    
    # Pre-calculate phonetic codes for query tokens
    query_phonetics = {qt: jellyfish.metaphone(qt) for qt in query_tokens if len(qt) > 2}
    
    for _, row in df.iterrows():
        row_id = str(row['id_centro']).lower()
        row_code = str(row['codigo']).lower()
        row_id_clean = clean_token(row_id)
        row_code_clean = clean_token(row_code)
        # 1. Direct Code/ID Match (Highest Priority)
        # Check if any query token exactly matches id_centro or codigo (case-insensitive)
        if (row_id in query_tokens or
            row_code in query_tokens or
            row_id_clean in query_tokens_clean or
            row_code_clean in query_tokens_clean or
            (row_code_clean and row_code_clean in normalized_query_compact)):
            matches.append({
                'row': row,
                'score': 1.0  # Perfect match
            })
            continue
            
        # Token overlap scoring - must have at least some overlap
        # Remove stopwords from row data for better overlap calculation
        row_nombre_tokens = set([w for w in row['norm_nombre'].split() if w not in stopwords])
        row_poblacion_tokens = set([w for w in row['norm_poblacion'].split() if w not in stopwords])
        row_provincia_tokens = set([w for w in row['norm_provincia'].split() if w not in stopwords])
        
        # Fallback to original tokens if filtering removed everything
        if not row_nombre_tokens: row_nombre_tokens = set(row['norm_nombre'].split())
        if not row_poblacion_tokens: row_poblacion_tokens = set(row['norm_poblacion'].split())
        if not row_provincia_tokens: row_provincia_tokens = set(row['norm_provincia'].split())
        
        # Check for any token overlap
        nombre_overlap = len(query_tokens & row_nombre_tokens)
        poblacion_overlap = len(query_tokens & row_poblacion_tokens)
        provincia_overlap = len(query_tokens & row_provincia_tokens)
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
        
        # Phonetic matching
        # Check if query phonetics match row phonetics
        row_nombre_phonetics = {w: jellyfish.metaphone(w) for w in row_nombre_tokens if len(w) > 2}
        row_poblacion_phonetics = {w: jellyfish.metaphone(w) for w in row_poblacion_tokens if len(w) > 2}
        row_provincia_phonetics = {w: jellyfish.metaphone(w) for w in row_provincia_tokens if len(w) > 2}
        
        nombre_phonetic_match = any(qp in row_nombre_phonetics.values() for qp in query_phonetics.values())
        poblacion_phonetic_match = any(qp in row_poblacion_phonetics.values() for qp in query_phonetics.values())
        provincia_phonetic_match = any(qp in row_provincia_phonetics.values() for qp in query_phonetics.values())
        
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
        
        # Pre-calculate fuzzy scores for guard and reuse later
        nombre_fuzzy_full = fuzzy_similarity(query_string, row['norm_nombre'])
        poblacion_fuzzy_full = fuzzy_similarity(query_string, row['norm_poblacion'])
        provincia_fuzzy_full = fuzzy_similarity(query_string, row['norm_provincia'])
        fuzzy_override_match = max(nombre_fuzzy_full, poblacion_fuzzy_full, provincia_fuzzy_full) >= 0.7
        
        # Skip if there's no overlap, phonetic match, substring match, token fuzzy, or strong fuzzy match
        if (not fuzzy_override_match and
            nombre_overlap == 0 and poblacion_overlap == 0 and provincia_overlap == 0 and
            not nombre_phonetic_match and not poblacion_phonetic_match and not provincia_phonetic_match and
            not nombre_substring_match and not poblacion_substring_match and not provincia_substring_match and
            not nombre_token_fuzzy and not poblacion_token_fuzzy and not provincia_token_fuzzy):
            continue
        
        # Calculate fuzzy similarity for fields with some overlap
        # Only calculate fuzzy if there is some relevance to save computation and reduce noise
        nombre_fuzzy = nombre_fuzzy_full if (nombre_overlap > 0 or nombre_phonetic_match or nombre_substring_match or fuzzy_override_match) else 0
        poblacion_fuzzy = poblacion_fuzzy_full if (poblacion_overlap > 0 or poblacion_phonetic_match or poblacion_substring_match or fuzzy_override_match) else 0
        provincia_fuzzy = provincia_fuzzy_full if (provincia_overlap > 0 or provincia_phonetic_match or provincia_substring_match or fuzzy_override_match) else 0
        
        # Normalized overlap scores - use Jaccard-like ratio but favor query coverage
        nombre_overlap_score = nombre_overlap / max(len(query_tokens), len(row_nombre_tokens)) if row_nombre_tokens else 0
        poblacion_overlap_score = poblacion_overlap / max(len(query_tokens), len(row_poblacion_tokens)) if row_poblacion_tokens else 0
        provincia_overlap_score = provincia_overlap / max(len(query_tokens), len(row_provincia_tokens)) if row_provincia_tokens else 0
        
        # Boost for phonetic or token-level fuzzy matches
        if nombre_phonetic_match or nombre_token_fuzzy: nombre_overlap_score = max(nombre_overlap_score, 0.6)
        if poblacion_phonetic_match or poblacion_token_fuzzy: poblacion_overlap_score = max(poblacion_overlap_score, 0.6)
        if provincia_phonetic_match or provincia_token_fuzzy: provincia_overlap_score = max(provincia_overlap_score, 0.6)

        # Hybrid score: combine fuzzy and overlap, with overlap being more important
        nombre_score = (nombre_fuzzy * 0.3) + (nombre_overlap_score * 0.7)
        poblacion_score = (poblacion_fuzzy * 0.3) + (poblacion_overlap_score * 0.7)
        provincia_score = (provincia_fuzzy * 0.3) + (provincia_overlap_score * 0.7)
        
        # Calculate final score based on what matched
        # CRITICAL: If both city AND province have decent matches, give massive boost
        if poblacion_score > 0.35 and provincia_score > 0.35:
            # Both location fields match - this is very likely the right center
            # But if nombre also has a good match, prioritize it
            if nombre_score > 0.5:
                # Strong name match with location match - highest priority
                final_score = (poblacion_score + provincia_score + nombre_score * 2) / 2
            else:
                # Location match without strong name match
                final_score = (poblacion_score + provincia_score) * 1.2
        elif nombre_score > 0.5:
            # Strong name match alone
            final_score = nombre_score * 0.9
        elif poblacion_score > 0.5 or provincia_score > 0.5:
            # Strong location match
            final_score = max(poblacion_score, provincia_score) * 0.8
        else:
            # Weak matches - combine all signals
            final_score = max(
                nombre_score * 0.7,
                poblacion_score * 0.8,
                provincia_score * 0.7,
                (poblacion_score + provincia_score) / 2 * 0.85
            )
        
        # Only collect matches with meaningful scores
        if final_score >= 0.4:
            matches.append({
                'row': row,
                'score': final_score
            })
    
    # Sort matches by score in descending order
    matches.sort(key=lambda x: x['score'], reverse=True)
    
    if not matches:
        response = "I couldn't find a center matching your description."
    elif len(matches) == 1:
        # Single match - return it directly
        best_match = matches[0]['row']
        response = f"I believe you're referring to **{best_match['nombre']}** in {best_match['poblacion']}.<br>"
        response += f"Center ID: {best_match['id_centro']}<br>"
        response += f"Code: {best_match['codigo']}<br>"
        response += f"Location: {best_match['direccion']}"
    else:
        # Multiple matches - check if top match is significantly better
        top_score = matches[0]['score']
        second_score = matches[1]['score']
        
        # If the top match is significantly better (>15% difference), return it
        if top_score - second_score > 0.15:
            best_match = matches[0]['row']
            response = f"I believe you're referring to **{best_match['nombre']}** in {best_match['poblacion']}.<br>"
            response += f"Center ID: {best_match['id_centro']}<br>"
            response += f"Code: {best_match['codigo']}<br>"
            response += f"Location: {best_match['direccion']}"
        else:
            # Multiple similar matches - ask for clarification
            response = "I found multiple centers matching your query. Please specify which one you're referring to:<br><br>"
            for i, match in enumerate(matches, 1):
                row = match['row']
                response += f"{i}. **{row['nombre']}** – {row['provincia']} (Code: {row['codigo']})<br>"

    return jsonify({"response": response})

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy", "service": "lawash-tool"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000)
