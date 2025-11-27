import requests
import json

BASE_URL = 'http://localhost:3000/api/chat'

def test_query(query, description):
    print(f"\nTesting: {description}")
    print(f"Query: '{query}'")
    print("-" * 50)
    try:
        response = requests.post(
            BASE_URL,
            json={'message': query}
        )
        result = response.json()
        print(f"Response: {result['response']}")
    except Exception as e:
        print(f"Error: {e}")

# Test Case 1: Phonetic + Number Word mismatch
# "Cali d Sardinia two hundred" -> "Sardenya 200"
test_query(
    "what is the center id of my center at Cali d Sardinia two hundred", 
    "Phonetic 'Cali d Sardinia' + Number word 'two hundred'"
)

# Test Case 2: Direct Code Search
# "ES0263" -> "Av. los Pescadores 6"
test_query(
    "show me center code ES0263",
    "Direct Code Search 'ES0263'"
)

# Test Case 3: "Santa Cruz, the Tenerefaith" -> Phonetic city match
test_query(
    "Santa Cruz, the Tenerefaith",
    "Phonetic City Match 'Tenerefaith'"
)
