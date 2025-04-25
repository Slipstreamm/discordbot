import random

class TicTacToe:
    def __init__(self, ai_player='O', ai_difficulty=None):
        """
        Initialize a new Tic Tac Toe game.
        
        Parameters:
          ai_player (str): The player that the AI controls ('X' or 'O').
          ai_difficulty (str): AI difficulty level. Should be one of:
              'random'  - chooses a random valid move.
              'rule'    - uses simple rules (win, block, take center/corner).
              'minimax' - uses the minimax algorithm for perfect play.
              None      - no AI moves; both players are human.
        """
        self.board = [' '] * 9  # 3x3 board represented in a list.
        self.current_player = 'X'
        self.winner = None
        self.game_over = False
        # If no AI difficulty is provided, no player is controlled by the computer.
        self.ai_player = ai_player if ai_difficulty is not None else None
        self.ai_difficulty = ai_difficulty

    def reset(self):
        """Reset the game to its initial state."""
        self.board = [' '] * 9
        self.current_player = 'X'
        self.winner = None
        self.game_over = False

    def get_board(self):
        """Return a copy of the current board."""
        return self.board[:]

    def play_turn(self, position=None):
        """
        Play one turn of the game.

        If it is the human's turn, you must supply the 'position' (an integer from 0 to 8).
        If it is the AI's turn, you may call play_turn() without a position; the AI 
        will pick and execute its move automatically and return the move's index.
        
        Returns:
          int: The position where the move was made.
          
        Raises:
          ValueError: If the move is invalid or if the game is already over.
        """
        if self.game_over:
            raise ValueError("Game is over.")
        # If the current player is controlled by AI, ignore any supplied position.
        if self.current_player == self.ai_player:
            move = self._select_ai_move()
            self._make_move(move)
            return move
        else:
            if position is None:
                raise ValueError("Human move required. Provide a position (0-8).")
            self._make_move(position)
            return position

    def _make_move(self, position):
        """Internal method to update the board with the current player's move."""
        if self.game_over:
            raise ValueError("Game is over.")
        if self.board[position] != ' ':
            raise ValueError("Invalid move; spot already taken.")
        self.board[position] = self.current_player
        self._check_game_over()
        if not self.game_over:
            self._switch_player()

    def _switch_player(self):
        """Switch the turn to the other player."""
        self.current_player = 'O' if self.current_player == 'X' else 'X'

    def _check_game_over(self):
        """Check the board for a win or tie."""
        win_combinations = [
            [0, 1, 2], [3, 4, 5], [6, 7, 8],   # Rows
            [0, 3, 6], [1, 4, 7], [2, 5, 8],   # Columns
            [0, 4, 8], [2, 4, 6]               # Diagonals
        ]
        for combo in win_combinations:
            if self.board[combo[0]] == self.board[combo[1]] == self.board[combo[2]] != ' ':
                self.winner = self.board[combo[0]]
                self.game_over = True
                return
        if ' ' not in self.board:
            self.game_over = True  # It's a tie.

    def is_game_over(self):
        """Return whether the game is over."""
        return self.game_over

    def get_winner(self):
        """Return the winner ('X' or 'O'); if it's a tie, returns None."""
        return self.winner

    def get_current_player(self):
        """Return the marker of the player whose turn it is."""
        return self.current_player

    def _get_valid_moves(self, board):
        """Return a list of valid move positions given a board state."""
        return [i for i, spot in enumerate(board) if spot == ' ']

    def _select_ai_move(self):
        """Select an AI move based on the chosen difficulty."""
        if self.ai_difficulty == 'random':
            return self._ai_random_move()
        elif self.ai_difficulty == 'rule':
            return self._ai_rule_move()
        elif self.ai_difficulty == 'minimax':
            return self._ai_minimax_move()
        else:
            raise ValueError("Invalid AI difficulty.")

    def _ai_random_move(self):
        """AI randomly selects one of the available moves."""
        valid_moves = self._get_valid_moves(self.board)
        return random.choice(valid_moves)

    def _ai_rule_move(self):
        """
        AI selects a move based on simple rules:
          1. Take a winning move if available.
          2. Block the opponent's winning move.
          3. Take the center if available.
          4. Take one of the corners.
          5. Otherwise, pick a random move.
        """
        valid_moves = self._get_valid_moves(self.board)
        # 1. Check for a winning move.
        for move in valid_moves:
            board_copy = self.board[:]
            board_copy[move] = self.ai_player
            if self._check_win(board_copy, self.ai_player):
                return move
        # 2. Check for a move to block the opponent.
        opponent = 'X' if self.ai_player == 'O' else 'O'
        for move in valid_moves:
            board_copy = self.board[:]
            board_copy[move] = opponent
            if self._check_win(board_copy, opponent):
                return move
        # 3. Take the center if it is free.
        if 4 in valid_moves:
            return 4
        # 4. Choose one of the available corners.
        corners = [i for i in [0, 2, 6, 8] if i in valid_moves]
        if corners:
            return random.choice(corners)
        # 5. Fallback: random move.
        return self._ai_random_move()

    def _check_win(self, board, player):
        """
        Helper method to check if a given board state is winning for a player.

        Returns True if the player has a winning combination.
        """
        win_combinations = [
            [0, 1, 2], [3, 4, 5], [6, 7, 8],
            [0, 3, 6], [1, 4, 7], [2, 5, 8],
            [0, 4, 8], [2, 4, 6]
        ]
        for combo in win_combinations:
            if board[combo[0]] == board[combo[1]] == board[combo[2]] == player:
                return True
        return False

    def _ai_minimax_move(self):
        """AI selects a move using the minimax algorithm."""
        score, move = self._minimax(self.board, True, 0)
        return move

    def _minimax(self, board, is_maximizing, depth):
        """
        Minimax algorithm to evaluate board positions.
        
        Parameters:
          board (list): The current board state.
          is_maximizing (bool): True if the AI should maximize the score.
          depth (int): Current depth of recursion (used for score adjustment).
        
        Returns:
          tuple: (score, move) where score is the evaluation of the board,
                 and move is the best move to make.
        """
        opponent = 'X' if self.ai_player == 'O' else 'O'
        if self._check_win(board, self.ai_player):
            return 10 - depth, None
        if self._check_win(board, opponent):
            return depth - 10, None
        if ' ' not in board:
            return 0, None

        valid_moves = self._get_valid_moves(board)

        if is_maximizing:
            best_score = -float('inf')
            best_move = None
            for move in valid_moves:
                board_copy = board[:]
                board_copy[move] = self.ai_player
                score, _ = self._minimax(board_copy, False, depth + 1)
                if score > best_score:
                    best_score = score
                    best_move = move
            return best_score, best_move
        else:
            best_score = float('inf')
            best_move = None
            for move in valid_moves:
                board_copy = board[:]
                board_copy[move] = opponent
                score, _ = self._minimax(board_copy, True, depth + 1)
                if score < best_score:
                    best_score = score
                    best_move = move
            return best_score, best_move

# Example usage:
# from tictactoe import TicTacToe

# # Create a game with the AI controlling 'O' using minimax (perfect play).
# game = TicTacToe(ai_player='O', ai_difficulty='minimax')

# # Game loop example:
# while not game.is_game_over():
#     print("Current board:", game.get_board())
#     if game.get_current_player() != game.ai_player:
#         # Human move: get input (for example, via input() or from a UI)
#         try:
#             pos = int(input("Enter your move (0-8): "))
#             game.play_turn(pos)
#         except ValueError as ve:
#             print("Error:", ve)
#     else:
#         # AI move: simply call play_turn() without a parameter.
#         ai_move = game.play_turn()
#         print(f"AI chose position {ai_move}")

# # After game is over, show the final result.
# print("Final board:", game.get_board())
# winner = game.get_winner()
# if winner:
#     print(f"Winner: {winner}")
# else:
#     print("It's a tie!")
