import random
from english_words import get_english_words_set

j = []
k = []
web2lowerset = get_english_words_set(["web2"], lower=True)

for word in web2lowerset:
    if word.startswith("j"):
        j.append(word)
    elif word.startswith("k"):
        k.append(word)

j = random.choice(j)
k = random.choice(k)
print(j, k)
