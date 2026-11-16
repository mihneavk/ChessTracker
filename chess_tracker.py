import os
import re
import glob
import json
import time
import math
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import tkinter as tk
from tkinter import messagebox, filedialog
import numpy as np
import chess
import chess.pgn
import chess.engine

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EXT_DIR = os.path.join(BASE_DIR, "chess_extension")
BRIDGE_PORT = 8765
MAX_ANALYSIS_SECONDS = 5.0

PIECE_SYMBOLS = {
    'P': '♙', 'N': '♘', 'B': '♗', 'R': '♖', 'Q': '♕', 'K': '♔',
    'p': '♟', 'n': '♞', 'b': '♝', 'r': '♜', 'q': '♛', 'k': '♚'
}

PIECE_TYPE_MAP = {
    'p': chess.PAWN,
    'n': chess.KNIGHT,
    'b': chess.BISHOP,
    'r': chess.ROOK,
    'q': chess.QUEEN,
    'k': chess.KING,
}

ARROW_COLORS = {
    1: "#f59e0b",  # Rank 1 (thickest) - Amber/Gold
    2: "#38bdf8",  # Rank 2 (medium)   - Sky Blue
    3: "#c084fc",  # Rank 3 (thin)     - Purple
}

TAMPERMONKEY_SCRIPT = f"""// ==UserScript==
// @name         ChessReader HTML Bridge
// @namespace    http://tampermonkey.net/
// @version      1.2
// @description  Sends live board state and move history from Chess.com to the Python tracker
// @match        *://*.chess.com/*
// @grant        GM_xmlhttpRequest
// @connect      127.0.0.1
// ==/UserScript==

(function() {{
    'use strict';

    function extractMoveSan(node) {{
        let san = "";
        function walk(el) {{
            if (!el) return;
            if (el.nodeType === Node.ELEMENT_NODE) {{
                const cls = (el.className || "").toString();
                if (/\\b(eval|score|classification|move-number|clock|time|tooltip)\\b/i.test(cls)) {{
                    return;
                }}
                const fig = el.getAttribute("data-figurine");
                if (fig) san += fig;
                el.childNodes.forEach(walk);
            }} else if (el.nodeType === Node.TEXT_NODE) {{
                san += el.textContent || "";
            }}
        }}
        walk(node);
        san = san.replace(/\\s+/g, "").replace(/^\\d+\\.+/, "").replace(/[!?‼⁇⁉⁈]+$/g, "").trim();
        return san;
    }}

    function readBoardFromDOM() {{
        const boardEl = document.querySelector("wc-chess-board, chess-board, .board");
        if (!boardEl) return null;

        const root = boardEl.shadowRoot || boardEl;
        const pieceEls = root.querySelectorAll(".piece");
        if (!pieceEls || pieceEls.length === 0) return null;

        const pieces = [];
        pieceEls.forEach((el) => {{
            const cls = el.className || "";
            const pMatch = cls.match(/\\b([wb])([pnbrqk])\\b/);
            const sMatch = cls.match(/\\bsquare-(\\d)(\\d)\\b/);
            if (pMatch && sMatch) {{
                pieces.push({{
                    color: pMatch[1],
                    type: pMatch[2],
                    file: parseInt(sMatch[1], 10),
                    rank: parseInt(sMatch[2], 10)
                }});
            }}
        }});

        if (pieces.length === 0) return null;

        const flipped = boardEl.classList.contains("flipped");
        const highlights = [];
        root.querySelectorAll(".highlight").forEach((el) => {{
            const sMatch = (el.className || "").match(/\\bsquare-(\\d)(\\d)\\b/);
            if (sMatch) {{
                highlights.push({{
                    file: parseInt(sMatch[1], 10),
                    rank: parseInt(sMatch[2], 10)
                }});
            }}
        }});

        const moves = [];
        let selectedPly = null;
        const moveNodes = document.querySelectorAll(
            "wc-simple-move-list [data-ply], .move-list [data-ply], .vertical-move-list .node, [data-node]"
        );
        const seenKeys = new Set();

        moveNodes.forEach((node) => {{
            const plyAttr = node.getAttribute("data-ply") || node.getAttribute("data-node");
            if (plyAttr && seenKeys.has(plyAttr)) return;
            if (plyAttr) seenKeys.add(plyAttr);

            const san = extractMoveSan(node);
            if (!san || !/^[O0-9a-hNBRQK]/.test(san)) return;

            const plyNum = plyAttr ? parseInt(plyAttr, 10) : (moves.length + 1);
            const isSelected = (
                node.classList.contains("selected") ||
                node.classList.contains("active") ||
                node.getAttribute("aria-current") === "true" ||
                node.querySelector(".selected, .active") !== null
            );

            if (isSelected && !isNaN(plyNum)) {{
                selectedPly = plyNum;
            }}

            moves.push({{
                ply: isNaN(plyNum) ? (moves.length + 1) : plyNum,
                san: san,
                selected: isSelected
            }});
        }});

        return {{ flipped, pieces, highlights, moves, selectedPly }};
    }}

    let lastPayload = "";
    setInterval(() => {{
        const state = readBoardFromDOM();
        if (!state) return;
        const serialized = JSON.stringify(state);
        if (serialized !== lastPayload) {{
            lastPayload = serialized;
            GM_xmlhttpRequest({{
                method: "POST",
                url: "http://127.0.0.1:{BRIDGE_PORT}/update",
                headers: {{ "Content-Type": "application/json" }},
                data: serialized
            }});
        }}
    }}, 250);
}})();
"""


