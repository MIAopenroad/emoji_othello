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
# プレイヤー2の設定待ち状態を管理
waiting_for_player2 = {}

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
                if (x, y) in legal_moves:
                    board_str += "🔵" # 現在のプレイヤーが置ける場所
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
    user_id = command["user_id"]
    
    if channel_id in games:
        safe_say(say, "このチャンネルでは既にゲームが進行中です。終了するには `/othello-end` と入力してください。", channel_id)
        return

    # プレイヤー名を取得
    try:
        user_info = app.client.users_info(user=user_id)
        player1_name = user_info["user"]["real_name"] or user_info["user"]["name"]
    except:
        player1_name = "プレイヤー1"
    
    # プレイヤー2の設定を待つ状態にする
    waiting_for_player2[channel_id] = {
        "player1_id": user_id,
        "player1_name": player1_name,
        "timestamp": time.time()
    }
    
    safe_say(say, f"6x6 オセロを開始します！\n⚫️ {player1_name} が参加しました。\nプレイヤー2が `/othello-join` と入力して参加してください。", channel_id)

@app.command("/othello-join")
def handle_join_game(ack, say, command):
    ack()
    channel_id = command["channel_id"]
    user_id = command["user_id"]
    
    if channel_id not in waiting_for_player2:
        safe_say(say, "参加待ちのゲームがありません。`/othello-start` でゲームを開始してください。", channel_id)
        return
    
    # プレイヤー1と同じユーザーは参加できない
    if user_id == waiting_for_player2[channel_id]["player1_id"]:
        safe_say(say, "プレイヤー1と同じユーザーは参加できません。", channel_id)
        return
    
    # プレイヤー2名を取得
    try:
        user_info = app.client.users_info(user=user_id)
        player2_name = user_info["user"]["real_name"] or user_info["user"]["name"]
    except:
        player2_name = "プレイヤー2"
    
    # ゲームを開始
    player1_name = waiting_for_player2[channel_id]["player1_name"]
    game = OthelloGame(player1_name=player1_name, player2_name=player2_name)
    games[channel_id] = game
    
    # プレイヤー情報を保存
    game.player1_id = waiting_for_player2[channel_id]["player1_id"]
    game.player2_id = user_id
    game.player_ids = {1: game.player1_id, -1: game.player2_id}
    
    # 待機状態を削除
    del waiting_for_player2[channel_id]
    
    board_text = format_board(game)
    current_player_emoji = game.get_current_player_emoji()
    current_player_name = game.get_current_player_name()
    
    safe_say(say, f"⚪️ {player2_name} が参加しました！\n{current_player_emoji} {current_player_name} のターンです。\n`/othello-put [A-F][1-6]` で石を置いてください。\n{board_text}", channel_id)

@app.command("/othello-put")
def handle_put_disc(ack, say, command):
    ack()
    channel_id = command["channel_id"]
    user_id = command["user_id"]
    
    if channel_id not in games:
        safe_say(say, "ゲームが開始されていません。`/othello-start` で開始してください。", channel_id)
        return

    game = games[channel_id]
    current_player_emoji = game.get_current_player_emoji()
    current_player_name = game.get_current_player_name()
    
    # 現在のプレイヤーが手番かチェック
    current_player_id = game.player_ids.get(game.current_player)
    if user_id != current_player_id:
        safe_say(say, f"{current_player_emoji} {current_player_name} のターンです。お待ちください。", channel_id)
        return

    coord_str = command.get("text", "").strip()
    x, y = coord_to_xy(coord_str)

    if x is None:
        safe_say(say, f"入力形式が正しくありません。`A1` のように入力してください。", channel_id)
        return

    if not game.get_flippable_discs(x, y, game.current_player):
        safe_say(say, f"{coord_str} には石を置けません。青いマス(🔵)に置いてください。", channel_id)
        return

    # 石を置く
    game.make_move(x, y, game.current_player)
    safe_say(say, f"{current_player_emoji} {current_player_name} が {coord_str.upper()} に置きました。", channel_id)

    # ゲーム終了チェック
    if game.is_game_over():
        end_game(channel_id, say)
        return

    # 次のプレイヤーの手番をチェック
    next_player_emoji = game.get_current_player_emoji()
    next_player_name = game.get_current_player_name()
    
    # 次のプレイヤーが置ける場所があるかチェック
    if not game.get_legal_moves(game.current_player):
        # パスの場合
        safe_say(say, f"{next_player_emoji} {next_player_name} は置ける場所がありません。パスします。", channel_id)
        game.current_player *= -1  # ターンを戻す
        
        # 再度ゲーム終了チェック
        if game.is_game_over():
            end_game(channel_id, say)
            return
        
        # 次のプレイヤーも置けない場合
        if not game.get_legal_moves(game.current_player):
            end_game(channel_id, say)
            return
    
    # 盤面更新
    board_text = format_board(game)
    safe_say(say, f"{next_player_emoji} {next_player_name} のターンです。\n{board_text}", channel_id)

@app.command("/othello-end")
def handle_end_game(ack, say, command):
    ack()
    channel_id = command["channel_id"]
    
    # 進行中のゲームを終了
    if channel_id in games:
        del games[channel_id]
        safe_say(say, "現在のゲームを強制終了しました。", channel_id)
    # 待機状態のゲームを終了
    elif channel_id in waiting_for_player2:
        del waiting_for_player2[channel_id]
        safe_say(say, "待機中のゲームを終了しました。", channel_id)
    else:
        safe_say(say, "進行中のゲームはありません。", channel_id)

def end_game(channel_id, say):
    """ゲーム終了時の処理"""
    if channel_id in games:
        game = games[channel_id]
        winner, player1_score, player2_score = game.get_winner()
        result_text = (
            f"ゲーム終了！\n"
            f"スコア: {game.player_emojis[1]} {game.player1_name} {player1_score} - {player2_score} {game.player_emojis[-1]} {game.player2_name}\n"
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