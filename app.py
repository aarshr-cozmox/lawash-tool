from flask import Flask, request, jsonify
import pandas as pd
import json
import os
import unicodedata
from difflib import SequenceMatcher

app = Flask(__name__)

# Load data
try:
    with open('centers.json', 'r') as f:
        data = json.load(f)
    df = pd.DataFrame(data['centers'])
    print("Data loaded successfully.")
except Exception as e:
    print(f"Error loading data: {e}")
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
    best_score = 0
    best_match = None
    query_string = " ".join(query_words)
    query_tokens = set(query_words)
    
    for _, row in df.iterrows():
        # Calculate fuzzy similarity for each field
        nombre_fuzzy = fuzzy_similarity(query_string, row['norm_nombre'])
        poblacion_fuzzy = fuzzy_similarity(query_string, row['norm_poblacion'])
        provincia_fuzzy = fuzzy_similarity(query_string, row['norm_provincia'])
        
        # Token overlap scoring (semantic-like boost)
        nombre_tokens = set(row['norm_nombre'].split())
        poblacion_tokens = set(row['norm_poblacion'].split())
        provincia_tokens = set(row['norm_provincia'].split())
        
        nombre_overlap = len(query_tokens & nombre_tokens) / max(len(query_tokens), 1)
        poblacion_overlap = len(query_tokens & poblacion_tokens) / max(len(query_tokens), 1)
        provincia_overlap = len(query_tokens & provincia_tokens) / max(len(query_tokens), 1)
        
        # Hybrid score: fuzzy is primary, token overlap provides boost
        nombre_score = (nombre_fuzzy * 0.8) + (nombre_overlap * 0.2)
        poblacion_score = (poblacion_fuzzy * 0.8) + (poblacion_overlap * 0.2)
        provincia_score = (provincia_fuzzy * 0.8) + (provincia_overlap * 0.2)
        
        # CRITICAL: If both city AND province have decent matches, give massive boost
        # This handles queries like "San Sebastian at Guipuzcoa"
        if poblacion_score > 0.3 and provincia_score > 0.3:
            # Both location fields match - this is very likely the right center
            combined_boost = (poblacion_score + provincia_score) * 1.5
            final_score = combined_boost
        else:
            # Standard scoring when only one field matches
            final_score = max(
                nombre_score * 0.4,
                poblacion_score * 0.7,
                provincia_score * 0.6,
                (poblacion_score + provincia_score) / 2 * 0.75
            )
        
        if final_score > best_score:
            best_score = final_score
            best_match = row
    
    # Require at least 35% similarity for better recall with typos
    if best_match is not None and best_score >= 0.35:
        response = f"I believe you're referring to **{best_match['nombre']}** in {best_match['poblacion']}.<br>"
        response += f"Center ID: {best_match['id_centro']}<br>"
        response += f"Code: {best_match['codigo']}<br>"
        response += f"Location: {best_match['direccion']}"
    else:
        response = "I couldn't find a center matching your description."

    return jsonify({"response": response})

if __name__ == '__main__':
    app.run(debug=True, port=3000)
