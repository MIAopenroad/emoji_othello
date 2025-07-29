import os
import re
import time
from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_sdk.errors import SlackApiError
from othello_game import OthelloGame

load_dotenv()

# --- 環境変数からトークンを読み込む ---
# ステップ1で取得したトークンを設定
# 例: export SLACK_APP_TOKEN='xapp-...'
# 例: export SLACK_BOT_TOKEN='xoxb-...'
app = App(token=os.environ.get("SLACK_BOT_TOKEN"))

# ゲームインスタンスをチャンネルIDごとに保存
games = {}

# --- ヘルパー関数 ---
def safe_say(say_func, message, channel_id):
    """安全にメッセージを送信する関数"""
    try:
        return say_func(message)
    except SlackApiError as e:
        if e.response["error"] == "channel_not_found":
            print(f"エラー: チャンネル {channel_id} が見つかりません。ボットがチャンネルに招待されているか確認してください。")
        elif e.response["error"] == "not_in_channel":
            print(f"エラー: ボットがチャンネル {channel_id} に参加していません。")
            print("解決方法:")
            print("1. チャンネルで `/invite @ボット名` を入力")
            print("2. または、チャンネル設定から「Integrations」→「Add apps」でボットを追加")
        else:
            print(f"Slack API エラー: {e.response['error']}")
        return None
    except Exception as e:
        print(f"予期しないエラー: {e}")
        return None

def format_board(game):
    """盤面をSlackメッセージ用にフォーマットする"""
    board_str = "  A B C D E F\n"
    legal_moves = game.get_legal_moves(game.current_player)

    for y in range(game.size):
        board_str += f"{y+1} "
        for x in range(game.size):
            cell = game.board[y][x]
            if cell == 1:
                board_str += "⚫️"
            elif cell == -1:
                board_str += "⚪️"
            else:
                if (x, y) in legal_moves and game.current_player == 1:
                    board_str += "🔵" # ユーザーが置ける場所
                else:
                    board_str += "🟩"
        board_str += "\n"
    return f"```{board_str}```"

def coord_to_xy(coord_str):
    """ "A1"のような文字列を(x, y)座標に変換 """
    match = re.match(r"^([A-F])([1-6])$", coord_str.upper())
    if not match:
        return None, None
    col, row = match.groups()
    x = ord(col) - ord('A')
    y = int(row) - 1
    return x, y

def xy_to_coord(x, y):
    """ (x, y)座標を"A1"のような文字列に変換 """
    return f"{chr(ord('A') + x)}{y + 1}"

# --- Slackコマンドハンドラ ---
@app.command("/othello-start")
def handle_start_game(ack, say, command):
    ack()
    channel_id = command["channel_id"]
    
    if channel_id in games:
        safe_say(say, "このチャンネルでは既にゲームが進行中です。終了するには `/othello-end` と入力してください。", channel_id)
        return

    game = OthelloGame()
    games[channel_id] = game

    board_text = format_board(game)
    safe_say(say, f"6x6 オセロを開始します！ ⚫️ (あなた) のターンです。\n`/othello-put [A-F][1-6]` で石を置いてください。\n{board_text}", channel_id)

@app.command("/othello-put")
def handle_put_disc(ack, say, command):
    ack()
    channel_id = command["channel_id"]
    
    if channel_id not in games:
        safe_say(say, "ゲームが開始されていません。`/othello-start` で開始してください。", channel_id)
        return

    game = games[channel_id]
    if game.current_player != 1:
        safe_say(say, "CPUのターンです。しばらくお待ちください。", channel_id)
        return

    coord_str = command.get("text", "").strip()
    x, y = coord_to_xy(coord_str)

    if x is None:
        safe_say(say, f"入力形式が正しくありません。`A1` のように入力してください。", channel_id)
        return

    if not game.get_flippable_discs(x, y, 1):
        safe_say(say, f"{coord_str} には石を置けません。青いマス(🔵)に置いてください。", channel_id)
        return

    # ユーザーのターン
    game.make_move(x, y, 1)
    safe_say(say, f"⚫️ が {coord_str.upper()} に置きました。", channel_id)

    # ゲーム終了チェック
    if game.is_game_over():
        end_game(channel_id, say)
        return

    # 盤面更新
    board_text = format_board(game)
    cpu_turn_message = safe_say(say, f"⚪️ (CPU) のターンです...\n{board_text}", channel_id)
    
    if cpu_turn_message is None:
        return  # エラーが発生した場合は処理を停止
    
    time.sleep(1.5) # CPUが考えているように見せる

    # CPUのターン
    if game.current_player == -1:
        cpu_move_pos = game.cpu_move()
        if cpu_move_pos:
            cpu_coord_str = xy_to_coord(cpu_move_pos[0], cpu_move_pos[1])
            try:
                app.client.chat_update(
                    channel=channel_id,
                    ts=cpu_turn_message['ts'],
                    text=f"⚪️ (CPU) が {cpu_coord_str} に置きました。⚫️ (あなた) のターンです。\n{format_board(game)}"
                )
            except SlackApiError as e:
                print(f"メッセージ更新エラー: {e.response['error']}")
        else: # CPUがパスする場合
            game.current_player *= -1 # ターンを戻す
            try:
                app.client.chat_update(
                    channel=channel_id,
                    ts=cpu_turn_message['ts'],
                    text=f"⚪️ (CPU) はパスしました。続けて ⚫️ (あなた) のターンです。\n{format_board(game)}"
                )
            except SlackApiError as e:
                print(f"メッセージ更新エラー: {e.response['error']}")
    
    # 再度、ユーザーが置けるかチェック
    if not game.get_legal_moves(1):
        # ユーザーもパスならゲーム終了
        if game.is_game_over():
            end_game(channel_id, say)
        else:
             safe_say(say, f"あなたは置ける場所がありません。パスします。", channel_id)
             # 再度CPUのターンを実行する必要があるが、今回は簡易的に省略

@app.command("/othello-end")
def handle_end_game(ack, say, command):
    ack()
    channel_id = command["channel_id"]
    if channel_id in games:
        del games[channel_id]
        safe_say(say, "現在のゲームを強制終了しました。", channel_id)
    else:
        safe_say(say, "進行中のゲームはありません。", channel_id)

def end_game(channel_id, say):
    """ゲーム終了時の処理"""
    if channel_id in games:
        game = games[channel_id]
        winner, black, white = game.get_winner()
        result_text = (
            f"ゲーム終了！\n"
            f"スコア: ⚫️ (あなた) {black} - {white} ⚪️ (CPU)\n"
            f"勝者: **{winner}**"
        )
        safe_say(say, f"{format_board(game)}\n{result_text}", channel_id)
        del games[channel_id]

# --- Botの起動 ---
if __name__ == "__main__":
    # 環境変数を設定
    # macOS/Linux: export SLACK_APP_TOKEN=xapp-...
    # Windows: set SLACK_APP_TOKEN=xapp-...
    app_token = os.environ.get("SLACK_APP_TOKEN")
    if not app_token:
        print("エラー: 環境変数 SLACK_APP_TOKEN が設定されていません。")
    else:
        print("⚡️ Othello Bot is running!")
        SocketModeHandler(app, app_token).start()