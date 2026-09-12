import string

letters = string.ascii_lowercase

with open("dictionary.txt", "w", encoding="utf-8") as f:
    for c1 in letters:
        for c2 in letters:
            for c3 in letters:
                f.write(f"{c1}{c2}{c3}\n")

print("17,576件の単語リストを dictionary.txt に出力しました。")