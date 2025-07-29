import random

class OthelloGame:
    """6x6のオセロゲームのロジックを管理するクラス"""

    def __init__(self):
        self.size = 6
        self.board = [[0] * self.size for _ in range(self.size)]
        # 0: 空, 1: 黒(User), -1: 白(CPU)
        self.current_player = 1

        # 初期配置
        mid = self.size // 2
        self.board[mid - 1][mid - 1] = -1  # 白
        self.board[mid - 1][mid] = 1       # 黒
        self.board[mid][mid - 1] = 1       # 黒
        self.board[mid][mid] = -1          # 白

    def is_valid_coord(self, x, y):
        """座標が盤面内にあるか"""
        return 0 <= x < self.size and 0 <= y < self.size

    def get_flippable_discs(self, x, y, player):
        """指定した場所に石を置いた場合に裏返せる石のリストを返す"""
        if not self.is_valid_coord(x, y) or self.board[y][x] != 0:
            return []

        flippable = []
        # 8方向をチェック
        for dx, dy in [(0, 1), (1, 0), (0, -1), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)]:
            line = []
            nx, ny = x + dx, y + dy
            while self.is_valid_coord(nx, ny) and self.board[ny][nx] == -player:
                line.append((nx, ny))
                nx += dx
                ny += dy
            if self.is_valid_coord(nx, ny) and self.board[ny][nx] == player and line:
                flippable.extend(line)
        return flippable

    def get_legal_moves(self, player):
        """プレイヤーが石を置ける合法手のリストを返す"""
        moves = {}
        for y in range(self.size):
            for x in range(self.size):
                if self.get_flippable_discs(x, y, player):
                    moves[(x, y)] = len(self.get_flippable_discs(x, y, player))
        return moves

    def make_move(self, x, y, player):
        """石を置き、相手の石を裏返す"""
        flippable = self.get_flippable_discs(x, y, player)
        if not flippable:
            return False

        self.board[y][x] = player
        for fx, fy in flippable:
            self.board[fy][fx] = player
        self.current_player *= -1  # ターン交代
        return True

    def cpu_move(self):
        """CPUの思考ルーチン (最も多く取れる手を選ぶ)"""
        legal_moves = self.get_legal_moves(-1) # CPUは白(-1)
        if not legal_moves:
            return None

        # 最も多く裏返せる手を選ぶ
        best_move = max(legal_moves, key=legal_moves.get)
        self.make_move(best_move[0], best_move[1], -1)
        return best_move

    def is_game_over(self):
        """ゲーム終了判定"""
        user_moves = self.get_legal_moves(1)
        cpu_moves = self.get_legal_moves(-1)
        return not user_moves and not cpu_moves

    def get_winner(self):
        """勝敗を判定し、スコアを返す"""
        black_score = sum(row.count(1) for row in self.board)
        white_score = sum(row.count(-1) for row in self.board)

        if black_score > white_score:
            winner = "⚫️ あなた"
        elif white_score > black_score:
            winner = "⚪️ CPU"
        else:
            winner = "引き分け"
        return winner, black_score, white_score