def ensure_browser_extension_files():
    """Generates a Manifest V3 extension (Chrome + Firefox compatible) in chess_extension."""
    os.makedirs(EXT_DIR, exist_ok=True)

    manifest = {
        "manifest_version": 3,
        "name": "ChessReader HTML Bridge",
        "version": "1.2",
        "description": "Reads live board state and move history from Chess.com HTML",
        "host_permissions": [
            "*://*.chess.com/*",
            "http://127.0.0.1/*"
        ],
        "background": {
            "service_worker": "background.js"
        },
        "content_scripts": [
            {
                "matches": ["*://*.chess.com/*"],
                "js": ["content.js"],
                "run_at": "document_idle"
            }
        ]
    }

    background_js = f"""const api = typeof browser !== "undefined" ? browser : chrome;
api.runtime.onMessage.addListener((msg) => {{
  if (msg && msg.type === "CHESS_STATE") {{
    fetch("http://127.0.0.1:{BRIDGE_PORT}/update", {{
      method: "POST",
      headers: {{ "Content-Type": "application/json" }},
      body: JSON.stringify(msg.payload)
    }}).catch(() => {{}});
  }}
}});
"""

    content_js = """const api = typeof browser !== "undefined" ? browser : chrome;

function extractMoveSan(node) {
  let san = "";
  function walk(el) {
    if (!el) return;
    if (el.nodeType === Node.ELEMENT_NODE) {
      const cls = (el.className || "").toString();
      if (/\\b(eval|score|classification|move-number|clock|time|tooltip)\\b/i.test(cls)) {
        return;
      }
      const fig = el.getAttribute("data-figurine");
      if (fig) san += fig;
      el.childNodes.forEach(walk);
    } else if (el.nodeType === Node.TEXT_NODE) {
      san += el.textContent || "";
    }
  }
  walk(node);
  san = san.replace(/\\s+/g, "").replace(/^\\d+\\.+/, "").replace(/[!?‼⁇⁉⁈]+$/g, "").trim();
  return san;
}

function readBoardFromDOM() {
  const boardEl = document.querySelector("wc-chess-board, chess-board, .board");
  if (!boardEl) return null;

  const root = boardEl.shadowRoot || boardEl;
  const pieceEls = root.querySelectorAll(".piece");
  if (!pieceEls || pieceEls.length === 0) return null;

  const pieces = [];
  pieceEls.forEach((el) => {
    const cls = el.className || "";
    const pMatch = cls.match(/\\b([wb])([pnbrqk])\\b/);
    const sMatch = cls.match(/\\bsquare-(\\d)(\\d)\\b/);
    if (pMatch && sMatch) {
      pieces.push({
        color: pMatch[1],
        type: pMatch[2],
        file: parseInt(sMatch[1], 10),
        rank: parseInt(sMatch[2], 10)
      });
    }
  });

  if (pieces.length === 0) return null;

  const flipped = boardEl.classList.contains("flipped");
  const highlights = [];
  root.querySelectorAll(".highlight").forEach((el) => {
    const sMatch = (el.className || "").match(/\\bsquare-(\\d)(\\d)\\b/);
    if (sMatch) {
      highlights.push({
        file: parseInt(sMatch[1], 10),
        rank: parseInt(sMatch[2], 10)
      });
    }
  });

  const moves = [];
  let selectedPly = null;
  const moveNodes = document.querySelectorAll(
    "wc-simple-move-list [data-ply], .move-list [data-ply], .vertical-move-list .node, [data-node]"
  );
  const seenKeys = new Set();

  moveNodes.forEach((node) => {
    const plyAttr = node.getAttribute("data-ply") || node.getAttribute("data-node");
    if (plyAttr && seenKeys.has(plyAttr)) return;
    if (plyAttr) seenKeys.add(plyAttr);

    const san = extractMoveSan(node);
    if (!san || !/^[O0-9a-hNBRQK]/.test(san)) return;

    const plyNum = plyAttr ? parseInt(plyAttr, 10) : (moves.length + 1);
    const isSelected = (
      node.classList.contains("selected") ||
      node.classList.contains("active") ||
      node.getAttribute("aria-current") === "true" ||
      node.querySelector(".selected, .active") !== null
    );

    if (isSelected && !isNaN(plyNum)) {
      selectedPly = plyNum;
    }

    moves.push({
      ply: isNaN(plyNum) ? (moves.length + 1) : plyNum,
      san: san,
      selected: isSelected
    });
  });

  return { flipped, pieces, highlights, moves, selectedPly };
}

let lastPayload = "";
setInterval(() => {
  const state = readBoardFromDOM();
  if (!state) return;
  const serialized = JSON.stringify(state);
  if (serialized !== lastPayload) {
    lastPayload = serialized;
    try {
      api.runtime.sendMessage({ type: "CHESS_STATE", payload: state });
    } catch (e) {}
  }
}, 250);
"""

    with open(os.path.join(EXT_DIR, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    with open(os.path.join(EXT_DIR, "background.js"), "w", encoding="utf-8") as f:
        f.write(background_js)
    with open(os.path.join(EXT_DIR, "content.js"), "w", encoding="utf-8") as f:
        f.write(content_js)


class ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True


class DarkAutoScrollbar(tk.Canvas):
    """Sleek dark-themed scrollbar that automatically hides when all content fits."""

    def __init__(
        self,
        parent,
        command=None,
        width=7,
        bg="#0d0d0d",
        thumb_color="#2a2a2e",
        hover_color="#4b5563",
    ):
        super().__init__(
            parent,
            width=width,
            bg=bg,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self.command = command
        self.thumb_color = thumb_color
        self.hover_color = hover_color
        self.first = 0.0
        self.last = 1.0
        self._dragging = False
        self._hovering = False
        self._drag_offset = 0.0
        self._visible = False

        self.bind("<Configure>", lambda _e: self._redraw())
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)

    def set(self, first, last):
        self.first = float(first)
        self.last = float(last)
        if self.first <= 0.0 and self.last >= 1.0:
            if self._visible:
                self._visible = False
                self.grid_remove()
        else:
            if not self._visible:
                self._visible = True
                self.grid()
            self._redraw()

    def _redraw(self):
        self.delete("all")
        if not self._visible:
            return
        h = self.winfo_height()
        w = self.winfo_width()
        if h <= 1 or w <= 1:
            return

        y1 = max(2, int(self.first * h) + 2)
        y2 = min(h - 2, max(y1 + 16, int(self.last * h) - 2))
        color = self.hover_color if (self._hovering or self._dragging) else self.thumb_color
        self.create_rectangle(1, y1, w - 1, y2, fill=color, outline="")

    def _on_enter(self, _event):
        self._hovering = True
        self._redraw()

    def _on_leave(self, _event):
        self._hovering = False
        self._redraw()

    def _on_press(self, event):
        h = max(1, self.winfo_height())
        thumb_y1 = self.first * h
        thumb_y2 = self.last * h
        span = self.last - self.first

        if thumb_y1 <= event.y <= thumb_y2:
            self._drag_offset = event.y - thumb_y1
        else:
            self._drag_offset = (span * h) / 2.0
            if self.command:
                new_first = max(0.0, min(1.0 - span, (event.y - self._drag_offset) / h))
                self.command("moveto", new_first)

        self._dragging = True
        self._redraw()

    def _on_drag(self, event):
        if self._dragging and self.command:
            h = max(1, self.winfo_height())
            span = self.last - self.first
            new_first = max(0.0, min(1.0 - span, (event.y - self._drag_offset) / h))
            self.command("moveto", new_first)

    def _on_release(self, _event):
        self._dragging = False
        self._redraw()


class ChessScreenApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Chess.com HTML Live Tracker + Rodent IV")
        self.root.geometry("1060x760")
        self.root.minsize(920, 680)
        self.root.resizable(True, True)
        self.root.configure(bg="#000000")

        ensure_browser_extension_files()

        self.board = chess.Board()
        self.flipped = False
        self.browser_connected = False
        self.last_dom_payload = None
        self.http_server = None

        # Real match history tracking
        self.known_san_sequence = []
        self.match_moves = []          # Full list of real chess.Move objects in the match
        self.last_html_ply = 0         # Ply currently active on Chess.com
        self.last_html_board_fen = self.board.board_fen()
        self.view_ply = 0              # Ply currently viewed in this app
        self.manual_history_nav = False

        # Sandbox ("Try Move") state
        self.sandbox_mode = False
        self.sandbox_base_ply = 0      # Real match ply from which sandbox branched off
        self.sandbox_moves = []        # Hypothetical moves made on top of sandbox_base_ply
        self.selected_square = None
        self.legal_targets_for_selected = set()

        # Arrows for Top 3 recommended moves: list of (rank_int, chess.Move)
        self.top3_arrows = []
        self.preview_canvases = []

        self.engine = None
        self.engine_path = self._auto_find_rodent()
        self.engine_lock = threading.Lock()
        self.analysis_generation = 0
        self.is_analyzing = False
        self.current_eval_cp = 0.0
        self.current_eval_text = "0.0"

        self.show_eval_var = tk.BooleanVar(value=False)
        self.show_top3_var = tk.BooleanVar(value=False)
        self.elo_var = tk.IntVar(value=1500)

        self.board_size = 560
        self.controls_layout_mode = None
        self.top_bar_height_est = 66
        self.side_bar_width = 216

        self._build_ui()
        self._draw_board()
        self._draw_eval_bar()
        self._update_pgn_display()
        self._update_nav_buttons()
        self._update_elo_labels()
        self._start_html_bridge_server()

        # Keyboard shortcuts for Backwards / Forwards
        self.root.bind("<Left>", self._on_left_key)
        self.root.bind("<Right>", self._on_right_key)

        if self.engine_path:
            self.engine_status_lbl.config(
                text=f"Connecting to {os.path.basename(self.engine_path)}...",
                fg="#fbbf24"
            )
            threading.Thread(
                target=self._init_rodent,
                args=(self.engine_path,),
                daemon=True
            ).start()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ================= TIME & RANK PROFILES =================
    def _get_rank_profile(self, elo=None):
        if elo is None:
            elo = self.elo_var.get()

        if elo >= 2850:
            return {
                "rank_short": "MAX (~2975)",
                "rank_desc": "MAX (~2975 Elo)",
                "primary_time": 0.90,
                "refine_time": 0.45,
                "screen_time": 0.06,
                "max_candidates": 9,
                "max_depth": 14,
                "est_top3": 2.3,
                "est_eval": 0.8,
            }
        elif elo >= 2400:
            return {
                "rank_short": f"{elo} Elo",
                "rank_desc": f"{elo} Elo (Grandmaster)",
                "primary_time": 0.75,
                "refine_time": 0.38,
                "screen_time": 0.05,
                "max_candidates": 8,
                "max_depth": 13,
                "est_top3": 1.9,
                "est_eval": 0.7,
            }
        elif elo >= 2000:
            return {
                "rank_short": f"{elo} Elo",
                "rank_desc": f"{elo} Elo (Master)",
                "primary_time": 0.60,
                "refine_time": 0.30,
                "screen_time": 0.05,
                "max_candidates": 8,
                "max_depth": 12,
                "est_top3": 1.6,
                "est_eval": 0.6,
            }
        elif elo >= 1500:
            return {
                "rank_short": f"{elo} Elo",
                "rank_desc": f"{elo} Elo (Intermediate)",
                "primary_time": 0.45,
                "refine_time": 0.24,
                "screen_time": 0.04,
                "max_candidates": 7,
                "max_depth": 11,
                "est_top3": 1.2,
                "est_eval": 0.5,
            }
        else:
            return {
                "rank_short": f"{elo} Elo",
                "rank_desc": f"{elo} Elo (Beginner / Club)",
                "primary_time": 0.28,
                "refine_time": 0.15,
                "screen_time": 0.03,
                "max_candidates": 5,
                "max_depth": 9,
                "est_top3": 0.8,
                "est_eval": 0.3,
            }

    def _update_elo_labels(self):
        prof = self._get_rank_profile()
        elo = self.elo_var.get()
        color = "#f59e0b" if elo >= 2850 else "#00d4ff"
        self.elo_value_lbl.config(text=f"Level: {prof['rank_desc']}", fg=color)
        self.elo_time_hint_lbl.config(
            text=f"Rank: {prof['rank_short']} | Est: ~{prof['est_top3']:.1f}s (cap {MAX_ANALYSIS_SECONDS:.0f}s)"
        )

    # ================= LOCAL SERVER FOR HTML BRIDGE =================
    def _start_html_bridge_server(self):
        app_ref = self

        class BridgeHandler(BaseHTTPRequestHandler):
            def _send_cors_headers(self):
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.send_header("Access-Control-Allow-Private-Network", "true")

            def do_OPTIONS(self):
                self.send_response(200)
                self._send_cors_headers()
                self.end_headers()

            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(b'{"status":"ok"}')

            def do_POST(self):
                if self.path != "/update":
                    self.send_response(404)
                    self.end_headers()
                    return

                content_len = int(self.headers.get("Content-Length", 0))
                raw_body = self.rfile.read(content_len)
                try:
                    payload = json.loads(raw_body.decode("utf-8"))
                    app_ref.root.after(0, lambda: app_ref._on_html_board_update(payload))
                except Exception:
                    pass

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(b'{"ok":true}')

            def log_message(self, format, *args):
                pass

        try:
            self.http_server = ReusableThreadingHTTPServer(("127.0.0.1", BRIDGE_PORT), BridgeHandler)
            threading.Thread(target=self.http_server.serve_forever, daemon=True).start()
        except Exception as e:
            self.status_label.config(
                text=f"Local server error (port {BRIDGE_PORT}): {e}",
                fg="#ff5555"
            )

    def _board_state_signature(self, b):
        return (b.board_fen(), b.turn, b.castling_rights, b.ep_square, len(b.move_stack))

    def _clean_san(self, raw_san):
        s = raw_san.strip()
        s = re.sub(r'^\d+\.+', '', s)
        s = re.sub(r'[!?‼⁇⁉⁈]+$', '', s)
        s = s.replace("0-0-0", "O-O-O").replace("0-0", "O-O")
        return s.strip()

    def _build_sequence_states(self, san_list):
        temp = chess.Board()
        states = [temp.copy(stack=True)]
        valid_sans = []

        for raw_san in san_list:
            san = self._clean_san(raw_san)
            if not san:
                continue
            try:
                temp.push_san(san)
                valid_sans.append(san)
                states.append(temp.copy(stack=True))
            except Exception:
                break

        return states, valid_sans

    def _extract_highlight_squares(self, highlights):
        sq_set = set()
        for hl in highlights:
            f_idx = int(hl.get("file", 0)) - 1
            r_idx = int(hl.get("rank", 0)) - 1
            if 0 <= f_idx < 8 and 0 <= r_idx < 8:
                sq_set.add(chess.square(f_idx, r_idx))
        return sq_set

    def _reconstruct_board_from_payload(self, payload, reference_board):
        """
        Returns (reconstructed_board, (active_ply, total_plies), full_match_moves_list)
        """
        pieces_data = payload.get("pieces", [])
        if not pieces_data:
            return None, (0, 0), []

        raw_moves = payload.get("moves", [])
        highlights = payload.get("highlights", [])
        selected_ply = payload.get("selectedPly", None)

        incoming_sans = []
        for idx, item in enumerate(raw_moves):
            if isinstance(item, dict):
                san_val = item.get("san", "")
                if san_val:
                    incoming_sans.append(san_val)
                if item.get("selected") and selected_ply is None:
                    selected_ply = item.get("ply", idx + 1)
            elif isinstance(item, str):
                incoming_sans.append(item)

        dom_board = chess.Board.empty()
        for p in pieces_data:
            f_idx = int(p.get("file", 0)) - 1
            r_idx = int(p.get("rank", 0)) - 1
            p_type = PIECE_TYPE_MAP.get(p.get("type", ""))
            p_color = chess.WHITE if p.get("color") == "w" else chess.BLACK
            if 0 <= f_idx < 8 and 0 <= r_idx < 8 and p_type:
                sq = chess.square(f_idx, r_idx)
                dom_board.set_piece_at(sq, chess.Piece(p_type, p_color))

        target_board_fen = dom_board.board_fen()
        hl_squares = self._extract_highlight_squares(highlights)

        states, valid_sans = self._build_sequence_states(incoming_sans)

        if (
            len(valid_sans) < len(self.known_san_sequence)
            and self.known_san_sequence[:len(valid_sans)] == valid_sans
        ):
            states, valid_sans = self._build_sequence_states(self.known_san_sequence)
        elif valid_sans:
            self.known_san_sequence = valid_sans

        total_plies = len(states) - 1
        full_match_moves = list(states[-1].move_stack) if total_plies > 0 else []

        if isinstance(selected_ply, int) and 0 <= selected_ply <= total_plies:
            if states[selected_ply].board_fen() == target_board_fen:
                return states[selected_ply].copy(stack=True), (selected_ply, total_plies), full_match_moves

        matching_indices = [
            i for i, st in enumerate(states) if st.board_fen() == target_board_fen
        ]

        if len(matching_indices) == 1:
            idx = matching_indices[0]
            return states[idx].copy(stack=True), (idx, total_plies), full_match_moves

        if len(matching_indices) > 1:
            if hl_squares:
                hl_matches = []
                for idx in matching_indices:
                    if idx == 0 and not hl_squares:
                        hl_matches.append(0)
                    elif idx > 0:
                        last_mv = states[idx].peek()
                        if {last_mv.from_square, last_mv.to_square} == hl_squares:
                            hl_matches.append(idx)
                if len(hl_matches) == 1:
                    idx = hl_matches[0]
                    return states[idx].copy(stack=True), (idx, total_plies), full_match_moves
                if hl_matches:
                    matching_indices = hl_matches

            cur_ply = len(reference_board.move_stack) if reference_board is not None else total_plies
            best_idx = min(matching_indices, key=lambda i: abs(i - cur_ply))
            return states[best_idx].copy(stack=True), (best_idx, total_plies), full_match_moves

        if reference_board is not None:
            if reference_board.board_fen() == target_board_fen:
                ply_now = len(reference_board.move_stack)
                return reference_board.copy(stack=True), (ply_now, max(ply_now, total_plies)), list(reference_board.move_stack)

            temp_back = reference_board.copy(stack=True)
            while len(temp_back.move_stack) > 0:
                temp_back.pop()
                if temp_back.board_fen() == target_board_fen:
                    ply_now = len(temp_back.move_stack)
                    return temp_back, (ply_now, max(ply_now, total_plies)), list(reference_board.move_stack)

            for mv in reference_board.legal_moves:
                b_next = reference_board.copy(stack=True)
                b_next.push(mv)
                if b_next.board_fen() == target_board_fen:
                    ply_now = len(b_next.move_stack)
                    return b_next, (ply_now, max(ply_now, total_plies)), list(b_next.move_stack)

        self.known_san_sequence = []
        last_moved_color = None
        for sq in hl_squares:
            piece_on_hl = dom_board.piece_at(sq)
            if piece_on_hl is not None:
                last_moved_color = piece_on_hl.color
                break

        if last_moved_color is not None:
            dom_board.turn = not last_moved_color
        else:
            dom_board.turn = chess.WHITE

        return dom_board, (0, 0), []

    def _format_sync_status_text(self):
        turn_str = "White" if self.board.turn == chess.WHITE else "Black"
        total_plies = len(self.match_moves)
        if self.sandbox_mode:
            return (
                f"🧪 TEST MODE (+{len(self.sandbox_moves)} move(s) from move {self.sandbox_base_ply}/{total_plies}, {turn_str} to move)",
                "#60a5fa"
            )
        if total_plies > 0 and self.view_ply < total_plies:
            return (
                f"⏪ History view: move {self.view_ply}/{total_plies} ({turn_str} to move)",
                "#38bdf8"
            )
        return (
            f"✓ 100% Synced from HTML ({turn_str} to move)",
            "#00ff66"
        )

    def _on_html_board_update(self, payload, force_analysis=False):
        self.last_dom_payload = payload
        if not self.browser_connected:
            self.browser_connected = True
            self.conn_badge.config(text="● HTML Connected", fg="#00ff66")

        reconstructed, hist, full_match_moves = self._reconstruct_board_from_payload(payload, self.board)
        if reconstructed is None:
            return

        html_ply, _ = hist
        prev_sig = (
            [m.uci() for m in self.match_moves],
            self.last_html_ply,
            self.last_html_board_fen,
        )
        new_sig = (
            [m.uci() for m in full_match_moves],
            html_ply,
            reconstructed.board_fen(),
        )
        html_changed = (new_sig != prev_sig)

        self.match_moves = full_match_moves
        self.last_html_ply = html_ply
        self.last_html_board_fen = reconstructed.board_fen()
        self.flipped = bool(payload.get("flipped", False))

        if self.sandbox_mode:
            self._update_nav_buttons()
            return

        if self.manual_history_nav and not html_changed and not force_analysis:
            self._update_nav_buttons()
            return

        self.manual_history_nav = False
        self.view_ply = html_ply

        if full_match_moves:
            target_board = chess.Board()
            for mv in full_match_moves[:html_ply]:
                target_board.push(mv)
        else:
            target_board = reconstructed

        board_changed = (
            self._board_state_signature(target_board) != self._board_state_signature(self.board)
        )
        self.board = target_board

        if board_changed:
            self.top3_arrows = []

        self._draw_board()
        self._update_pgn_display()
        self._update_nav_buttons()

        status_txt, status_col = self._format_sync_status_text()
        self.status_label.config(text=status_txt, fg=status_col)

        if board_changed or force_analysis:
            self._request_engine_analysis()

    def _show_browser_connect_dialog(self):
        win = tk.Toplevel(self.root)
        win.title("Connect Browser (Chrome / Firefox)")
        win.geometry("740x470")
        win.minsize(680, 440)
        win.configure(bg="#0d0d0d")
        win.resizable(True, True)

        container = tk.Frame(win, bg="#0d0d0d")
        container.pack(fill="both", expand=True, padx=24, pady=16)

        tk.Label(
            container,
            text="DIRECT CONNECTION TO CHESS.COM HTML (CHROME / FIREFOX)",
            bg="#0d0d0d",
            fg="#00ff66",
            font=("Consolas", 11, "bold"),
            anchor="w"
        ).pack(fill="x", pady=(0, 12))

        info_txt = (
            "METHOD 1 — Chrome / Edge / Firefox (Manifest V3 Extension):\n"
            "  1. In Chrome open: chrome://extensions  and enable 'Developer mode' (top-right).\n"
            "  2. Click 'Load unpacked' and select the 'chess_extension' folder.\n"
            "     (In Firefox: about:debugging#/runtime/this-firefox -> Load Temporary Add-on -> manifest.json)\n"
            "  3. Refresh (F5) your Chess.com tab.\n\n"
            "METHOD 2 — Using Tampermonkey:\n"
            "  1. In Chrome: chrome://extensions -> Developer mode ON -> Details on Tampermonkey\n"
            "     -> enable 'Allow User Scripts' (if visible).\n"
            "  2. Click the green button below, paste the script into Tampermonkey, and save (Ctrl+S)."
        )

        info_lbl = tk.Label(
            container,
            text=info_txt,
            bg="#0d0d0d",
            fg="#e5e7eb",
            font=("Consolas", 9),
            justify="left",
            anchor="nw",
            wraplength=680
        )
        info_lbl.pack(fill="x", pady=(0, 14))

        def on_dialog_resize(event):
            if event.widget is win:
                new_wrap = max(480, event.width - 56)
                info_lbl.config(wraplength=new_wrap)
                path_lbl.config(wraplength=new_wrap)

        win.bind("<Configure>", on_dialog_resize)

        btn_row = tk.Frame(container, bg="#0d0d0d")
        btn_row.pack(fill="x", pady=8)

        def open_ext_folder():
            ensure_browser_extension_files()
            os.startfile(EXT_DIR)

        def copy_tm_script():
            self.root.clipboard_clear()
            self.root.clipboard_append(TAMPERMONKEY_SCRIPT)
            messagebox.showinfo(
                "Copied!",
                "Tampermonkey script copied to clipboard.\n"
                "Paste it into Tampermonkey and press Ctrl+S.",
                parent=win
            )

        tk.Button(
            btn_row,
            text="📂 Open chess_extension Folder",
            command=open_ext_folder,
            bg="#2563eb",
            fg="#ffffff",
            activebackground="#1d4ed8",
            activeforeground="#ffffff",
            relief="flat",
            font=("Consolas", 9, "bold"),
            padx=14,
            pady=7,
            cursor="hand2"
        ).pack(side=tk.LEFT, padx=(0, 10))

        tk.Button(
            btn_row,
            text="📋 Copy Tampermonkey Script",
            command=copy_tm_script,
            bg="#16a34a",
            fg="#ffffff",
            activebackground="#15803d",
            activeforeground="#ffffff",
            relief="flat",
            font=("Consolas", 9, "bold"),
            padx=14,
            pady=7,
            cursor="hand2"
        ).pack(side=tk.LEFT)

        path_lbl = tk.Label(
            container,
            text=f"Extension path: {EXT_DIR}",
            bg="#0d0d0d",
            fg="#9ca3af",
            font=("Consolas", 8),
            anchor="w",
            justify="left",
            wraplength=680
        )
        path_lbl.pack(fill="x", pady=(14, 0))

    # ================= RODENT IV ENGINE =================
    def _auto_find_rodent(self):
        preferred_paths = [
            os.path.join(BASE_DIR, "Rodent_IV", "rodent-iv-x64.exe"),
            os.path.join(BASE_DIR, "Rodent_IV", "rodent-iv-plain.exe"),
            os.path.join(BASE_DIR, "Rodent_IV", "rodent-iv-x32.exe"),
            os.path.join(BASE_DIR, "rodent-iv-x64.exe"),
        ]
        for path in preferred_paths:
            if os.path.isfile(path):
                return path

        matches = glob.glob(os.path.join(BASE_DIR, "**", "*rodent*.exe"), recursive=True)
        if matches:
            matches.sort(key=lambda p: (0 if "x64" in p.lower() else 1, p))
            return matches[0]
        return None

    def _init_rodent(self, path):
        with self.engine_lock:
            if self.engine:
                try:
                    self.engine.quit()
                except Exception:
                    pass
                self.engine = None

            try:
                engine_dir = os.path.dirname(os.path.abspath(path))
                eng = chess.engine.SimpleEngine.popen_uci(path, cwd=engine_dir)
                self.engine = eng
                self.engine_path = path
                self._apply_rodent_difficulty_locked()

                bot_name = os.path.basename(path)
                self.root.after(0, lambda: self.engine_status_lbl.config(
                    text=f"✓ Auto-connected: {bot_name}",
                    fg="#00ff66"
                ))
                self.root.after(0, self._request_engine_analysis)
            except Exception as e:
                self.engine = None
                self.root.after(0, lambda: self.engine_status_lbl.config(
                    text="Failed to start Rodent IV!",
                    fg="#ff5555"
                ))
                self.root.after(0, lambda: messagebox.showerror(
                    "Rodent IV Error", f"Could not start the engine:\n{e}"
                ))

    def _apply_rodent_difficulty_locked(self, force_max=False):
        if not self.engine:
            return
        elo = self.elo_var.get()
        opts = {}

        if "UseBook" in self.engine.options:
            opts["UseBook"] = False

        if force_max or elo >= 2850:
            if "UCI_LimitStrength" in self.engine.options:
                opts["UCI_LimitStrength"] = False
        else:
            if "UCI_LimitStrength" in self.engine.options:
                opts["UCI_LimitStrength"] = True
            if "UCI_Elo" in self.engine.options:
                min_elo = self.engine.options["UCI_Elo"].min or 600
                max_elo = self.engine.options["UCI_Elo"].max or 2800
                opts["UCI_Elo"] = max(min_elo, min(max_elo, int(elo)))
        if opts:
            try:
                self.engine.configure(opts)
            except Exception:
                pass

    def _on_elo_changed(self, _val=None):
        self._update_elo_labels()
        self.analysis_generation += 1

        if self.engine:
            def reconfigure():
                with self.engine_lock:
                    self._apply_rodent_difficulty_locked()
                self.root.after(0, self._request_engine_analysis)

            threading.Thread(target=reconfigure, daemon=True).start()

    def _select_rodent_dialog(self):
        initial_dir = os.path.join(BASE_DIR, "Rodent_IV")
        if not os.path.isdir(initial_dir):
            initial_dir = BASE_DIR

        path = filedialog.askopenfilename(
            initialdir=initial_dir,
            title="Select Rodent IV executable (e.g., rodent-iv-x64.exe)",
            filetypes=[("Rodent IV Executables", "*.exe"), ("All Files", "*.*")]
        )
        if path:
            threading.Thread(target=self._init_rodent, args=(path,), daemon=True).start()

    # ================= RESPONSIVE UI CONSTRUCTION =================
    def _build_ui(self):
        main_container = tk.Frame(self.root, bg="#000000")
        main_container.pack(fill="both", expand=True, padx=14, pady=10)

        right_frame = tk.Frame(
            main_container,
            bg="#0a0a0a",
            width=425,
            highlightthickness=1,
            highlightbackground="#262626"
        )
        right_frame.pack(side=tk.RIGHT, fill="y", padx=(12, 0))
        right_frame.pack_propagate(False)

        self.left_frame = tk.Frame(main_container, bg="#000000")
        self.left_frame.pack(side=tk.LEFT, fill="both", expand=True)
        self.left_frame.bind("<Configure>", self._on_left_frame_resize)

        # ================= ADAPTIVE CONTROLS BAR (TOP OR LEFT SIDE COLUMN) =================
        self.controls_frame = tk.Frame(self.left_frame, bg="#000000")
        self.controls_inner = tk.Frame(self.controls_frame, bg="#000000")

        self.connect_btn = tk.Button(
            self.controls_inner,
            text="🌐 Connect Browser (HTML)",
            command=self._show_browser_connect_dialog,
            bg="#2563eb",
            fg="#ffffff",
            activebackground="#1d4ed8",
            activeforeground="#ffffff",
            relief="flat",
            font=("Consolas", 9, "bold"),
            padx=10,
            pady=5,
            cursor="hand2"
        )

        self.flip_btn = tk.Button(
            self.controls_inner,
            text="⇅ Flip Board",
            command=self._toggle_flip,
            bg="#1a1a1a",
            fg="#ffffff",
            activebackground="#333333",
            activeforeground="#ffffff",
            relief="flat",
            font=("Consolas", 9, "bold"),
            padx=10,
            pady=5,
            cursor="hand2"
        )

        self.reset_btn = tk.Button(
            self.controls_inner,
            text="↺ Reset",
            command=self._reset_game,
            bg="#1a1a1a",
            fg="#bbbbbb",
            activebackground="#333333",
            activeforeground="#ffffff",
            relief="flat",
            font=("Consolas", 9),
            padx=8,
            pady=5,
            cursor="hand2"
        )

        self.conn_badge = tk.Label(
            self.controls_inner,
            text="● Waiting for HTML",
            bg="#000000",
            fg="#fbbf24",
            font=("Consolas", 9, "bold")
        )

        self.status_label = tk.Label(
            self.controls_frame,
            text="Click '🌐 Connect Browser (HTML)' to link Chrome or Firefox",
            bg="#000000",
            fg="#888888",
            font=("Consolas", 9)
        )

        self.board_stage_frame = tk.Frame(self.left_frame, bg="#000000")

        self.board_row_frame = tk.Frame(self.board_stage_frame, bg="#000000")
        self.board_row_frame.place(relx=0.5, rely=0.5, anchor="center")

        self.canvas = tk.Canvas(
            self.board_row_frame,
            width=self.board_size,
            height=self.board_size,
            bg="#000000",
            highlightthickness=1,
            highlightbackground="#333333",
            cursor="hand2"
        )
        self.canvas.pack(side=tk.LEFT)
        self.canvas.bind("<Button-1>", self._on_board_click)

        self.eval_bar_width = 32
        self.eval_canvas = tk.Canvas(
            self.board_row_frame,
            width=self.eval_bar_width,
            height=self.board_size,
            bg="#111111",
            highlightthickness=1,
            highlightbackground="#333333"
        )

        # Start in horizontal top mode; auto-switches to side column if space permits
        self._apply_controls_layout("top")

        # ================= RIGHT SIDE (RODENT IV ENGINE + NAV + PGN) =================
        tk.Label(
            right_frame,
            text="RODENT IV ENGINE",
            bg="#0a0a0a",
            fg="#ffffff",
            font=("Consolas", 11, "bold")
        ).pack(pady=(10, 4))

        self.select_bot_btn = tk.Button(
            right_frame,
            text="⚙ Change Engine (.exe)",
            command=self._select_rodent_dialog,
            bg="#1f2937",
            fg="#ffffff",
            activebackground="#374151",
            activeforeground="#ffffff",
            relief="flat",
            font=("Consolas", 8, "bold"),
            padx=10,
            pady=4,
            cursor="hand2"
        )
        self.select_bot_btn.pack(pady=(0, 2))

        self.engine_status_lbl = tk.Label(
            right_frame,
            text="Rodent_IV\\rodent-iv-x64.exe not found",
            bg="#0a0a0a",
            fg="#ffaa00",
            font=("Consolas", 8),
            justify="center"
        )
        self.engine_status_lbl.pack(pady=(2, 6))

        diff_frame = tk.Frame(right_frame, bg="#111111", highlightthickness=1, highlightbackground="#222222")
        diff_frame.pack(fill="x", padx=12, pady=4)

        self.elo_value_lbl = tk.Label(
            diff_frame,
            text="Level: 1500 Elo (Intermediate)",
            bg="#111111",
            fg="#00d4ff",
            font=("Consolas", 9, "bold")
        )
        self.elo_value_lbl.pack(pady=(6, 0))

        self.elo_slider = tk.Scale(
            diff_frame,
            from_=800,
            to=2850,
            resolution=50,
            orient=tk.HORIZONTAL,
            variable=self.elo_var,
            command=self._on_elo_changed,
            bg="#111111",
            fg="#cccccc",
            troughcolor="#262626",
            highlightthickness=0,
            showvalue=False,
            sliderlength=16,
            length=360,
            cursor="hand2"
        )
        self.elo_slider.pack(padx=12, pady=(2, 2))

        self.elo_time_hint_lbl = tk.Label(
            diff_frame,
            text="Rank: 1500 Elo | Est: ~1.2s (cap 5s)",
            bg="#111111",
            fg="#9ca3af",
            font=("Consolas", 8)
        )
        self.elo_time_hint_lbl.pack(pady=(0, 6))

        self.chk_eval = tk.Checkbutton(
            right_frame,
            text="Position Evaluation Bar",
            variable=self.show_eval_var,
            command=self._on_toggle_eval_bar,
            bg="#0a0a0a",
            fg="#e5e7eb",
            selectcolor="#1f2937",
            activebackground="#0a0a0a",
            activeforeground="#ffffff",
            font=("Consolas", 9, "bold"),
            anchor="w",
            cursor="hand2"
        )
        self.chk_eval.pack(fill="x", padx=14, pady=(4, 0))

        self.eval_detail_lbl = tk.Label(
            right_frame,
            text="Evaluation: disabled",
            bg="#0a0a0a",
            fg="#777777",
            font=("Consolas", 8),
            anchor="w"
        )
        self.eval_detail_lbl.pack(fill="x", padx=34, pady=(0, 4))

        self.chk_top3 = tk.Checkbutton(
            right_frame,
            text=f"Top 3 Moves + Arrows (max {MAX_ANALYSIS_SECONDS:.0f}s cap)",
            variable=self.show_top3_var,
            command=self._on_toggle_top3,
            bg="#0a0a0a",
            fg="#e5e7eb",
            selectcolor="#1f2937",
            activebackground="#0a0a0a",
            activeforeground="#ffffff",
            font=("Consolas", 9, "bold"),
            anchor="w",
            cursor="hand2"
        )
        self.chk_top3.pack(fill="x", padx=14, pady=(2, 4))

        self.top3_frame = tk.Frame(
            right_frame,
            bg="#121212",
            highlightthickness=1,
            highlightbackground="#2a2a2a"
        )
        self.top3_frame.pack(fill="x", padx=12, pady=(0, 8))

        self.top3_meta_lbl = tk.Label(
            self.top3_frame,
            text="Rank: 1500 Elo | Time: -- (cap 5.0s)",
            bg="#18181b",
            fg="#60a5fa",
            font=("Consolas", 8, "bold"),
            anchor="w",
            padx=8,
            pady=3
        )
        self.top3_meta_lbl.pack(fill="x")

        self.side1_header_lbl = tk.Label(
            self.top3_frame,
            text="⚪ WHITE (to move):",
            bg="#121212",
            fg="#f8fafc",
            font=("Consolas", 8, "bold"),
            anchor="w"
        )
        self.side1_header_lbl.pack(fill="x", padx=8, pady=(6, 2))

        self.top3_text = tk.Text(
            self.top3_frame,
            height=4,
            bg="#121212",
            fg="#00ff66",
            relief="flat",
            bd=0,
            highlightthickness=0,
            font=("Consolas", 8),
            wrap="none",
            padx=10,
            pady=2,
            cursor="arrow"
        )
        self.top3_text.tag_configure("rank1", foreground="#f59e0b", font=("Consolas", 8, "bold"))
        self.top3_text.tag_configure("rank2", foreground="#38bdf8", font=("Consolas", 8, "bold"))
        self.top3_text.tag_configure("rank3", foreground="#c084fc", font=("Consolas", 8, "bold"))
        self.top3_text.tag_configure("move_text", foreground="#e5e7eb", font=("Consolas", 8))
        self.top3_text.tag_configure("info_text", foreground="#6b7280", font=("Consolas", 8))
        self.top3_text.tag_configure("warn_text", foreground="#fbbf24", font=("Consolas", 8))
        self.top3_text.tag_configure("err_text", foreground="#ff5555", font=("Consolas", 8))
        self.top3_text.pack(fill="x", pady=(0, 6))
        self._set_top3_message("Check box to calculate & show board arrows.", "info_text")

        # ================= COMPACT HISTORY NAVIGATION & MOVE VERDICT BOX =================
        sandbox_box = tk.Frame(
            right_frame,
            bg="#121212",
            highlightthickness=1,
            highlightbackground="#2e3b4e"
        )
        sandbox_box.pack(fill="x", padx=12, pady=(0, 8))

        nav_btn_row = tk.Frame(sandbox_box, bg="#121212")
        nav_btn_row.pack(fill="x", padx=8, pady=(8, 4))

        self.back_btn = tk.Button(
            nav_btn_row,
            text="◀ Backwards",
            command=self._step_backwards,
            bg="#1f2937",
            fg="#ffffff",
            activebackground="#374151",
            activeforeground="#ffffff",
            disabledforeground="#6b7280",
            relief="flat",
            font=("Consolas", 8, "bold"),
            padx=6,
            pady=5,
            cursor="hand2",
            state="disabled"
        )
        self.back_btn.pack(side=tk.LEFT, expand=True, fill="x", padx=(0, 3))

        self.forward_btn = tk.Button(
            nav_btn_row,
            text="Forwards ▶",
            command=self._step_forwards,
            bg="#1f2937",
            fg="#ffffff",
            activebackground="#374151",
            activeforeground="#ffffff",
            disabledforeground="#6b7280",
            relief="flat",
            font=("Consolas", 8, "bold"),
            padx=6,
            pady=5,
            cursor="hand2",
            state="disabled"
        )
        self.forward_btn.pack(side=tk.LEFT, expand=True, fill="x", padx=(3, 0))

        self.exit_try_btn = tk.Button(
            sandbox_box,
            text="↩ Back to Live Match",
            command=self._exit_sandbox_mode,
            bg="#374151",
            fg="#ffffff",
            activebackground="#4b5563",
            activeforeground="#ffffff",
            disabledforeground="#6b7280",
            relief="flat",
            font=("Consolas", 8, "bold"),
            padx=6,
            pady=4,
            cursor="hand2",
            state="disabled"
        )
        self.exit_try_btn.pack(fill="x", padx=8, pady=(0, 6))

        self.move_verdict_lbl = tk.Label(
            sandbox_box,
            text="Click any piece on the board to test a move,\nor use Backwards / Forwards to review history.",
            bg="#121212",
            fg="#9ca3af",
            font=("Consolas", 9),
            justify="left",
            anchor="nw",
            wraplength=385,
            height=3
        )
        self.move_verdict_lbl.pack(fill="x", padx=8, pady=(2, 8))

        # ================= PGN NOTATION BOX (DARK AUTO-HIDING SCROLLBAR) =================
        pgn_box = tk.Frame(
            right_frame,
            bg="#121212",
            highlightthickness=1,
            highlightbackground="#262626"
        )
        pgn_box.pack(fill="both", expand=True, padx=12, pady=(0, 10))

        pgn_header = tk.Label(
            pgn_box,
            text="PGN NOTATION:",
            bg="#18181b",
            fg="#9ca3af",
            font=("Consolas", 8, "bold"),
            anchor="w",
            padx=8,
            pady=3
        )
        pgn_header.pack(fill="x")

        pgn_body = tk.Frame(pgn_box, bg="#0d0d0d")
        pgn_body.pack(fill="both", expand=True, padx=6, pady=6)
        pgn_body.rowconfigure(0, weight=1)
        pgn_body.columnconfigure(0, weight=1)

        self.pgn_text = tk.Text(
            pgn_body,
            height=4,
            bg="#0d0d0d",
            fg="#00ff66",
            insertbackground="#ffffff",
            relief="flat",
            highlightthickness=0,
            font=("Consolas", 8),
            wrap="word",
            padx=4,
            pady=4,
        )
        self.pgn_text.grid(row=0, column=0, sticky="nsew")

        self.pgn_scroll = DarkAutoScrollbar(
            pgn_body,
            command=self.pgn_text.yview,
            width=7,
            bg="#0d0d0d",
            thumb_color="#2a2a2e",
            hover_color="#4b5563",
        )
        self.pgn_scroll.grid(row=0, column=1, sticky="ns", padx=(2, 0))
        self.pgn_scroll.grid_remove()

        self.pgn_text.config(yscrollcommand=self.pgn_scroll.set)

    def _clear_preview_canvases(self):
        for cv in self.preview_canvases:
            try:
                cv.destroy()
            except Exception:
                pass
        self.preview_canvases = []

    def _set_top3_message(self, msg, tag="info_text"):
        self.top3_text.config(state="normal")
        self._clear_preview_canvases()
        self.top3_text.delete("1.0", tk.END)
        self.top3_text.insert(tk.END, msg, tag)
        self.top3_text.config(state="disabled")

    def _set_top3_lines(self, lines):
        self.top3_text.config(state="normal")
        self._clear_preview_canvases()
        self.top3_text.delete("1.0", tk.END)

        mini_styles = {
            1: (ARROW_COLORS[1], 4.2, (7, 8, 4)),
            2: (ARROW_COLORS[2], 2.4, (6, 7, 3)),
            3: (ARROW_COLORS[3], 1.1, (5, 6, 2)),
        }

        for idx, (r, san, sc, ln, _, _) in enumerate(lines):
            if idx > 0:
                self.top3_text.insert(tk.END, "\n")
            self.top3_text.insert(tk.END, f"{r}. ", f"rank{r}")

            color, width, arrowshape = mini_styles.get(r, ("#ffffff", 2.0, (6, 7, 3)))
            mini_cv = tk.Canvas(
                self.top3_text,
                width=32,
                height=13,
                bg="#121212",
                highlightthickness=0,
                bd=0
            )
            mini_cv.create_line(
                2, 7, 30, 7,
                fill=color,
                width=width,
                arrow=tk.LAST,
                arrowshape=arrowshape,
                capstyle=tk.ROUND
            )
            self.preview_canvases.append(mini_cv)
            self.top3_text.window_create(tk.END, window=mini_cv, align="center")

            self.top3_text.insert(tk.END, f" {san} [{sc}] -> {ln}", "move_text")

        self.top3_text.config(state="disabled")

    # ================= ADAPTIVE CONTROLS LAYOUT & BOARD RESIZING =================
    def _apply_controls_layout(self, mode):
        if self.controls_layout_mode == mode:
            return
        self.controls_layout_mode = mode

        self.board_stage_frame.pack_forget()
        self.controls_frame.pack_forget()
        for w in (self.connect_btn, self.flip_btn, self.reset_btn, self.conn_badge, self.status_label, self.controls_inner):
            w.pack_forget()

        if mode == "side":
            panel_bg = "#0a0a0a"
            col_w = self.side_bar_width - 12  # 204px inner width + 12px right margin
            self.controls_frame.config(
                bg=panel_bg,
                width=col_w,
                highlightthickness=1,
                highlightbackground="#262626"
            )
            self.controls_frame.pack_propagate(False)
            self.controls_inner.config(bg=panel_bg)
            self.conn_badge.config(bg=panel_bg)
            self.status_label.config(bg=panel_bg, wraplength=col_w - 20, justify="center")

            self.controls_inner.pack(side=tk.TOP, fill="x", padx=10, pady=(12, 6))
            self.connect_btn.pack(side=tk.TOP, fill="x", pady=(0, 6))
            self.flip_btn.pack(side=tk.TOP, fill="x", pady=(0, 6))
            self.reset_btn.pack(side=tk.TOP, fill="x", pady=(0, 8))
            self.conn_badge.pack(side=tk.TOP, anchor="center", pady=(2, 2))
            self.status_label.pack(side=tk.TOP, fill="x", padx=10, pady=(4, 12))

            self.controls_frame.pack(side=tk.LEFT, fill="y", padx=(0, 12))
            self.board_stage_frame.pack(side=tk.LEFT, fill="both", expand=True)
        else:
            self.controls_frame.config(
                bg="#000000",
                width=0,
                highlightthickness=0
            )
            self.controls_frame.pack_propagate(True)
            self.controls_inner.config(bg="#000000")
            self.conn_badge.config(bg="#000000")
            self.status_label.config(bg="#000000", wraplength=0, justify="center")

            self.controls_inner.pack(side=tk.TOP, anchor="center")
            self.connect_btn.pack(side=tk.LEFT, padx=4)
            self.flip_btn.pack(side=tk.LEFT, padx=4)
            self.reset_btn.pack(side=tk.LEFT, padx=4)
            self.conn_badge.pack(side=tk.LEFT, padx=6)
            self.status_label.pack(side=tk.TOP, fill="x", pady=(4, 0))

            self.controls_frame.pack(side=tk.TOP, fill="x", pady=(0, 4))
            self.board_stage_frame.pack(side=tk.TOP, fill="both", expand=True)
            self.controls_frame.update_idletasks()
            req_h = self.controls_frame.winfo_reqheight()
            if req_h > 20:
                self.top_bar_height_est = req_h + 4

    def _recalculate_layout_and_board(self, left_w=None, left_h=None):
        if left_w is None:
            left_w = self.left_frame.winfo_width()
        if left_h is None:
            left_h = self.left_frame.winfo_height()

        if left_w <= 1 or left_h <= 1:
            return

        eval_space = (self.eval_bar_width + 10) if self.show_eval_var.get() else 0
        margin = 12

        size_top = max(260, min(left_w - eval_space - margin, left_h - self.top_bar_height_est - margin))
        size_side = max(260, min(left_w - self.side_bar_width - eval_space - margin, left_h - margin))

        # Switch to side column only when doing so genuinely makes the board larger
        if self.controls_layout_mode == "side":
            desired_mode = "side" if size_side >= size_top + 2 else "top"
        else:
            desired_mode = "side" if size_side >= size_top + 10 else "top"

        self._apply_controls_layout(desired_mode)
        new_size = size_side if desired_mode == "side" else size_top

        if abs(new_size - self.board_size) >= 2:
            self.board_size = new_size
            self.canvas.config(width=self.board_size, height=self.board_size)
            self.eval_canvas.config(height=self.board_size)
            self._draw_board()
            if self.show_eval_var.get():
                self._draw_eval_bar()

    def _on_left_frame_resize(self, event):
        if event.widget is self.left_frame:
            self._recalculate_layout_and_board(event.width, event.height)

    # ================= HISTORY NAVIGATION & SANDBOX LOGIC =================
    def _on_left_key(self, event):
        if isinstance(event.widget, (tk.Entry, tk.Text)):
            return
        self._step_backwards()

    def _on_right_key(self, event):
        if isinstance(event.widget, (tk.Entry, tk.Text)):
            return
        self._step_forwards()

    def _update_nav_buttons(self):
        can_back = (
            (self.sandbox_mode and len(self.sandbox_moves) > 0)
            or (not self.sandbox_mode and self.view_ply > 0 and len(self.match_moves) > 0)
        )
        can_forward = (not self.sandbox_mode) and (self.view_ply < len(self.match_moves))
        can_return_live = self.sandbox_mode or self.manual_history_nav

        self.back_btn.config(
            state="normal" if can_back else "disabled",
            bg="#2563eb" if can_back else "#1f2937"
        )
        self.forward_btn.config(
            state="normal" if can_forward else "disabled",
            bg="#2563eb" if can_forward else "#1f2937"
        )
        self.exit_try_btn.config(
            state="normal" if can_return_live else "disabled",
            bg="#dc2626" if can_return_live else "#374151"
        )

    def _rebuild_and_evaluate_current_view(self):
        b = chess.Board()
        base_limit = self.sandbox_base_ply if self.sandbox_mode else self.view_ply
        for mv in self.match_moves[:base_limit]:
            b.push(mv)
        if self.sandbox_mode:
            for mv in self.sandbox_moves:
                b.push(mv)

        self.board = b
        self.selected_square = None
        self.legal_targets_for_selected = set()
        self.top3_arrows = []

        self._draw_board()
        self._update_pgn_display()
        self._update_nav_buttons()

        status_txt, status_col = self._format_sync_status_text()
        self.status_label.config(text=status_txt, fg=status_col)
        self._request_engine_analysis()

    def _step_backwards(self):
        if self.sandbox_mode and len(self.sandbox_moves) > 0:
            self.sandbox_moves.pop()
            if len(self.sandbox_moves) == 0:
                self.sandbox_mode = False
                self.view_ply = self.sandbox_base_ply
                self.manual_history_nav = (self.view_ply != self.last_html_ply)
                self.move_verdict_lbl.config(
                    text="Unplayed test move discarded.\nReturned to match history.",
                    fg="#9ca3af"
                )
            else:
                self.move_verdict_lbl.config(
                    text=f"Test move discarded ({len(self.sandbox_moves)} test move(s) active).\nForwards disabled for unplayed moves.",
                    fg="#60a5fa"
                )
            self._rebuild_and_evaluate_current_view()
            return

        if not self.sandbox_mode and self.view_ply > 0 and len(self.match_moves) > 0:
            self.view_ply -= 1
            self.manual_history_nav = (self.view_ply != self.last_html_ply)
            self.move_verdict_lbl.config(
                text=f"Match history: move {self.view_ply}/{len(self.match_moves)}.\nClick any piece on the board to test an alternative.",
                fg="#9ca3af"
            )
            self._rebuild_and_evaluate_current_view()

    def _step_forwards(self):
        if self.sandbox_mode:
            return
        if self.view_ply < len(self.match_moves):
            self.view_ply += 1
            self.manual_history_nav = (self.view_ply != self.last_html_ply)
            self.move_verdict_lbl.config(
                text=f"Match history: move {self.view_ply}/{len(self.match_moves)}.\nClick any piece on the board to test an alternative.",
                fg="#9ca3af"
            )
            self._rebuild_and_evaluate_current_view()

    def _exit_sandbox_mode(self):
        self.analysis_generation += 1
        self.is_analyzing = False

        self.sandbox_mode = False
        self.sandbox_moves = []
        self.manual_history_nav = False
        self.selected_square = None
        self.legal_targets_for_selected = set()
        self.top3_arrows = []

        self.view_ply = self.last_html_ply
        if self.match_moves:
            b = chess.Board()
            for mv in self.match_moves[:self.view_ply]:
                b.push(mv)
            self.board = b
        else:
            self.board = chess.Board()

        self.move_verdict_lbl.config(
            text="Returned to live match.\nClick any piece to test a move.",
            fg="#9ca3af"
        )

        self._draw_board()
        self._update_pgn_display()
        self._update_nav_buttons()
        status_txt, status_col = self._format_sync_status_text()
        self.status_label.config(text=status_txt, fg=status_col)

        if self.last_dom_payload:
            self._on_html_board_update(self.last_dom_payload, force_analysis=True)
        else:
            self._request_engine_analysis()

    def _on_board_click(self, event):
        sq_dim = self.board_size / 8.0
        col = int(event.x // sq_dim)
        row = int(event.y // sq_dim)
        if not (0 <= col < 8 and 0 <= row < 8):
            return

        file_idx = 7 - col if self.flipped else col
        rank_idx = row if self.flipped else 7 - row
        clicked_sq = chess.square(file_idx, rank_idx)

        if self.selected_square is not None and clicked_sq in self.legal_targets_for_selected:
            move = chess.Move(self.selected_square, clicked_sq)
            piece = self.board.piece_at(self.selected_square)
            if piece and piece.piece_type == chess.PAWN and rank_idx in (0, 7):
                move = chess.Move(self.selected_square, clicked_sq, promotion=chess.QUEEN)

            if move in self.board.legal_moves:
                if not self.sandbox_mode:
                    self.sandbox_mode = True
                    self.sandbox_base_ply = self.view_ply
                    self.sandbox_moves = []

                board_before = self.board.copy(stack=False)
                san_move = board_before.san(move)
                self.board.push(move)
                self.sandbox_moves.append(move)
                board_after = self.board.copy(stack=False)

                self.selected_square = None
                self.legal_targets_for_selected = set()
                self.top3_arrows = []
                self._draw_board()
                self._update_pgn_display()
                self._update_nav_buttons()

                status_txt, status_col = self._format_sync_status_text()
                self.status_label.config(text=status_txt, fg=status_col)

                self._evaluate_tried_move(board_before, board_after, move, san_move)
                return

        piece = self.board.piece_at(clicked_sq)
        if piece and piece.color == self.board.turn:
            self.selected_square = clicked_sq
            self.legal_targets_for_selected = {
                m.to_square for m in self.board.legal_moves if m.from_square == clicked_sq
            }
        else:
            self.selected_square = None
            self.legal_targets_for_selected = set()

        self._draw_board()

    def _evaluate_tried_move(self, board_before, board_after, played_move, san_move):
        if not self._ensure_engine_ready():
            return

        self.analysis_generation += 1
        gen = self.analysis_generation
        prof = self._get_rank_profile()

        self.move_verdict_lbl.config(
            text=f"⏳ Analyzing {san_move} at {prof['rank_short']}...",
            fg="#fbbf24"
        )

        def worker():
            t0 = time.monotonic()
            mover_is_white = (board_before.turn == chess.WHITE)
            with self.engine_lock:
                if self.engine is None or self.analysis_generation != gen:
                    return
                try:
                    self._apply_rodent_difficulty_locked(force_max=True)

                    info_before = self.engine.analyse(
                        board_before,
                        chess.engine.Limit(time=0.55, depth=12)
                    )
                    best_pv = info_before.get("pv", [])
                    best_move = best_pv[0] if best_pv else None
                    best_san = board_before.san(best_move) if best_move else "-"

                    score_before_obj = info_before["score"].pov(mover_is_white)
                    cp_before = score_before_obj.score(mate_score=10000) / 100.0

                    if board_after.is_checkmate():
                        cp_after = 100.0
                    elif board_after.is_stalemate() or board_after.is_insufficient_material():
                        cp_after = 0.0
                    else:
                        info_after = self.engine.analyse(
                            board_after,
                            chess.engine.Limit(time=0.55, depth=12)
                        )
                        score_after_obj = info_after["score"].pov(mover_is_white)
                        cp_after = score_after_obj.score(mate_score=10000) / 100.0

                    self._apply_rodent_difficulty_locked(force_max=False)
                except Exception as e:
                    self.root.after(0, lambda: self.move_verdict_lbl.config(
                        text=f"Evaluation error: {e}", fg="#ff5555"
                    ))
                    return

            if self.analysis_generation != gen:
                return

            elapsed = time.monotonic() - t0
            loss = max(0.0, cp_before - cp_after)
            is_top_choice = (best_move == played_move)

            if is_top_choice or loss <= 0.15:
                verdict = f"🌟 {san_move}: BEST MOVE!"
                color = "#00ff66"
                detail = f"Eval: {cp_after:+.2f} | Time: {elapsed:.1f}s"
            elif loss <= 0.35:
                verdict = f"✅ {san_move}: Excellent move!"
                color = "#4ade80"
                detail = f"Diff: -{loss:.2f} | Best: {best_san} ({elapsed:.1f}s)"
            elif loss <= 0.75:
                verdict = f"👍 {san_move}: Good move."
                color = "#a3e635"
                detail = f"Diff: -{loss:.2f} | Better: {best_san} ({elapsed:.1f}s)"
            elif loss <= 1.50:
                verdict = f"⚠️ {san_move}: Inaccuracy!"
                color = "#fbbf24"
                detail = f"Loss: -{loss:.2f} | Better: {best_san} ({elapsed:.1f}s)"
            elif loss <= 3.00:
                verdict = f"❌ {san_move}: Mistake!"
                color = "#fb923c"
                detail = f"Loss: -{loss:.2f} | Best was: {best_san} ({elapsed:.1f}s)"
            else:
                verdict = f"💥 {san_move}: BLUNDER!"
                color = "#ef4444"
                detail = f"Loss: -{loss:.2f} | Best was: {best_san} ({elapsed:.1f}s)"

            def finish_verdict():
                if self.analysis_generation != gen:
                    return
                self.move_verdict_lbl.config(text=f"{verdict}\n{detail}", fg=color)
                self._request_engine_analysis()

            self.root.after(0, finish_verdict)

        threading.Thread(target=worker, daemon=True).start()

    # ================= DISTINCT TOP 3 MOVES ALGORITHM =================
    def _rank_candidate_moves(self, board_obj, exclude_move=None):
        scored = []
        for mv in board_obj.legal_moves:
            if exclude_move is not None and mv == exclude_move:
                continue
            priority = 0
            if board_obj.is_capture(mv):
                priority += 40
            if mv.promotion:
                priority += 50
            if board_obj.gives_check(mv):
                priority += 35
            if board_obj.is_castling(mv):
                priority += 30
            to_file = chess.square_file(mv.to_square)
            to_rank = chess.square_rank(mv.to_square)
            if 2 <= to_file <= 5 and 2 <= to_rank <= 5:
                priority += 15
            piece = board_obj.piece_at(mv.from_square)
            if piece and piece.piece_type in (chess.KNIGHT, chess.BISHOP):
                priority += 10
            scored.append((priority, mv))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [mv for _, mv in scored]

    def _format_score_white(self, score_obj):
        white_score = score_obj.white()
        if white_score.is_mate():
            mate_in = white_score.mate()
            eval_str = f"#M{mate_in}"
            eval_cp = 10.0 if mate_in > 0 else -10.0
            sort_cp = 100000 - abs(mate_in) if mate_in > 0 else -100000 + abs(mate_in)
        else:
            raw_cp = white_score.score(mate_score=10000)
            cp = raw_cp / 100.0
            eval_str = f"{cp:+.1f}"
            eval_cp = cp
            sort_cp = raw_cp
        return eval_str, eval_cp, sort_cp

    def _compute_top3_distinct_locked(
        self, board_obj, gen, t_start, primary_t, refine_t, screen_t, max_cand, max_depth
    ):
        legal_moves = list(board_obj.legal_moves)
        if not legal_moves:
            return [], 0

        mover_is_white = (board_obj.turn == chess.WHITE)
        max_depth_reached = 0
        results = []

        rem = MAX_ANALYSIS_SECONDS - (time.monotonic() - t_start) - 0.15
        if rem <= 0.15 or self.analysis_generation != gen:
            return [], 0

        t1 = min(primary_t, max(0.15, rem))
        info1 = self.engine.analyse(board_obj, chess.engine.Limit(time=t1, depth=max_depth))
        pv1 = info1.get("pv", [])
        if not pv1 or "score" not in info1:
            return [], 0

        best_mv1 = pv1[0]
        max_depth_reached = max(max_depth_reached, info1.get("depth", 0))
        eval_str1, eval_cp1, _ = self._format_score_white(info1["score"])

        temp_b = board_obj.copy(stack=False)
        line1_sans = []
        for m in pv1[:3]:
            line1_sans.append(temp_b.san(m))
            temp_b.push(m)
        results.append((1, board_obj.san(best_mv1), eval_str1, " ".join(line1_sans), eval_cp1, best_mv1))

        if len(legal_moves) == 1:
            return results, max_depth_reached

        candidates = self._rank_candidate_moves(board_obj, exclude_move=best_mv1)[:max_cand]
        screened = []

        for mv in candidates:
            if self.analysis_generation != gen:
                return results, max_depth_reached
            rem = MAX_ANALYSIS_SECONDS - (time.monotonic() - t_start) - 0.25
            if rem <= 0.20:
                break

            b_child = board_obj.copy(stack=False)
            b_child.push(mv)
            if b_child.is_checkmate():
                screened.append((100000, mv, []))
                continue

            st = min(screen_t, max(0.03, rem))
            info_c = self.engine.analyse(b_child, chess.engine.Limit(time=st, depth=min(6, max_depth)))
            if "score" in info_c:
                pov_sc = info_c["score"].pov(mover_is_white).score(mate_score=10000)
                screened.append((pov_sc, mv, info_c.get("pv", [])))

        screened.sort(key=lambda item: item[0], reverse=True)

        for _, mv_alt, fallback_pv in screened[:2]:
            if self.analysis_generation != gen:
                return results, max_depth_reached
            rem = MAX_ANALYSIS_SECONDS - (time.monotonic() - t_start) - 0.15
            if rem <= 0.15:
                break

            b_child = board_obj.copy(stack=False)
            b_child.push(mv_alt)
            san_alt = board_obj.san(mv_alt)

            if b_child.is_checkmate():
                mate_str = "#M1" if mover_is_white else "#M-1"
                mate_cp = 10.0 if mover_is_white else -10.0
                results.append((len(results) + 1, san_alt, mate_str, san_alt, mate_cp, mv_alt))
                continue

            rt = min(refine_t, max(0.15, rem))
            info_r = self.engine.analyse(
                b_child,
                chess.engine.Limit(time=rt, depth=max(6, max_depth - 1))
            )
            max_depth_reached = max(max_depth_reached, info_r.get("depth", 0))
            if "score" in info_r:
                ev_str, ev_cp, _ = self._format_score_white(info_r["score"])
                pv_r = info_r.get("pv", fallback_pv)
                line_sans = [san_alt]
                temp_b = b_child.copy(stack=False)
                for m in pv_r[:2]:
                    line_sans.append(temp_b.san(m))
                    temp_b.push(m)
                results.append((len(results) + 1, san_alt, ev_str, " ".join(line_sans), ev_cp, mv_alt))

        return results, max_depth_reached

    # ================= EVALUATION & TOP 3 (5S CAP) =================
    def _on_toggle_eval_bar(self):
        if self.show_eval_var.get():
            if not self._ensure_engine_ready():
                self.show_eval_var.set(False)
                return
            self.eval_canvas.pack(side=tk.LEFT, padx=(8, 0))
            self._recalculate_layout_and_board()
            self._draw_eval_bar()
            self._request_engine_analysis()
        else:
            self.eval_canvas.pack_forget()
            self._recalculate_layout_and_board()
            self.eval_detail_lbl.config(text="Evaluation: disabled", fg="#777777")

    def _on_toggle_top3(self):
        if self.show_top3_var.get():
            if not self._ensure_engine_ready():
                self.show_top3_var.set(False)
                return
            self._request_engine_analysis()
        else:
            self.top3_arrows = []
            self._draw_board()
            self.top3_meta_lbl.config(
                text=f"Rank: {self._get_rank_profile()['rank_short']} | Time: -- (cap {MAX_ANALYSIS_SECONDS:.0f}s)",
                fg="#60a5fa"
            )
            self._set_top3_message("Check box to calculate & show board arrows.", "info_text")

    def _ensure_engine_ready(self):
        if self.engine is not None:
            return True
        found = self._auto_find_rodent()
        if found:
            self._init_rodent(found)
            return self.engine is not None

        messagebox.showinfo(
            "Rodent IV Missing",
            "Could not automatically find rodent-iv-x64.exe in the Rodent_IV folder.\n"
            "Please select it manually."
        )
        self._select_rodent_dialog()
        return self.engine is not None

    def _draw_eval_bar(self):
        self.eval_canvas.delete("all")
        w = self.eval_bar_width
        h = self.board_size

        clamped = max(-10.0, min(10.0, self.current_eval_cp))
        white_ratio = 1.0 / (1.0 + np.exp(-0.45 * clamped))
        white_ratio = max(0.05, min(0.95, white_ratio))

        white_h = int(h * white_ratio)
        black_h = h - white_h

        self.eval_canvas.create_rectangle(0, 0, w, black_h, fill="#262626", outline="")
        self.eval_canvas.create_rectangle(0, black_h, w, h, fill="#f3f4f6", outline="")
        self.eval_canvas.create_line(0, h // 2, w, h // 2, fill="#ef4444", width=1)

        if self.current_eval_cp >= 0:
            self.eval_canvas.create_text(
                w // 2, h - 14,
                text=self.current_eval_text,
                font=("Consolas", 8, "bold"),
                fill="#111111"
            )
        else:
            self.eval_canvas.create_text(
                w // 2, 14,
                text=self.current_eval_text,
                font=("Consolas", 8, "bold"),
                fill="#ffffff"
            )

    def _request_engine_analysis(self):
        if self.engine is None:
            return
        if not (self.show_eval_var.get() or self.show_top3_var.get()):
            return
        if not self.board.is_valid():
            if self.show_top3_var.get():
                self._set_top3_message("Invalid board position.", "err_text")
            return

        self.analysis_generation += 1
        gen = self.analysis_generation
        self.is_analyzing = True

        board_snapshot = self.board.copy(stack=False)
        fen_snapshot = board_snapshot.fen()
        want_top3 = self.show_top3_var.get()
        prof = self._get_rank_profile()
        est_sec = prof["est_top3"] if want_top3 else prof["est_eval"]
        t_start = time.monotonic()

        active_is_white = (board_snapshot.turn == chess.WHITE)
        if active_is_white:
            self.side1_header_lbl.config(text="⚪ WHITE (to move):", fg="#f8fafc")
        else:
            self.side1_header_lbl.config(text="⚫ BLACK (to move):", fg="#fbbf24")

        if want_top3:
            self.top3_meta_lbl.config(
                text=f"⏳ {prof['rank_short']} | 0.0s / cap {MAX_ANALYSIS_SECONDS:.0f}s (est. ~{est_sec:.1f}s)",
                fg="#fbbf24"
            )
            self._set_top3_message("Calculating top 3 moves...", "warn_text")

        if self.show_eval_var.get():
            self.eval_detail_lbl.config(
                text=f"Evaluating ({prof['rank_short']}): calculating...",
                fg="#fbbf24"
            )

        def tick_timer():
            if not self.is_analyzing or self.analysis_generation != gen:
                return
            elapsed = time.monotonic() - t_start
            if want_top3:
                self.top3_meta_lbl.config(
                    text=f"⏳ {prof['rank_short']} | {elapsed:.1f}s / cap {MAX_ANALYSIS_SECONDS:.0f}s (est. ~{est_sec:.1f}s)",
                    fg="#fbbf24"
                )
            self.root.after(200, tick_timer)

        self.root.after(200, tick_timer)

        threading.Thread(
            target=self._run_engine_worker,
            args=(board_snapshot, fen_snapshot, want_top3, gen, prof, t_start),
            daemon=True
        ).start()

    def _run_engine_worker(self, board_snapshot, fen_snapshot, want_top3, gen, prof, t_start):
        side1_lines = []
        best_eval_cp = 0.0
        best_eval_str = "0.0"
        max_reached_depth = 0
        error_msg = None

        with self.engine_lock:
            if self.engine is None or self.analysis_generation != gen:
                return
            try:
                self._apply_rodent_difficulty_locked(force_max=False)
                legal_moves = list(board_snapshot.legal_moves)

                if not legal_moves:
                    side1_lines = []
                elif not want_top3:
                    res = self.engine.analyse(
                        board_snapshot,
                        chess.engine.Limit(time=prof["primary_time"], depth=prof["max_depth"])
                    )
                    if "score" in res:
                        best_eval_str, best_eval_cp, _ = self._format_score_white(res["score"])
                        max_reached_depth = res.get("depth", 0)
                else:
                    side1_lines, d1 = self._compute_top3_distinct_locked(
                        board_snapshot,
                        gen=gen,
                        t_start=t_start,
                        primary_t=prof["primary_time"],
                        refine_t=prof["refine_time"],
                        screen_t=prof["screen_time"],
                        max_cand=prof["max_candidates"],
                        max_depth=prof["max_depth"],
                    )
                    max_reached_depth = max(max_reached_depth, d1)

                    if side1_lines:
                        best_eval_str = side1_lines[0][2]
                        best_eval_cp = side1_lines[0][4]
            except Exception as e:
                error_msg = str(e)

        total_elapsed = time.monotonic() - t_start

        def update_ui():
            if self.analysis_generation != gen or self.board.fen() != fen_snapshot:
                return

            self.is_analyzing = False

            if error_msg:
                self.top3_arrows = []
                self._draw_board()
                self.top3_meta_lbl.config(text=f"Error | {total_elapsed:.1f}s", fg="#ff5555")
                self._set_top3_message(f"Rodent IV error: {error_msg}", "err_text")
                return

            self.current_eval_cp = best_eval_cp
            self.current_eval_text = best_eval_str
            depth_tag = f" | d{max_reached_depth}" if max_reached_depth > 0 else ""

            if self.show_eval_var.get():
                self._draw_eval_bar()
                who = "White" if best_eval_cp > 0.2 else ("Black" if best_eval_cp < -0.2 else "Equal")
                self.eval_detail_lbl.config(
                    text=f"Score: {best_eval_str} ({who}) [{prof['rank_short']}, {total_elapsed:.1f}s]",
                    fg="#00ff66"
                )

            if self.show_top3_var.get():
                self.top3_meta_lbl.config(
                    text=f"✓ {prof['rank_short']} | {total_elapsed:.1f}s / {MAX_ANALYSIS_SECONDS:.0f}s{depth_tag}",
                    fg="#00d4ff"
                )

                active_is_white = (board_snapshot.turn == chess.WHITE)
                if active_is_white:
                    self.side1_header_lbl.config(text="⚪ WHITE (to move):", fg="#f8fafc")
                else:
                    self.side1_header_lbl.config(text="⚫ BLACK (to move):", fg="#fbbf24")

                if not side1_lines:
                    self.top3_arrows = []
                    self._set_top3_message("No legal moves available.", "info_text")
                else:
                    self.top3_arrows = [
                        (r, mv_obj) for r, _, _, _, _, mv_obj in side1_lines if mv_obj is not None
                    ]
                    self._set_top3_lines(side1_lines)

                self._draw_board()

        self.root.after(0, update_ui)

    # ================= BOARD DRAWING (COORDINATES + ARROWS) & PGN =================
    def _toggle_flip(self):
        self.flipped = not self.flipped
        self._draw_board()

    def _reset_game(self):
        self.analysis_generation += 1
        self.is_analyzing = False
        self.sandbox_mode = False
        self.sandbox_moves = []
        self.sandbox_base_ply = 0
        self.manual_history_nav = False
        self.selected_square = None
        self.legal_targets_for_selected = set()
        self.top3_arrows = []
        self.known_san_sequence = []
        self.match_moves = []
        self.last_html_ply = 0
        self.view_ply = 0

        self.board = chess.Board()
        self.last_html_board_fen = self.board.board_fen()
        self._draw_board()
        self._update_pgn_display()
        self._update_nav_buttons()
        self._request_engine_analysis()

    def _square_to_canvas_center(self, square):
        file_idx = chess.square_file(square)
        rank_idx = chess.square_rank(square)
        col = 7 - file_idx if self.flipped else file_idx
        row = rank_idx if self.flipped else 7 - rank_idx
        sq = self.board_size / 8.0
        return (col + 0.5) * sq, (row + 0.5) * sq

    def _draw_move_arrows(self):
        if not self.show_top3_var.get() or not self.top3_arrows:
            return

        sq = self.board_size / 8.0

        style_map = {
            1: (
                ARROW_COLORS[1],
                max(8, round(sq * 0.21)),
                (round(sq * 0.33), round(sq * 0.37), round(sq * 0.21)),
            ),
            2: (
                ARROW_COLORS[2],
                max(5, round(sq * 0.12)),
                (round(sq * 0.24), round(sq * 0.27), round(sq * 0.14)),
            ),
            3: (
                ARROW_COLORS[3],
                max(2, round(sq * 0.055)),
                (round(sq * 0.16), round(sq * 0.19), round(sq * 0.09)),
            ),
        }

        for rank_num, move in sorted(self.top3_arrows, key=lambda item: item[0], reverse=True):
            if rank_num not in style_map:
                continue
            color, width, arrow_shape = style_map[rank_num]
            x1, y1 = self._square_to_canvas_center(move.from_square)
            x2, y2 = self._square_to_canvas_center(move.to_square)

            dx = x2 - x1
            dy = y2 - y1
            dist = math.hypot(dx, dy)
            if dist < 1e-3:
                continue

            ux = dx / dist
            uy = dy / dist
            start_pad = sq * 0.16
            end_pad = sq * 0.12

            sx = x1 + ux * start_pad
            sy = y1 + uy * start_pad
            ex = x2 - ux * end_pad
            ey = y2 - uy * end_pad

            self.canvas.create_line(
                sx, sy, ex, ey,
                fill=color,
                width=width,
                arrow=tk.LAST,
                arrowshape=arrow_shape,
                capstyle=tk.ROUND
            )

    def _draw_board(self):
        self.canvas.delete("all")
        light_color = "#ebecd0"
        dark_color = "#779556"

        sq = self.board_size / 8.0
        font_px = max(16, int(sq * 0.62))
        coord_px = max(8, int(sq * 0.18))
        coord_pad = max(3, int(sq * 0.06))
        dot_r = max(5, int(sq * 0.16))

        for row in range(8):
            for col in range(8):
                x1 = round(col * sq)
                y1 = round(row * sq)
                x2 = round((col + 1) * sq)
                y2 = round((row + 1) * sq)
                cx = (x1 + x2) // 2
                cy = (y1 + y2) // 2

                file_idx = 7 - col if self.flipped else col
                rank_idx = row if self.flipped else 7 - row
                square = chess.square(file_idx, rank_idx)

                is_light = ((row + col) % 2 == 0)
                if square == self.selected_square:
                    color = "#f6f669"
                    coord_fg = dark_color
                else:
                    color = light_color if is_light else dark_color
                    coord_fg = dark_color if is_light else light_color

                self.canvas.create_rectangle(x1, y1, x2, y2, fill=color, outline="")

                # Rank numbers (1-8) along the left edge
                if col == 0:
                    self.canvas.create_text(
                        x1 + coord_pad,
                        y1 + coord_pad,
                        text=str(rank_idx + 1),
                        anchor="nw",
                        font=("Consolas", coord_px, "bold"),
                        fill=coord_fg
                    )

                # File letters (a-h) along the bottom edge
                if row == 7:
                    self.canvas.create_text(
                        x2 - coord_pad,
                        y2 - coord_pad,
                        text=chr(ord('a') + file_idx),
                        anchor="se",
                        font=("Consolas", coord_px, "bold"),
                        fill=coord_fg
                    )

                if square in self.legal_targets_for_selected:
                    self.canvas.create_oval(
                        cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r,
                        fill="#2563eb", outline=""
                    )

                piece = self.board.piece_at(square)
                if piece:
                    symbol = PIECE_SYMBOLS[piece.symbol()]
                    fg_color = "#ffffff" if piece.color == chess.WHITE else "#111111"
                    if piece.color == chess.WHITE:
                        self.canvas.create_text(
                            cx + 1,
                            cy + 1,
                            text=symbol,
                            font=("Segoe UI Symbol", font_px),
                            fill="#222222"
                        )
                    self.canvas.create_text(
                        cx,
                        cy,
                        text=symbol,
                        font=("Segoe UI Symbol", font_px),
                        fill=fg_color
                    )

        self._draw_move_arrows()

    def _update_pgn_display(self):
        game = chess.pgn.Game.from_board(self.board)
        exporter = chess.pgn.StringExporter(headers=False, variations=False, comments=False)
        pgn_str = game.accept(exporter).strip()
        if not pgn_str or pgn_str == "*":
            turn_str = "White" if self.board.turn == chess.WHITE else "Black"
            pgn_str = f"Starting position ({turn_str} to move). Waiting for moves..."

        self.pgn_text.config(state="normal")
        self.pgn_text.delete("1.0", tk.END)
        self.pgn_text.insert(tk.END, pgn_str)
        self.pgn_text.see(tk.END)
        self.pgn_text.config(state="disabled")
        self.root.after_idle(lambda: self.pgn_scroll.set(*self.pgn_text.yview()))

    def _on_close(self):
        self.analysis_generation += 1
        if self.http_server:
            try:
                self.http_server.shutdown()
            except Exception:
                pass
        if self.engine:
            try:
                self.engine.quit()
            except Exception:
                pass
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = ChessScreenApp(root)
    root.mainloop()
