import csv
import json
import os
import time
import unicodedata

from openai import OpenAI


DICTIONARY_FILE = "shiritori_dictionary.json"
CSV_FILE = "shiritori_log_v3.csv"

# 最大試行回数
MAX_GAMES = 2000


# ========================================
# OpenAI API
# ========================================

client = OpenAI()


def ask_gpt(
    prompt_text,
    max_consecutive,
    consecutive_count,
    previous_word,
    required_char,
    history
):
    history_text = ""

    for player_id, word in history:
        history_text += f"{player_id}：{word}\n"

    prompt = f"""{prompt_text}

【現在のゲーム状態】
最大連続回答回数：{max_consecutive}回
現在の連続回答回数：{consecutive_count}回目
前の単語：{previous_word}
次に必要な文字：{required_char}

【これまでの回答履歴】
{history_text}

あなたの回答：
"""

    response = client.responses.create(
        model="gpt-5.6-luna",
        input=prompt
    )

    return response.output_text.strip()


# ========================================
# かな処理
# ========================================

def normalize_kana(text):
    text = unicodedata.normalize("NFKC", text)

    result = []

    for char in text:
        code = ord(char)

        if 0x30A1 <= code <= 0x30F6:
            char = chr(code - 0x60)

        result.append(char)

    return "".join(result)


def get_next_char(reading):
    """
    読みの最後の文字から、次の要求文字を決定する。

    ・通常のカナ → そのまま
    ・「っ」 → 「つ」
    ・「ゃ」 → 「や」
    ・「ゅ」 → 「ゆ」
    ・「ょ」 → 「よ」
    ・「ー」 → 直前のカナの母音
    """

    reading = normalize_kana(reading)

    if not reading or reading == "*":
        return ""

    last_char = reading[-1]

    small_kana_map = {
        "っ": "つ",
        "ゃ": "や",
        "ゅ": "ゆ",
        "ょ": "よ"
    }

    if last_char in small_kana_map:
        return small_kana_map[last_char]

    if last_char != "ー":
        return last_char

    if len(reading) < 2:
        return ""

    previous_char = reading[-2]

    vowel_map = {
        "あ": "あ", "か": "あ", "が": "あ", "さ": "あ", "ざ": "あ",
        "た": "あ", "だ": "あ", "な": "あ", "は": "あ", "ば": "あ",
        "ぱ": "あ", "ま": "あ", "や": "あ", "ら": "あ", "わ": "あ",

        "い": "い", "き": "い", "ぎ": "い", "し": "い", "じ": "い",
        "ち": "い", "ぢ": "い", "に": "い", "ひ": "い", "び": "い",
        "ぴ": "い", "み": "い", "り": "い",

        "う": "う", "く": "う", "ぐ": "う", "す": "う", "ず": "う",
        "つ": "う", "づ": "う", "ぬ": "う", "ふ": "う", "ぶ": "う",
        "ぷ": "う", "む": "う", "ゆ": "う", "る": "う",

        "え": "え", "け": "え", "げ": "え", "せ": "え", "ぜ": "え",
        "て": "え", "で": "え", "ね": "え", "へ": "え", "べ": "え",
        "ぺ": "え", "め": "え", "れ": "え",

        "お": "お", "こ": "お", "ご": "お", "そ": "お", "ぞ": "お",
        "と": "お", "ど": "お", "の": "お", "ほ": "お", "ぼ": "お",
        "ぽ": "お", "も": "お", "よ": "お", "ろ": "お"
    }

    return vowel_map.get(previous_char, "")


# ========================================
# 辞書
# ========================================

def load_dictionary():
    """
    shiritori_dictionary.json を読み込む。
    """

    if not os.path.exists(DICTIONARY_FILE):
        print(
            f"辞書ファイルが見つかりません: "
            f"{DICTIONARY_FILE}"
        )
        return None

    with open(
        DICTIONARY_FILE,
        "r",
        encoding="utf-8"
    ) as f:
        dictionary = json.load(f)

    print(
        f"辞書読み込み完了: "
        f"{len(dictionary):,} 表記"
    )

    return dictionary


def get_word_info(dictionary, word, required_char=None):
    """
    辞書から単語情報を取得する。

    readings に複数の読みがある場合、
    required_char から始まる読みを優先する。

    戻り値:
        dictionary_ok
        reading
        readings
        pos
    """

    word = unicodedata.normalize("NFKC", word)

    entry = dictionary.get(word)

    if entry is None:
        return {
            "dictionary_ok": False,
            "reading": "",
            "readings": [],
            "pos": ""
        }

    readings = entry.get("readings", [])

    if not readings:
        single_reading = entry.get("reading", "")

        if single_reading:
            readings = [single_reading]

    normalized_readings = []

    for reading in readings:
        normalized = normalize_kana(reading)

        if normalized and normalized != "*":
            normalized_readings.append(normalized)

    normalized_readings = list(
        dict.fromkeys(normalized_readings)
    )

    selected_reading = ""

    if required_char:

        for reading in normalized_readings:

            if reading.startswith(required_char):
                selected_reading = reading
                break

    elif normalized_readings:

        selected_reading = normalized_readings[0]

    return {
        "dictionary_ok": True,
        "reading": selected_reading,
        "readings": normalized_readings,
        "pos": "名詞"
    }


