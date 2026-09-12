import csv
import json
import math
import os
import time
import unicodedata
import string

from openai import OpenAI


DICTIONARY_FILE = "dictionary.txt"
CSV_FILE = "shiritori_log_v2.csv"

# 最大試行回数
MAX_GAMES = 2000


# ========================================
# OpenAI API
# ========================================

client = OpenAI()


def build_history_text(history):
    """
    回答履歴をプロンプト用の文字列に変換する。
    """

    history_text = ""

    for player_id, word in history:
        history_text += f"{player_id}：{word}\n"

    return history_text


def ask_gpt(
    prompt_text,
    max_consecutive,
    consecutive_count,
    previous_word,
    required_char,
    history,
    banned_ending
):
    """
    GPTに次の単語を回答させる。

    戻り値:
        GPTの回答文字列
    """

    history_text = build_history_text(history)

    prompt = f"""{prompt_text}

【現在のゲーム状態】
禁止語尾：{banned_ending}
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


def ask_gpt_continue(
    prompt_text,
    max_consecutive,
    consecutive_count,
    previous_word,
    required_char,
    history,
    banned_ending
):
    """
    GPTに手番を続けるか判断させる。

    戻り値:
        "y" または "n"

    GPTの出力が完全一致で "y" の場合だけ
    続行と判定する。
    """

    history_text = build_history_text(history)

    prompt = f"""{prompt_text}

【現在のゲーム状態】
禁止語尾：{banned_ending}
最大連続回答回数：{max_consecutive}回
現在の連続回答回数：{consecutive_count}回目
前の単語：{previous_word}
次に必要な文字：{required_char}

【これまでの回答履歴】
{history_text}

【重要】
現在は単語を回答する場面ではありません。
続けて自分が回答するか、相手に手番を渡すかを判断してください。

続けて自分が回答する場合は y、
相手に手番を渡す場合は n
と回答してください。

y または n の1文字だけを回答してください。

