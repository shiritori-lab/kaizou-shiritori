import itertools
import string


# ==========================================
# 入力
# ==========================================

# 使用するアルファベットの終了文字
# 例：e → a～e
#     j → a～j
#     z → a～z
end_letter = input(
    "使用するアルファベットの終了文字を入力してください（a～z） > "
).lower()

# 文字列の長さ
# 例：6 → 6文字の語だけを生成
word_length = int(input(
    "文字列の長さを入力してください > "
))


# ==========================================
# 入力チェック
# ==========================================

if end_letter not in string.ascii_lowercase:
    print("エラー：終了文字はa～zで指定してください。")
    exit()

if word_length < 1:
    print("エラー：文字列の長さは1以上で指定してください。")
    exit()


# ==========================================
# 使用する文字
# ==========================================

# a～指定した終了文字まで
letters = string.ascii_lowercase[
    :ord(end_letter) - ord("a") + 1
]


# ==========================================
# 出力ファイル名
# ==========================================

output_file = (
    f"dictionary_a-{end_letter}_{word_length}letters.txt"
)


# ==========================================
# 辞書生成
# ==========================================

count = 0

with open(output_file, "w", encoding="utf-8") as f:

    # a～指定文字を、指定した文字数だけ
    # すべての組み合わせで生成
    for chars in itertools.product(
        letters,
        repeat=word_length
    ):
        word = "".join(chars)
        f.write(word + "\n")
        count += 1


# ==========================================
# 結果表示
# ==========================================

print()
print("辞書生成完了")
print(f"使用文字：{letters}")
print(f"文字数：{word_length}")
print(f"生成語数：{count:,}")
print(f"出力ファイル：{output_file}")