# ========================================
# CSV
# ========================================

def initialize_csv():
    """
    新しいログファイルを作成する。
    """

    if not os.path.exists(CSV_FILE):

        with open(
            CSV_FILE,
            "w",
            newline="",
            encoding="utf-8-sig"
        ) as f:

            writer = csv.writer(f)

            writer.writerow([
                "ゲームID",
                "ターン",
                "プレイヤーID",
                "前の単語",
                "要求文字",
                "回答",
                "応答時間_ms",
                "語頭判定",
                "辞書判定",
                "読み",
                "判定",
                "終了理由",
                "勝者ID",
                "敗者ID",
                "プロンプトNo",
                "最大連続回答回数"
            ])

def write_log(
    game_id,
    turn,
    player_id,
    previous_word,
    required_char,
    answer,
    response_time_ms,
    head_ok,
    dictionary_ok,
    reading,
    judgment,
    end_reason,
    winner_id,
    loser_id,
    prompt_no,
    max_consecutive
):
    """
    1ターン分のログをCSVに保存する。
    """

    with open(
        CSV_FILE,
        "a",
        newline="",
        encoding="utf-8-sig"
    ) as f:

        writer = csv.writer(f)

        writer.writerow([
            game_id,
            turn,
            player_id,
            previous_word,
            required_char,
            answer,
            response_time_ms,
            "○" if head_ok else "×",
            "○" if dictionary_ok else "×",
            reading,
            "○" if judgment else "×",
            end_reason,
            winner_id,
            loser_id,
            prompt_no,
            max_consecutive
        ])


# ========================================
# ゲーム本体
# ========================================

