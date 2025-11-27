from flask import Flask, request, jsonify
from flask_cors import CORS
import pandas as pd
import json
import os
import unicodedata
import logging
from difflib import SequenceMatcher

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
    return ''.join(c for c in unicodedata.normalize('NFD', text)
                  if unicodedata.category(c) != 'Mn').lower()

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
    
    for _, row in df.iterrows():
        # Token overlap scoring - must have at least some overlap
        # Remove stopwords from row data for better overlap calculation
        row_nombre_tokens = set([w for w in row['norm_nombre'].split() if w not in stopwords])
        row_poblacion_tokens = set([w for w in row['norm_poblacion'].split() if w not in stopwords])
        row_provincia_tokens = set([w for w in row['norm_provincia'].split() if w not in stopwords])
        
        # Fallback to original tokens if filtering removed everything (unlikely but possible)
        if not row_nombre_tokens: row_nombre_tokens = set(row['norm_nombre'].split())
        if not row_poblacion_tokens: row_poblacion_tokens = set(row['norm_poblacion'].split())
        if not row_provincia_tokens: row_provincia_tokens = set(row['norm_provincia'].split())
        
        # Check for any token overlap
        nombre_overlap = len(query_tokens & row_nombre_tokens)
        poblacion_overlap = len(query_tokens & row_poblacion_tokens)
        provincia_overlap = len(query_tokens & row_provincia_tokens)
        
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
        
        # Skip if there's no overlap or substring match at all
        if (nombre_overlap == 0 and poblacion_overlap == 0 and provincia_overlap == 0 and
            not nombre_substring_match and not poblacion_substring_match and not provincia_substring_match):
            continue
        
        # Calculate fuzzy similarity for fields with some overlap
        # Only calculate fuzzy if there is some relevance to save computation and reduce noise
        nombre_fuzzy = fuzzy_similarity(query_string, row['norm_nombre']) if (nombre_overlap > 0 or nombre_substring_match) else 0
        poblacion_fuzzy = fuzzy_similarity(query_string, row['norm_poblacion']) if (poblacion_overlap > 0 or poblacion_substring_match) else 0
        provincia_fuzzy = fuzzy_similarity(query_string, row['norm_provincia']) if (provincia_overlap > 0 or provincia_substring_match) else 0
        
        # Normalized overlap scores - use Jaccard-like ratio but favor query coverage
        # Denominator is max of query length or row length to penalize length mismatch, 
        # but we use a soft max to be lenient
        nombre_overlap_score = nombre_overlap / max(len(query_tokens), len(row_nombre_tokens)) if row_nombre_tokens else 0
        poblacion_overlap_score = poblacion_overlap / max(len(query_tokens), len(row_poblacion_tokens)) if row_poblacion_tokens else 0
        provincia_overlap_score = provincia_overlap / max(len(query_tokens), len(row_provincia_tokens)) if row_provincia_tokens else 0
        
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
        # Threshold 0.4 allows for "Sebastian Bay" (partial match) but blocks "Guadarrama" vs "Quarteira" (no match)
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
            for i, match in enumerate(matches[:5], 1):  # Show up to 5 matches
                row = match['row']
                response += f"{i}. **{row['nombre']}** - {row['direccion']}, {row['poblacion']}, {row['provincia']}<br>"
                response += f"   Center ID: {row['id_centro']}, Code: {row['codigo']}<br><br>"

    return jsonify({"response": response})

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy", "service": "lawash-tool"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000)
