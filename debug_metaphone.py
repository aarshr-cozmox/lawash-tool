import jellyfish
from word2number import w2n

print(f"Sardinia: {jellyfish.metaphone('Sardinia')}")
print(f"Sardenya: {jellyfish.metaphone('Sardenya')}")
print(f"Cali: {jellyfish.metaphone('Cali')}")
print(f"Calle: {jellyfish.metaphone('Calle')}")
print(f"two hundred: {w2n.word_to_num('two hundred')}")