def play_shiritori(
    dictionary,
    game_id,
    prompt_text,
    max_consecutive,
    player1_id,
    player2_id,
    prompt_no
):

    # ----------------------------------------
    # プレイヤー状態
    # ----------------------------------------

    current_player = player1_id
    other_player = player2_id

    consecutive_count = 0

    # ----------------------------------------
    # 初期単語
    # ----------------------------------------

    previous_word = "しりとり"

    initial_info = get_word_info(
        dictionary,
        previous_word
    )

    if not initial_info["dictionary_ok"]:

        print(
            "初期単語「しりとり」が"
            "辞書に存在しません。"
        )

        return False

    initial_reading = initial_info["reading"]

    if not initial_reading:

        print(
            "初期単語の読みを取得できませんでした。"
        )

        return False

    # ----------------------------------------
    # 最初の要求文字
    # ----------------------------------------

    required_char = get_next_char(
        initial_reading
    )

    if not required_char:

        print(
            "初期単語から次の要求文字を"
            "取得できませんでした。"
        )

        return False

    # ----------------------------------------
    # 使用済み単語
    # ----------------------------------------

    used_words = set()

    used_words.add(
        unicodedata.normalize(
            "NFKC",
            previous_word
        )
    )

    # ----------------------------------------
    # 回答履歴
    # ----------------------------------------

    history = []

    turn = 1

    # ----------------------------------------
    # 開始表示
    # ----------------------------------------

    print()
    print("=" * 50)
    print(f"ゲームID: {game_id}")
    print(f"最大連続回答回数: {max_consecutive}")
    print(f"プレイヤー1: {player1_id}")
    print(f"プレイヤー2: {player2_id}")
    print(f"最初の単語: {previous_word}")
    print(
        f"次は「{required_char}」"
        f"から始まる名詞"
    )
    print("=" * 50)

    # ========================================
    # ゲームループ
    # ========================================

    while True:

        # ------------------------------------
        # 連続回答回数
        # ------------------------------------

        consecutive_count += 1

        print(
            f"現在のプレイヤー: "
            f"{current_player}"
            f"（{consecutive_count}回目）"
        )

        # ------------------------------------
        # 回答入力
        # ------------------------------------

        start_time = time.perf_counter()

        if current_player.startswith("GPT"):

            answer = ask_gpt(
                prompt_text,
                max_consecutive,
                consecutive_count,
                previous_word,
                required_char,
                history
            )

            print(
                f"{current_player}の回答 > "
                f"{answer}"
            )

        else:

            answer = input(
                "回答 > "
            ).strip()

        end_time = time.perf_counter()

        response_time_ms = round(
            (end_time - start_time) * 1000
        )

        # ------------------------------------
        # 表記の正規化
        # ------------------------------------

        normalized_answer = (
            unicodedata.normalize(
                "NFKC",
                answer
            )
        )

        # ------------------------------------
        # 既出判定
        # ------------------------------------

        already_used = (
            normalized_answer in used_words
        )

        # ------------------------------------
        # 辞書判定
        # ------------------------------------

        info = get_word_info(
            dictionary,
            answer,
            required_char
        )

        dictionary_ok = info["dictionary_ok"]

        raw_reading = info["reading"]

        reading = normalize_kana(
            raw_reading
        )

        # ------------------------------------
        # 語頭判定
        # ------------------------------------
        if reading:

            answer_head = normalize_kana(
                reading
            )[0]

            head_ok = (
                answer_head == required_char
            )

        else:

            normalized_answer_kana = normalize_kana(
                normalized_answer
            )

            if normalized_answer_kana:

                answer_head = normalized_answer_kana[0]

                head_ok = (
                    answer_head == required_char
                )

            else:

                head_ok = False

        # ------------------------------------
        # 「ん」判定
        # ------------------------------------

        ends_with_n = (
            bool(reading)
            and reading[-1] == "ん"
        )

        # ------------------------------------
        # 最終判定
        # ------------------------------------

        judgment = (
            head_ok
            and dictionary_ok
            and not already_used
            and not ends_with_n
        )

        # ------------------------------------
        # 終了理由
        # ------------------------------------

        if already_used:

            end_reason = "既出単語"

        elif not dictionary_ok:

            end_reason = "辞書外"

        elif not head_ok:

            end_reason = "語頭不一致"

        elif ends_with_n:

            end_reason = "「ん」で終了"

        else:

            end_reason = ""

        # ------------------------------------
        # 勝敗
        # ------------------------------------

        if judgment:

            winner_id = ""
            loser_id = ""

        else:

            winner_id = other_player
            loser_id = current_player

        # ------------------------------------
        # 不正解なら終了
        # ------------------------------------

        if not judgment:

            write_log(
                game_id,
                turn,
                current_player,
                previous_word,
                required_char,
                answer,
                response_time_ms,
                head_ok,
                dictionary_ok,
                raw_reading,
                judgment,
                end_reason,
                winner_id,
                loser_id,
                prompt_no,
                max_consecutive
            )

            print(
                f"終了理由: {end_reason}"
            )

            print(
                f"勝者: {winner_id}"
            )

            print(
                f"敗者: {loser_id}"
            )

            return True

        # ------------------------------------
        # 正解ならログ保存
        # ------------------------------------

        write_log(
            game_id,
            turn,
            current_player,
            previous_word,
            required_char,
            answer,
            response_time_ms,
            head_ok,
            dictionary_ok,
            raw_reading,
            judgment,
            end_reason,
            winner_id,
            loser_id,
            prompt_no,
            max_consecutive
        )

        # ------------------------------------
        # 使用済みに追加
        # ------------------------------------

        used_words.add(
            normalized_answer
        )

        # ------------------------------------
        # 回答履歴に追加
        # ------------------------------------

        history.append(
            (
                current_player,
                normalized_answer
            )
        )

        # ------------------------------------
        # 次の単語へ
        # ------------------------------------

        previous_word = normalized_answer

        required_char = get_next_char(
            reading
        )

        turn += 1

        # ------------------------------------
        # 規定回数に達した場合
        # ------------------------------------

        if consecutive_count >= max_consecutive:

            print(
                f"{current_player}は規定回数（"
                f"{max_consecutive}回）に達しました。"
            )

            print(
                f"次のプレイヤー "
                f"{other_player} に交代します。"
            )

            current_player, other_player = (
                other_player,
                current_player
            )

            consecutive_count = 0

        # ------------------------------------
        # 規定回数未満なら続行確認
        # ------------------------------------

        else:

            # GPT同士の自動対戦では、
            # y/n入力を行わず自動的に継続する。
            if (
                current_player.startswith("GPT")
                and other_player.startswith("GPT")
            ):

                continue

            continue_input = input(
                f"続けて入力しますか？ y/n"
                f"（次は{consecutive_count + 1}"
                f"回目入力） > "
            ).strip().lower()

            if continue_input == "y":

                pass

            else:

                print()
                print(
                    f"{current_player}"
                    f"が入力を終了しました。"
                )

                print(
                    f"次のプレイヤー "
                    f"{other_player} に交代します。"
                )

                current_player, other_player = (
                    other_player,
                    current_player
                )

                consecutive_count = 0

        print()

        print(
            f"現在のプレイヤー: "
            f"{current_player}"
        )

        print(
            f"次は「{required_char}」"
            f"から始まる名詞"
        )

        print()


# ========================================
# 設定入力
# ========================================