あなたの判断：
"""

    response = client.responses.create(
        model="gpt-5.6-luna",
        input=prompt
    )

    raw_result = response.output_text.strip()

    print(
        f"続行判断API生出力: [{raw_result}]"
    )

    result = raw_result.lower()

    # 完全一致で y の場合だけ続行。
    # それ以外はすべて n とする。
    if result == "y":
        return "y"

    return "n"


def decide_continue(
    prompt_text,
    max_consecutive,
    consecutive_count,
    previous_word,
    required_char,
    history,
    current_player,
    other_player,
    banned_ending
):
    """
    正解した単語の後に、次の行動を決定する。

    戻り値:
        "continue"  → 同じプレイヤーが続行
        "switch"    → 相手へ交代

    この関数によって、
    「単語回答後には必ず続行判断を行う」
    というゲーム上の状態遷移を一箇所に集約する。
    """

    # ------------------------------------
    # 最大回数に達した場合
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

        return "switch"

    # ------------------------------------
    # GPT同士の自動対戦
    # ------------------------------------

    if (
        current_player.startswith("GPT")
        and other_player.startswith("GPT")
    ):

        print(
            f"{current_player}に"
            f"続行判断を要求します。"
        )

        continue_input = ask_gpt_continue(
            prompt_text,
            max_consecutive,
            consecutive_count,
            previous_word,
            required_char,
            history,
            banned_ending
        )

        print(
            f"{current_player}の続行判断 > "
            f"{continue_input}"
        )

        if continue_input == "y":

            print(
                f"{current_player}は"
                f"続行します。"
            )

            return "continue"

        print(
            f"{current_player}は"
            f"手番を終了します。"
        )

        return "switch"

    # ------------------------------------
    # 手動入力
    # ------------------------------------

    continue_input = input(
        f"続けて入力しますか？ y/n"
        f"（次は{consecutive_count + 1}"
        f"回目入力） > "
    ).strip().lower()

    if continue_input == "y":

        return "continue"

    print()
    print(
        f"{current_player}"
        f"が入力を終了しました。"
    )

    print(
        f"次のプレイヤー "
        f"{other_player} に交代します。"
    )

    return "switch"


# ========================================
# 人工語彙処理
# ========================================

def normalize_word(text):
    """
    人工語彙用の文字列正規化。
    NFKC正規化のみ行う。
    """
    return unicodedata.normalize("NFKC", text)


def get_score(word):
    """
    人工語の得点を計算する。

    a=1, b=2, ..., z=26 とし、
    3文字の数値合計の平方根を切り上げる。
    """
    word = normalize_word(word).lower()
    total = sum(
        ord(char) - ord("a") + 1
        for char in word
    )
    return math.ceil(math.sqrt(total))


def get_next_char(word):
    """
    単語の最後の文字を次の要求文字とする。
    """
    word = normalize_word(word)

    if not word:
        return ""

    return word[-1]


# ========================================
# 人工辞書
# ========================================

def load_dictionary():
    """
    dictionary.txt を読み込む。
    1行につき1語。
    """

    if not os.path.exists(DICTIONARY_FILE):
        print(
            f"辞書ファイルが見つかりません: "
            f"{DICTIONARY_FILE}"
        )
        return None

    dictionary = set()

    with open(
        DICTIONARY_FILE,
        "r",
        encoding="utf-8"
    ) as f:

        for line in f:
            word = line.strip()

            if word:
                dictionary.add(
                    normalize_word(word)
                )

    print(
        f"人工辞書読み込み完了: "
        f"{len(dictionary):,} 語"
    )

    return dictionary


def get_word_info(
    dictionary,
    word,
    required_char=None
):
    """
    人工辞書から単語情報を取得する。
    """

    word = normalize_word(word)

    if word not in dictionary:
        return {
            "dictionary_ok": False,
            "reading": "",
            "readings": [],
            "pos": ""
        }

    return {
        "dictionary_ok": True,
        "reading": word,
        "readings": [word],
        "pos": "人工語"
    }


# ========================================
# CSV
# ========================================

def initialize_csv():
    """
    新しいログファイルが存在しない場合、
    ヘッダーを作成する。
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
                "最大連続回答回数",
                "禁止語尾",
                "得点",
                "累計得点"
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
    max_consecutive,
    banned_ending,
    score,
    total_score
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
            max_consecutive,
            banned_ending,
            score,
            total_score
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
    prompt_no,
    banned_ending
):
    """
    1ゲームを実行する。

    ゲームの基本構造:

        1. 単語回答
        2. 外部判定
        3. 正解ならゲーム状態更新
        4. 最大回数なら強制交代
        5. それ以外は必ず続行判断
        6. yなら同じプレイヤー
        7. nなら相手へ交代
    """

    # ----------------------------------------
    # プレイヤー状態
    # ----------------------------------------

    current_player = player1_id
    other_player = player2_id

    consecutive_count = 0

    # ----------------------------------------
    # プレイヤー別得点
    # ----------------------------------------
    player_scores = {
        player1_id: 0,
        player2_id: 0
    }

    # ----------------------------------------
    # 初期状態
    # ----------------------------------------

    # 人工語彙版では初期単語を使用せず、
    # 最初から「a」で始まる語を要求する。
    previous_word = ""
    required_char = "a"

    # ----------------------------------------
    # 使用済み単語
    # ----------------------------------------

    used_words = set()

    # ----------------------------------------
    # 回答履歴
    # ----------------------------------------

    history = []

    # ----------------------------------------
    # ターン番号
    # ----------------------------------------

    turn = 1

    # ----------------------------------------
    # 開始表示
    # ----------------------------------------

    print()
    print("=" * 50)

    print(
        f"ゲームID: {game_id}"
    )

    print(
        f"最大連続回答回数: "
        f"{max_consecutive}"
    )

    print(
        f"プレイヤー1: "
        f"{player1_id}"
    )

    print(
        f"プレイヤー2: "
        f"{player2_id}"
    )

    print(
        f"禁止語尾: "
        f"{banned_ending}"
    )

    print(
        f"最初は「{required_char}」"
        f"から始まる人工語"
    )

    print("=" * 50)

    # ========================================
    # ゲームループ
    # ========================================

    while True:

        # ------------------------------------
        # 連続回答回数を1増やす
        # ------------------------------------

        consecutive_count += 1

        print(
            f"現在のプレイヤー: "
            f"{current_player}"
            f"（{consecutive_count}回目）"
        )

        # ------------------------------------
        # 単語回答
        # ------------------------------------

        start_time = time.perf_counter()

        if current_player.startswith("GPT"):

            answer = ask_gpt(
                prompt_text,
                max_consecutive,
                consecutive_count,
                previous_word,
                required_char,
                history,
                banned_ending
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

        dictionary_ok = (
            info["dictionary_ok"]
        )

        reading = info["reading"]

        # ------------------------------------
        # 語頭判定
        # ------------------------------------

        normalized_reading = normalize_word(reading)

        if normalized_reading:

            answer_head = normalized_reading[0]

            head_ok = (
                answer_head == required_char
            )

        else:

            head_ok = False

        # ------------------------------------
        # 禁止語尾判定
        # ------------------------------------

        ends_with_banned = (
            bool(reading)
            and reading[-1] == banned_ending
        )

        # ------------------------------------
        # 最終判定
        # ------------------------------------

        judgment = (
            head_ok
            and dictionary_ok
            and not already_used
            and not ends_with_banned
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

        elif ends_with_banned:

            end_reason = f"禁止語尾「{banned_ending}」"

        else:

            end_reason = ""

        # ------------------------------------
        # 得点
        # ------------------------------------

        if judgment:
            score = get_score(reading)
            player_scores[current_player] += score
        else:
            score = 0

        total_score = player_scores[current_player]

        # ------------------------------------
        # 勝敗
        # ------------------------------------

        if judgment:

            winner_id = ""
            loser_id = ""

        else:

            winner_id = other_player
            loser_id = current_player

        # ====================================
        # 不正解ならゲーム終了
        # ====================================

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
                reading,
                judgment,
                end_reason,
                winner_id,
                loser_id,
                prompt_no,
                max_consecutive,
                banned_ending,
                score,
                total_score
            )

            print(
                f"終了理由: "
                f"{end_reason}"
            )

            print(
                f"勝者: "
                f"{winner_id}"
            )

            print(
                f"敗者: "
                f"{loser_id}"
            )

            print(
                f"得点: 0点 / "
                f"{current_player}累計: {total_score}点"
            )

            return True

        # ====================================
        # 正解ならログ保存
        # ====================================

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
            reading,
            judgment,
            end_reason,
            winner_id,
            loser_id,
            prompt_no,
            max_consecutive,
            banned_ending,
            score,
            total_score
        )

        print(
            f"得点: {score}点 / "
            f"{current_player}累計: {total_score}点"
        )

        # ------------------------------------
        # 使用済み単語に追加
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
        # ゲーム状態を更新
        # ------------------------------------

        previous_word = normalized_answer

        required_char = get_next_char(
            reading
        )

        turn += 1

        # ====================================
        # 正解後の次の行動を決定
        # ====================================

        decision = decide_continue(
            prompt_text,
            max_consecutive,
            consecutive_count,
            previous_word,
            required_char,
            history,
            current_player,
            other_player,
            banned_ending
        )

        # ------------------------------------
        # 続行
        # ------------------------------------

        if decision == "continue":

            # 同じプレイヤーのまま。
            # consecutive_countも維持する。
            print()

            print(
                f"現在のプレイヤー: "
                f"{current_player}"
            )

            print(
                f"次は「{required_char}」"
                f"から始まる人工語"
            )

            print()

            continue

        # ====================================
        # 相手へ交代
        # ====================================

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
            f"から始まる人工語"
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
                "プロンプトNoは10以上の数字を"
                "入力してください。"
            )

        except ValueError:

            print(
                "数字を入力してください。"
            )

    # ----------------------------------------
    # プロンプト読み込み
    # ----------------------------------------

    prompt_file = (
        f"Prompt{prompt_no}.txt"
    )

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
    # 禁止語尾
    # ----------------------------------------

    while True:

        banned_ending = input(
            "禁止語尾は？（a～zの1文字） > "
        ).strip().lower()

        if (
            len(banned_ending) == 1
            and banned_ending in string.ascii_lowercase
        ):
            break

        print(
            "禁止語尾はa～zの1文字で指定してください。"
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
        banned_ending,
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
        banned_ending,
        player1_id,
        player2_id,
        game_count
    ) = settings

    # ----------------------------------------
    # 開始ゲームID
    # ----------------------------------------

    game_id = 1

    print()
    print("=" * 50)

    print(
        "実験開始"
    )

    print(
        f"使用プロンプト: "
        f"{prompt_file}"
    )

    print(
        f"開始ゲームID: "
        f"{game_id}"
    )

    print(
        f"試行回数: "
        f"{game_count}"
    )

    print(
        f"最大連続回答回数: "
        f"{max_consecutive}"
    )

    print(
        f"禁止語尾: "
        f"{banned_ending}"
    )

    print(
        f"プレイヤー1: "
        f"{player1_id}"
    )

    print(
        f"プレイヤー2: "
        f"{player2_id}"
    )

    print("=" * 50)
    print()

    # ----------------------------------------
    # 指定回数だけゲーム実行
    # ----------------------------------------

    completed_games = 0

    try:

        for i in range(game_count):

            current_game_id = (
                game_id + i
            )

            print()
            print()
            print(
                "#" * 60
            )

            print(
                f"試行 {i + 1} / "
                f"{game_count}"
            )

            print(
                f"ゲームID: "
                f"{current_game_id}"
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
                prompt_no,
                banned_ending
            )

            if success:
                completed_games += 1

            print()

            print(
                f"試行 {i + 1} / "
                f"{game_count} 完了"
            )

    except KeyboardInterrupt:

        print()
        print()
        print(
            "=" * 60
        )

        print(
            "Ctrl+Cにより実験を停止しました。"
        )

        print(
            f"完了したゲーム数: "
            f"{completed_games}"
        )

        print(
            "それまでのログはCSVに保存されています。"
        )

        print(
            "=" * 60
        )

        return

    # ----------------------------------------
    # 終了
    # ----------------------------------------

    print()
    print()

    print(
        "=" * 60
    )

    print(
        "全試行終了"
    )

    print(
        f"完了したゲーム数: "
        f"{completed_games} / "
        f"{game_count}"
    )

    print(
        f"ログファイル: "
        f"{CSV_FILE}"
    )

    print(
        "=" * 60
    )


# ========================================
# 実行
# ========================================

if __name__ == "__main__":
    main()