def get_settings():

    # ----------------------------------------
    # プロンプトNo
    # ----------------------------------------

    while True:

        try:

            prompt_no = int(
                input(
                    "プロンプトNo > "
                )
            )

            if prompt_no >= 10:
                break

            print(
                "プロンプトNoは10以上の数字を入力してください。"
            )

        except ValueError:

            print(
                "数字を入力してください。"
            )

    # ----------------------------------------
    # プロンプト読み込み
    # ----------------------------------------

    prompt_file = f"Prompt{prompt_no}.txt"

    if not os.path.exists(prompt_file):
        print(
            f"プロンプトファイルが見つかりません: "
            f"{prompt_file}"
        )
        return None

    with open(
        prompt_file,
        "r",
        encoding="utf-8"
    ) as f:
        prompt_text = f.read().strip()

    # ----------------------------------------
    # 最大連続回答回数
    # ----------------------------------------

    while True:

        try:

            max_consecutive = int(
                input(
                    "1人が続けて回答できる最大回数 > "
                )
            )

            if max_consecutive >= 1:
                break

            print(
                "1以上の数字を入力してください。"
            )

        except ValueError:

            print(
                "数字を入力してください。"
            )

    # ----------------------------------------
    # プレイヤーID
    # ----------------------------------------

    player1_id = input(
        "プレイヤー1 ID > "
    ).strip()

    while True:

        player2_id = input(
            "プレイヤー2 ID > "
        ).strip()

        if player2_id != player1_id:
            break

        print(
            "プレイヤーIDは別々にしてください。"
        )

    # ----------------------------------------
    # 試行回数
    # ----------------------------------------

    while True:

        try:

            game_count = int(
                input(
                    "試行回数？（最大2000回） > "
                )
            )

            if 1 <= game_count <= MAX_GAMES:
                break

            print(
                f"試行回数は1～{MAX_GAMES}回"
                "で指定してください。"
            )

        except ValueError:

            print(
                "数字を入力してください。"
            )

    return (
        prompt_no,
        prompt_file,
        prompt_text,
        max_consecutive,
        player1_id,
        player2_id,
        game_count
    )


# ========================================
# メイン
# ========================================

def main():

    print()
    print("改造しりとり 自動試行")
    print("=" * 50)

    # ----------------------------------------
    # CSV初期化
    # ----------------------------------------

    initialize_csv()

    # ----------------------------------------
    # 辞書読み込み
    # ----------------------------------------

    dictionary = load_dictionary()

    if dictionary is None:
        return

    # ----------------------------------------
    # 設定入力
    # ----------------------------------------

    settings = get_settings()

    if settings is None:
        return

    (
        prompt_no,
        prompt_file,
        prompt_text,
        max_consecutive,
        player1_id,
        player2_id,
        game_count
    ) = settings

    # ----------------------------------------
    # 開始ゲームID
    # ----------------------------------------

    # 新しい実験では常にゲームID 1から開始
    game_id = 1

    print()
    print("=" * 50)
    print("実験開始")
    print(f"使用プロンプト: {prompt_file}")
    print(f"開始ゲームID: {game_id}")
    print(f"試行回数: {game_count}")
    print(f"最大連続回答回数: {max_consecutive}")
    print(f"プレイヤー1: {player1_id}")
    print(f"プレイヤー2: {player2_id}")
    print("=" * 50)
    print()

    # ----------------------------------------
    # 指定回数だけゲーム実行
    # ----------------------------------------

    completed_games = 0

    try:

        for i in range(game_count):

            current_game_id = game_id + i

            print()
            print()
            print(
                "#" * 60
            )
            print(
                f"試行 {i + 1} / {game_count}"
            )
            print(
                f"ゲームID: {current_game_id}"
            )
            print(
                "#" * 60
            )

            success = play_shiritori(
                dictionary,
                current_game_id,
                prompt_text,
                max_consecutive,
                player1_id,
                player2_id,
                prompt_no
            )

            if success:
                completed_games += 1

            print()
            print(
                f"試行 {i + 1} / {game_count} 完了"
            )

    except KeyboardInterrupt:

        print()
        print()
        print("=" * 60)
        print("Ctrl+C により実験を停止しました。")
        print(
            f"完了したゲーム数: "
            f"{completed_games}"
        )
        print(
            "それまでのログはCSVに保存されています。"
        )
        print("=" * 60)

        return

    # ----------------------------------------
    # 終了
    # ----------------------------------------

    print()
    print()
    print("=" * 60)
    print("全試行終了")
    print(
        f"完了したゲーム数: "
        f"{completed_games} / {game_count}"
    )
    print(
        f"ログファイル: {CSV_FILE}"
    )
    print("=" * 60)


# ========================================
# 実行
# ========================================

if __name__ == "__main__":
    main()
