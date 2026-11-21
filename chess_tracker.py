import os
import re
import glob
import json
import time
import math
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import tkinter as tk
from tkinter import messagebox, filedialog, ttk
import numpy as np
import chess
import chess.pgn
import chess.engine

try:
    import chess.polyglot
    HAS_POLYGLOT = True
except Exception:
    HAS_POLYGLOT = False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EXT_DIR = os.path.join(BASE_DIR, "chess_extension")
BRIDGE_PORT = 8765
DEFAULT_PRESET_NAME = "🧠 Tactical / Advanced (2000 Elo • 3.0s)"
DEFAULT_MAX_TIME_SECONDS = 3.0
ENGINE_HASH_MB = 256
ENGINE_THREADS = 2

# Predefined Elo + Time + Depth Cap presets (clean alpha-beta evaluation without random eval_blur)
ANALYSIS_PRESETS = {
    "⚡ Blitz / Beginner (1000 Elo • 0.5s)": {
        "elo": 1000,
        "time": 0.5,
        "max_depth": 4,
        "tag": "Beginner • d4",
    },
    "🎯 Casual / Club (1350 Elo • 1.0s)": {
        "elo": 1350,
        "time": 1.0,
        "max_depth": 6,
        "tag": "Club • d6",
    },
    "⚖️ Balanced / Intermediate (1650 Elo • 2.0s)": {
        "elo": 1650,
        "time": 2.0,
        "max_depth": 9,
        "tag": "Intermediate • d9",
    },
    "🧠 Tactical / Advanced (2000 Elo • 3.0s)": {
        "elo": 2000,
        "time": 3.0,
        "max_depth": 12,
        "tag": "Advanced • d12",
    },
    "🏆 Master / Accurate (2400 Elo • 5.0s)": {
        "elo": 2400,
        "time": 5.0,
        "max_depth": 16,
        "tag": "Master • d16",
    },
    "👑 Grandmaster / Deep (2700 Elo • 7.5s)": {
        "elo": 2700,
        "time": 7.5,
        "max_depth": 20,
        "tag": "GM • d20",
    },
    "🔥 MAX Engine / Full Power (~2975 • 10.0s)": {
        "elo": 2850,
        "time": 10.0,
        "max_depth": None,
        "tag": "MAX • Full Depth",
    },
}

CUSTOM_PRESET_LABEL = "🛠 Custom (Manual Elo & Time)"

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

UNICODE_FIGURINE_TRANSLATION = str.maketrans({
    "♙": "", "♟": "",
    "♘": "N", "♞": "N",
    "♗": "B", "♝": "B",
    "♖": "R", "♜": "R",
    "♕": "Q", "♛": "Q",
    "♔": "K", "♚": "K",
})

# Engine Top 3 Arrow Colors
ARROW_COLORS = {
    1: "#f59e0b",  # Rank 1 (thickest) - Amber/Gold
    2: "#38bdf8",  # Rank 2 (medium)   - Sky Blue
    3: "#c084fc",  # Rank 3 (thin)     - Purple
}

# Book Moves Arrow Colors (Rank 1..N)
BOOK_ARROW_PALETTE = [
    "#10b981",  # #1 main book move - Emerald Green
    "#38bdf8",  # #2 book move      - Sky Blue
    "#818cf8",  # #3 book move      - Indigo
    "#2dd4bf",  # #4 book move      - Teal
    "#a78bfa",  # #5 book move      - Soft Violet
    "#94a3b8",  # #6+ book moves    - Slate Cyan
]

# ECO Opening Encyclopedia (A00 - E99) for Chess.com-style opening banner
ECO_OPENING_LINES = [
    ("A00", "Uncommon Opening", ""),
    ("A00", "Polish Opening (Orangutan)", "1. b4"),
    ("A00", "Polish Opening: Outflank Variation", "1. b4 c6"),
    ("A00", "Grob's Attack", "1. g4"),
    ("A00", "Larsen's Opening", "1. b3"),
    ("A00", "Dunst Opening", "1. Nc3"),
    ("A00", "Saragossa Opening", "1. c3"),
    ("A00", "Mieses Opening", "1. d3"),
    ("A00", "Van't Kruijs Opening", "1. e3"),
    ("A00", "Barnes Opening", "1. f3"),
    ("A00", "Anderssen's Opening", "1. a3"),
    ("A01", "Nimzowitsch-Larsen Attack", "1. b3 e5 2. Bb2 Nc6"),
    ("A02", "Bird's Opening", "1. f4"),
    ("A03", "Bird's Opening: Dutch Variation", "1. f4 d5"),
    ("A04", "Zukertort Opening", "1. Nf3"),
    ("A05", "Zukertort Opening: Symmetric", "1. Nf3 Nf6"),
    ("A06", "Zukertort Opening: Tennison / Santasiere", "1. Nf3 d5"),
    ("A07", "King's Indian Attack", "1. Nf3 d5 2. g3"),
    ("A09", "Réti Opening", "1. Nf3 d5 2. c4"),
    ("A10", "English Opening", "1. c4"),
    ("A13", "English Opening: Agincourt Defense", "1. c4 e6"),
    ("A15", "English Opening: Anglo-Indian Defense", "1. c4 Nf6"),
    ("A16", "English Opening: Anglo-Grünfeld", "1. c4 Nf6 2. Nc3 d5"),
    ("A20", "English Opening: Reversed Sicilian", "1. c4 e5"),
    ("A21", "English Opening: Reversed Sicilian", "1. c4 e5 2. Nc3"),
    ("A22", "English Opening: Bremen System", "1. c4 e5 2. Nc3 Nf6"),
    ("A25", "English Opening: Sicilian Reversed", "1. c4 e5 2. Nc3 Nc6"),
    ("A30", "English Opening: Symmetrical Variation", "1. c4 c5"),
    ("A34", "English Opening: Symmetrical, Three Knights", "1. c4 c5 2. Nc3 Nf6 3. Nf3"),
    ("A40", "Queen's Pawn Game", "1. d4"),
    ("A40", "Queen's Pawn: Horwitz Defense", "1. d4 e6"),
    ("A40", "Modern Defense", "1. d4 g6"),
    ("A41", "Queen's Pawn: Wade Defense", "1. d4 d6"),
    ("A43", "Old Benoni Defense", "1. d4 c5"),
    ("A45", "Indian Defense", "1. d4 Nf6"),
    ("A45", "Trompowsky Attack", "1. d4 Nf6 2. Bg5"),
    ("A46", "London System / Torre Attack", "1. d4 Nf6 2. Nf3"),
    ("A48", "London System: East Indian", "1. d4 Nf6 2. Nf3 g6 3. Bf4"),
    ("A50", "Indian Defense: Normal Variation", "1. d4 Nf6 2. c4"),
    ("A51", "Budapest Gambit", "1. d4 Nf6 2. c4 e5"),
    ("A52", "Budapest Gambit: Accepted", "1. d4 Nf6 2. c4 e5 3. dxe5 Ng4"),
    ("A53", "Old Indian Defense", "1. d4 Nf6 2. c4 d6"),
    ("A56", "Benoni Defense", "1. d4 Nf6 2. c4 c5 3. d5"),
    ("A57", "Benko Gambit", "1. d4 Nf6 2. c4 c5 3. d5 b5"),
    ("A60", "Modern Benoni", "1. d4 Nf6 2. c4 c5 3. d5 e6 4. Nc3 exd5 5. cxd5 d6"),
    ("A80", "Dutch Defense", "1. d4 f5"),
    ("A84", "Dutch Defense: Classical", "1. d4 f5 2. c4 e6"),
    ("A87", "Dutch Defense: Leningrad Variation", "1. d4 f5 2. c4 Nf6 3. g3 g6"),
    ("B00", "King's Pawn Game", "1. e4"),
    ("B00", "Nimzowitsch Defense", "1. e4 Nc6"),
    ("B00", "Owen's Defense", "1. e4 b6"),
    ("B00", "St. George Defense", "1. e4 a6"),
    ("B01", "Scandinavian Defense", "1. e4 d5"),
    ("B01", "Scandinavian Defense: Mieses-Kotroc Variation", "1. e4 d5 2. exd5 Qxd5"),
    ("B01", "Scandinavian Defense: Modern Variation", "1. e4 d5 2. exd5 Nf6"),
    ("B01", "Scandinavian Defense: Classical Variation", "1. e4 d5 2. exd5 Nf6 3. Nf3 Qxd5 4. Nc3 Qa5"),
    ("B01", "Scandinavian Defense: Main Line", "1. e4 d5 2. exd5 Qxd5 3. Nc3 Qa5"),
    ("B02", "Alekhine's Defense", "1. e4 Nf6"),
    ("B03", "Alekhine's Defense: Four Pawns / Exchange", "1. e4 Nf6 2. e5 Nd5 3. d4 d6"),
    ("B06", "Modern Defense (Robatsch)", "1. e4 g6"),
    ("B07", "Pirc Defense", "1. e4 d6 2. d4 Nf6 3. Nc3"),
    ("B09", "Pirc Defense: Austrian Attack", "1. e4 d6 2. d4 Nf6 3. Nc3 g6 4. f4"),
    ("B10", "Caro-Kann Defense", "1. e4 c6"),
    ("B12", "Caro-Kann Defense: Advance Variation", "1. e4 c6 2. d4 d5 3. e5"),
    ("B13", "Caro-Kann Defense: Exchange Variation", "1. e4 c6 2. d4 d5 3. exd5 cxd5"),
    ("B14", "Caro-Kann Defense: Panov-Botvinnik Attack", "1. e4 c6 2. d4 d5 3. exd5 cxd5 4. c4"),
    ("B15", "Caro-Kann Defense: Main Line", "1. e4 c6 2. d4 d5 3. Nc3"),
    ("B18", "Caro-Kann Defense: Classical Variation", "1. e4 c6 2. d4 d5 3. Nc3 dxe4 4. Nxe4 Bf5"),
    ("B20", "Sicilian Defense", "1. e4 c5"),
    ("B21", "Sicilian Defense: Smith-Morra Gambit / McDonnell", "1. e4 c5 2. d4 cxd4 3. c3"),
    ("B22", "Sicilian Defense: Alapin Variation", "1. e4 c5 2. c3"),
    ("B23", "Sicilian Defense: Closed", "1. e4 c5 2. Nc3"),
    ("B27", "Sicilian Defense: Hyperaccelerated Dragon", "1. e4 c5 2. Nf3 g6"),
    ("B30", "Sicilian Defense: Old Sicilian / Rossolimo", "1. e4 c5 2. Nf3 Nc6"),
    ("B31", "Sicilian Defense: Rossolimo Variation", "1. e4 c5 2. Nf3 Nc6 3. Bb5"),
    ("B32", "Sicilian Defense: Open", "1. e4 c5 2. Nf3 Nc6 3. d4 cxd4 4. Nxd4"),
    ("B33", "Sicilian Defense: Sveshnikov / Lasker-Pelikan", "1. e4 c5 2. Nf3 Nc6 3. d4 cxd4 4. Nxd4 Nf6 5. Nc3 e5"),
    ("B35", "Sicilian Defense: Accelerated Dragon", "1. e4 c5 2. Nf3 Nc6 3. d4 cxd4 4. Nxd4 g6 5. Nc3 Bg7"),
    ("B40", "Sicilian Defense: French Variation", "1. e4 c5 2. Nf3 e6"),
    ("B41", "Sicilian Defense: Kan Variation", "1. e4 c5 2. Nf3 e6 3. d4 cxd4 4. Nxd4 a6"),
    ("B44", "Sicilian Defense: Taimanov Variation", "1. e4 c5 2. Nf3 e6 3. d4 cxd4 4. Nxd4 Nc6"),
    ("B50", "Sicilian Defense: Modern Variations", "1. e4 c5 2. Nf3 d6"),
    ("B52", "Sicilian Defense: Canal-Sokolsky Attack", "1. e4 c5 2. Nf3 d6 3. Bb5+"),
    ("B54", "Sicilian Defense: Open", "1. e4 c5 2. Nf3 d6 3. d4 cxd4 4. Nxd4"),
    ("B56", "Sicilian Defense: Classical", "1. e4 c5 2. Nf3 d6 3. d4 cxd4 4. Nxd4 Nf6 5. Nc3"),
    ("B60", "Sicilian Defense: Richter-Rauzer", "1. e4 c5 2. Nf3 d6 3. d4 cxd4 4. Nxd4 Nf6 5. Nc3 Nc6 6. Bg5"),
    ("B70", "Sicilian Defense: Dragon Variation", "1. e4 c5 2. Nf3 d6 3. d4 cxd4 4. Nxd4 Nf6 5. Nc3 g6"),
    ("B80", "Sicilian Defense: Scheveningen Variation", "1. e4 c5 2. Nf3 d6 3. d4 cxd4 4. Nxd4 Nf6 5. Nc3 e6"),
    ("B90", "Sicilian Defense: Najdorf Variation", "1. e4 c5 2. Nf3 d6 3. d4 cxd4 4. Nxd4 Nf6 5. Nc3 a6"),
    ("B92", "Sicilian Najdorf: Opocensky Variation", "1. e4 c5 2. Nf3 d6 3. d4 cxd4 4. Nxd4 Nf6 5. Nc3 a6 6. Be2"),
    ("B96", "Sicilian Najdorf: English Attack / Bg5", "1. e4 c5 2. Nf3 d6 3. d4 cxd4 4. Nxd4 Nf6 5. Nc3 a6 6. Bg5"),
    ("C00", "French Defense", "1. e4 e6"),
    ("C01", "French Defense: Exchange Variation", "1. e4 e6 2. d4 d5 3. exd5 exd5"),
    ("C02", "French Defense: Advance Variation", "1. e4 e6 2. d4 d5 3. e5"),
    ("C03", "French Defense: Tarrasch Variation", "1. e4 e6 2. d4 d5 3. Nd2"),
    ("C10", "French Defense: Paulsen / Rubinstein", "1. e4 e6 2. d4 d5 3. Nc3"),
    ("C11", "French Defense: Classical Variation", "1. e4 e6 2. d4 d5 3. Nc3 Nf6"),
    ("C15", "French Defense: Winawer Variation", "1. e4 e6 2. d4 d5 3. Nc3 Bb4"),
    ("C20", "King's Pawn Game: Open Game", "1. e4 e5"),
    ("C21", "Danish Gambit / Center Game", "1. e4 e5 2. d4 exd4"),
    ("C23", "Bishop's Opening", "1. e4 e5 2. Bc4"),
    ("C25", "Vienna Game", "1. e4 e5 2. Nc3"),
    ("C29", "Vienna Gambit", "1. e4 e5 2. Nc3 Nf6 3. f4"),
    ("C30", "King's Gambit", "1. e4 e5 2. f4"),
    ("C33", "King's Gambit Accepted", "1. e4 e5 2. f4 exf4"),
    ("C40", "King's Knight Opening", "1. e4 e5 2. Nf3"),
    ("C40", "Latvian Gambit", "1. e4 e5 2. Nf3 f5"),
    ("C41", "Philidor Defense", "1. e4 e5 2. Nf3 d6"),
    ("C42", "Petrov's Defense (Russian Game)", "1. e4 e5 2. Nf3 Nf6"),
    ("C44", "Scotch Game / Ponziani", "1. e4 e5 2. Nf3 Nc6"),
    ("C45", "Scotch Game", "1. e4 e5 2. Nf3 Nc6 3. d4 exd4 4. Nxd4"),
    ("C46", "Three Knights Game", "1. e4 e5 2. Nf3 Nc6 3. Nc3"),
    ("C47", "Four Knights Game", "1. e4 e5 2. Nf3 Nc6 3. Nc3 Nf6"),
    ("C50", "Italian Game", "1. e4 e5 2. Nf3 Nc6 3. Bc4"),
    ("C50", "Giuoco Pianissimo", "1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5 4. d3"),
    ("C51", "Evans Gambit", "1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5 4. b4"),
    ("C53", "Italian Game: Giuoco Piano", "1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5 4. c3"),
    ("C55", "Two Knights Defense", "1. e4 e5 2. Nf3 Nc6 3. Bc4 Nf6"),
    ("C57", "Two Knights Defense: Fried Liver / Traxler", "1. e4 e5 2. Nf3 Nc6 3. Bc4 Nf6 4. Ng5"),
    ("C60", "Ruy Lopez (Spanish Game)", "1. e4 e5 2. Nf3 Nc6 3. Bb5"),
    ("C65", "Ruy Lopez: Berlin Defense", "1. e4 e5 2. Nf3 Nc6 3. Bb5 Nf6"),
    ("C68", "Ruy Lopez: Exchange Variation", "1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Bxc6"),
    ("C78", "Ruy Lopez: Morphy Defense", "1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6 5. O-O"),
    ("C84", "Ruy Lopez: Closed", "1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6 5. O-O Be7"),
    ("C89", "Ruy Lopez: Marshall Attack", "1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6 5. O-O Be7 6. Re1 b5 7. Bb3 O-O 8. c3 d5"),
    ("D00", "Queen's Pawn Game: Closed", "1. d4 d5"),
    ("D00", "Blackmar-Diemer Gambit", "1. d4 d5 2. e4 dxe4 3. Nc3"),
    ("D02", "London System", "1. d4 d5 2. Nf3 Nf6 3. Bf4"),
    ("D04", "Colle System", "1. d4 d5 2. Nf3 Nf6 3. e3"),
    ("D06", "Queen's Gambit", "1. d4 d5 2. c4"),
    ("D07", "Chigorin Defense", "1. d4 d5 2. c4 Nc6"),
    ("D08", "Albin Countergambit", "1. d4 d5 2. c4 e5"),
    ("D10", "Slav Defense", "1. d4 d5 2. c4 c6"),
    ("D15", "Slav Defense: Three Knights", "1. d4 d5 2. c4 c6 3. Nf3 Nf6 4. Nc3"),
    ("D20", "Queen's Gambit Accepted", "1. d4 d5 2. c4 dxc4"),
    ("D30", "Queen's Gambit Declined", "1. d4 d5 2. c4 e6"),
    ("D35", "Queen's Gambit Declined: Exchange Variation", "1. d4 d5 2. c4 e6 3. Nc3 Nf6 4. cxd5 exd5"),
    ("D37", "Queen's Gambit Declined: Classical", "1. d4 d5 2. c4 e6 3. Nc3 Nf6 4. Nf3"),
    ("D43", "Semi-Slav Defense", "1. d4 d5 2. c4 c6 3. Nf3 Nf6 4. Nc3 e6"),
    ("D53", "Queen's Gambit Declined: Orthodox", "1. d4 d5 2. c4 e6 3. Nc3 Nf6 4. Bg5 Be7"),
    ("D70", "Neo-Grünfeld Defense", "1. d4 Nf6 2. c4 g6 3. f3 d5"),
    ("D80", "Grünfeld Defense", "1. d4 Nf6 2. c4 g6 3. Nc3 d5"),
    ("D85", "Grünfeld Defense: Exchange Variation", "1. d4 Nf6 2. c4 g6 3. Nc3 d5 4. cxd5 Nxd5 5. e4"),
    ("E00", "Catalan Opening / Indian", "1. d4 Nf6 2. c4 e6"),
    ("E01", "Catalan Opening: Closed", "1. d4 Nf6 2. c4 e6 3. g3 d5 4. Bg2"),
    ("E11", "Bogo-Indian Defense", "1. d4 Nf6 2. c4 e6 3. Nf3 Bb4+"),
    ("E12", "Queen's Indian Defense", "1. d4 Nf6 2. c4 e6 3. Nf3 b6"),
    ("E20", "Nimzo-Indian Defense", "1. d4 Nf6 2. c4 e6 3. Nc3 Bb4"),
    ("E32", "Nimzo-Indian: Classical Variation", "1. d4 Nf6 2. c4 e6 3. Nc3 Bb4 4. Qc2"),
    ("E46", "Nimzo-Indian: Rubinstein System", "1. d4 Nf6 2. c4 e6 3. Nc3 Bb4 4. e3 O-O"),
    ("E60", "King's Indian Defense", "1. d4 Nf6 2. c4 g6"),
    ("E61", "King's Indian Defense: Normal", "1. d4 Nf6 2. c4 g6 3. Nc3 Bg7"),
    ("E70", "King's Indian Defense: Classical / Makogonov", "1. d4 Nf6 2. c4 g6 3. Nc3 Bg7 4. e4 d6"),
    ("E80", "King's Indian Defense: Sämisch Variation", "1. d4 Nf6 2. c4 g6 3. Nc3 Bg7 4. e4 d6 5. f3"),
    ("E90", "King's Indian Defense: Classical, Nf3", "1. d4 Nf6 2. c4 g6 3. Nc3 Bg7 4. e4 d6 5. Nf3"),
    ("E97", "King's Indian Defense: Mar del Plata", "1. d4 Nf6 2. c4 g6 3. Nc3 Bg7 4. e4 d6 5. Nf3 O-O 6. Be2 e5 7. O-O Nc6"),
]

TAMPERMONKEY_SCRIPT = f"""// ==UserScript==
// @name         ChessReader HTML Bridge
// @namespace    http://tampermonkey.net/
// @version      1.3
// @description  Sends live board state and move history from Chess.com to the Python tracker
// @match        *://*.chess.com/*
// @grant        GM_xmlhttpRequest
// @connect      127.0.0.1
// ==/UserScript==

(function() {{
    'use strict';

    const FIG_MAP = {{
        "♙": "", "♟": "",
        "♘": "N", "♞": "N",
        "♗": "B", "♝": "B",
        "♖": "R", "♜": "R",
        "♕": "Q", "♛": "Q",
        "♔": "K", "♚": "K"
    }};

    function normalizeSan(raw) {{
        let out = "";
        for (const ch of raw) {{
            out += (ch in FIG_MAP) ? FIG_MAP[ch] : ch;
        }}
        return out
            .replace(/\\s+/g, "")
            .replace(/^\\d+\\.+/, "")
            .replace(/e\\.p\\./gi, "")
            .replace(/[!?‼⁇⁉⁈]+$/g, "")
            .trim();
    }}

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
        return normalizeSan(san);
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
        "version": "1.3",
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

const FIG_MAP = {
  "♙": "", "♟": "",
  "♘": "N", "♞": "N",
  "♗": "B", "♝": "B",
  "♖": "R", "♜": "R",
  "♕": "Q", "♛": "Q",
  "♔": "K", "♚": "K"
};

function normalizeSan(raw) {
  let out = "";
  for (const ch of raw) {
    out += (ch in FIG_MAP) ? FIG_MAP[ch] : ch;
  }
  return out
    .replace(/\\s+/g, "")
    .replace(/^\\d+\\.+/, "")
    .replace(/e\\.p\\./gi, "")
    .replace(/[!?‼⁇⁉⁈]+$/g, "")
    .trim();
}

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
  return normalizeSan(san);
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
            height=1,
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
        self.root.geometry("1080x855")
        self.root.minsize(940, 775)
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

        # Arrows for Top 3 engine moves: list of (rank_int, chess.Move)
        self.top3_arrows = []
        self.preview_canvases = []
        self.book_preview_canvases = []

        self.engine = None
        self.engine_path = self._auto_find_rodent()
        self.engine_dir = (
            os.path.dirname(os.path.abspath(self.engine_path))
            if self.engine_path
            else os.path.join(BASE_DIR, "Rodent_IV")
        )
        self.engine_lock = threading.Lock()
        self.analysis_generation = 0
        self.is_analyzing = False
        self.pending_analysis_skip_top3 = None
        self.current_eval_cp = 0.0
        self.current_eval_text = "0.0"

        # Personalities / Player Emulation state
        self.personality_var = tk.StringVar(value="Default (Standard)")
        self.personality_map = {"Default (Standard)": "default.txt"}
        self.personality_desc = ""
        self._last_applied_pers = None
        self._last_applied_elo = None

        # Opening Book state (.bin Polyglot - defaults to main/rodent.bin)
        self.book_var = tk.StringVar(value="")
        self.book_map = {"Off (Engine Only)": None}
        self._last_applied_book = None
        self.eco_seq_index = {}        # tuple(uci_moves) -> (eco, name)
        self.eco_fen_index = {}        # board_fen -> (eco, name)
        self.current_opening_code = ""
        self.current_opening_name = "Starting Position"
        self.current_book_moves = []   # list of (chess.Move, san, weight, pct)

        # Presets + Separate toggles for Evaluation, Book Moves, and Top 3 Engine Moves
        default_cfg = ANALYSIS_PRESETS[DEFAULT_PRESET_NAME]
        self.preset_var = tk.StringVar(value=DEFAULT_PRESET_NAME)
        self.time_var = tk.DoubleVar(value=default_cfg["time"])
        self.elo_var = tk.IntVar(value=default_cfg["elo"])
        self._applying_preset = False

        self.show_eval_var = tk.BooleanVar(value=False)
        self.show_book_var = tk.BooleanVar(value=False)
        self.show_top3_var = tk.BooleanVar(value=False)

        self.board_size = 540
        self.controls_layout_mode = None
        self.top_bar_height_est = 66
        self.opening_bar_height_est = 34
        self.side_bar_width = 216

        self._build_eco_database()
        self._configure_ttk_styles()
        self._build_ui()
        self._refresh_personality_list(self.engine_dir)
        self._refresh_book_list(self.engine_dir)
        self._sync_book_and_engine_state(run_engine=False)
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

    # ================= ECO OPENING BANNER & POLYGLOT BOOK READER =================
    def _build_eco_database(self):
        """Builds fast sequence & transposition lookup tables for the Chess.com-style ECO banner."""
        seq_idx = {}
        fen_idx = {}

        def register_line(eco, name, san_str):
            b = chess.Board()
            uci_seq = []
            tokens = re.sub(r"\d+\.+", " ", san_str).split()
            for tok in tokens:
                tok_clean = tok.strip()
                if not tok_clean or tok_clean in ("*", "1-0", "0-1", "1/2-1/2"):
                    continue
                try:
                    mv = b.parse_san(tok_clean)
                except Exception:
                    break
                b.push(mv)
                uci_seq.append(mv.uci())

            key_seq = tuple(uci_seq)
            seq_idx[key_seq] = (eco, name)
            fen_idx.setdefault(b.board_fen(), (eco, name))

        for eco, name, moves_str in ECO_OPENING_LINES:
            register_line(eco, name, moves_str)

        for search_dir in (BASE_DIR, os.path.join(BASE_DIR, "Rodent_IV")):
            if not os.path.isdir(search_dir):
                continue
            for fname in os.listdir(search_dir):
                fpath = os.path.join(search_dir, fname)
                if fname.lower().endswith(".tsv") and os.path.isfile(fpath):
                    try:
                        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                            for line in f:
                                parts = line.strip().split("\t")
                                if len(parts) >= 3 and re.match(r"^[A-E]\d\d$", parts[0].strip()):
                                    register_line(parts[0].strip(), parts[1].strip(), parts[2].strip())
                    except Exception:
                        pass

        self.eco_seq_index = seq_idx
        self.eco_fen_index = fen_idx

    def _detect_current_opening(self):
        """Detects the current opening (ECO + Name) from move history or board transposition."""
        if len(self.board.move_stack) == 0:
            bfen = self.board.board_fen()
            if bfen == chess.STARTING_BOARD_FEN:
                return "", "Starting Position"
            if bfen in self.eco_fen_index:
                return self.eco_fen_index[bfen]
            return "", "Custom Position"

        temp = chess.Board()
        uci_prefix = []
        best_eco = ""
        best_name = ""

        for mv in self.board.move_stack:
            temp.push(mv)
            uci_prefix.append(mv.uci())
            t_key = tuple(uci_prefix)
            if t_key in self.eco_seq_index:
                best_eco, best_name = self.eco_seq_index[t_key]
            elif temp.board_fen() in self.eco_fen_index:
                best_eco, best_name = self.eco_fen_index[temp.board_fen()]

        if best_name:
            return best_eco, best_name
        return "", "Unclassified Opening"

    def _find_book_files(self, engine_dir=None):
        """Finds all Polyglot .bin opening books in Rodent_IV/books, Rodent_IV, and BASE_DIR."""
        found = []
        seen_paths = set()
        search_dirs = []

        if engine_dir:
            search_dirs.extend([
                os.path.join(engine_dir, "books"),
                os.path.join(os.path.dirname(engine_dir), "books"),
                engine_dir,
            ])
        search_dirs.extend([
            os.path.join(BASE_DIR, "Rodent_IV", "books"),
            os.path.join(BASE_DIR, "books"),
            BASE_DIR,
        ])

        for root_dir in search_dirs:
            if not os.path.isdir(root_dir):
                continue
            for dirpath, _dirnames, filenames in os.walk(root_dir):
                rel_depth = os.path.relpath(dirpath, root_dir).count(os.sep)
                if rel_depth > 2:
                    continue
                for fname in sorted(filenames):
                    if not fname.lower().endswith(".bin"):
                        continue
                    full_p = os.path.abspath(os.path.join(dirpath, fname))
                    norm_p = os.path.normcase(full_p)
                    if norm_p in seen_paths:
                        continue
                    seen_paths.add(norm_p)
                    parent_name = os.path.basename(dirpath)
                    if parent_name.lower() in ("guide", "main", "players"):
                        label = f"{parent_name}/{fname}"
                    else:
                        label = fname
                    found.append((label, full_p))

        found.sort(
            key=lambda item: (
                0 if item[0].lower() == "main/rodent.bin" else (
                    1 if item[0].lower().startswith("main/") else 2
                ),
                item[0].lower()
            )
        )
        return found

    def _refresh_book_list(self, engine_dir=None):
        current_choice = self.book_var.get()
        custom_entries = {
            k: v for k, v in self.book_map.items()
            if k not in ("Off (Engine Only)", "📂 Load Custom .bin...")
            and v and os.path.isfile(v)
        }

        new_map = {"Off (Engine Only)": None}

        for label, full_p in self._find_book_files(engine_dir):
            disp = label
            counter = 2
            while disp in new_map:
                disp = f"{label} ({counter})"
                counter += 1
            new_map[disp] = full_p

        for k, v in custom_entries.items():
            if v not in new_map.values():
                new_map[k] = v

        new_map["📂 Load Custom .bin..."] = "__LOAD_CUSTOM__"
        self.book_map = new_map
        self.book_combo["values"] = list(new_map.keys())

        real_bins = [
            k for k, v in new_map.items()
            if v and v != "__LOAD_CUSTOM__"
        ]

        if current_choice and current_choice in new_map and current_choice != "📂 Load Custom .bin...":
            self.book_var.set(current_choice)
        elif real_bins:
            preferred = (
                next((k for k in real_bins if k.lower() == "main/rodent.bin"), None)
                or next((k for k in real_bins if k.lower().startswith("main/") and "rodent" in k.lower()), None)
                or next((k for k in real_bins if k.lower().startswith("main/")), None)
                or next((k for k in real_bins if "rodent" in k.lower() and "guide" not in k.lower()), None)
                or next((k for k in real_bins if "guide" not in k.lower()), None)
                or real_bins[0]
            )
            self.book_var.set(preferred)
        else:
            self.book_var.set("Off (Engine Only)")

        bin_count = len(real_bins)
        if bin_count > 0:
            self.book_count_lbl.config(text=f"({bin_count})", fg="#00ff66")
        else:
            self.book_count_lbl.config(text="(0)", fg="#ff5555")

    def _select_custom_book_dialog(self):
        initial_dir = os.path.join(self.engine_dir, "books", "main")
        if not os.path.isdir(initial_dir):
            initial_dir = os.path.join(self.engine_dir, "books")
        if not os.path.isdir(initial_dir):
            initial_dir = self.engine_dir if os.path.isdir(self.engine_dir) else BASE_DIR

        path = filedialog.askopenfilename(
            initialdir=initial_dir,
            title="Select Polyglot Opening Book (.bin)",
            filetypes=[("Polyglot Opening Books", "*.bin"), ("All Files", "*.*")]
        )
        if path and os.path.isfile(path):
            full_p = os.path.abspath(path)
            label = os.path.basename(full_p)
            existing_key = next((k for k, v in self.book_map.items() if v == full_p), None)
            if existing_key:
                self.book_var.set(existing_key)
            else:
                rebuilt = {}
                for k, v in self.book_map.items():
                    if v == "__LOAD_CUSTOM__":
                        rebuilt[label] = full_p
                    rebuilt[k] = v
                self.book_map = rebuilt
                self.book_combo["values"] = list(rebuilt.keys())
                self.book_var.set(label)
            self._on_book_changed()
        else:
            if self.book_var.get() == "📂 Load Custom .bin...":
                real_bins = [k for k, v in self.book_map.items() if v and v != "__LOAD_CUSTOM__"]
                self.book_var.set(real_bins[0] if real_bins else "Off (Engine Only)")

    def _on_book_changed(self, _event=None):
        selected = self.book_var.get()
        if selected == "📂 Load Custom .bin...":
            self._select_custom_book_dialog()
            return

        self._last_applied_book = None
        self._sync_book_and_engine_state(run_engine=True)

    def _get_book_moves_for_board(self, board_obj):
        selected_label = self.book_var.get()
        book_target = self.book_map.get(selected_label)
        if not book_target or book_target == "__LOAD_CUSTOM__":
            return []

        if not HAS_POLYGLOT or not os.path.isfile(book_target):
            return []

        raw_entries = []
        try:
            with chess.polyglot.open_reader(book_target) as reader:
                for entry in reader.find_all(board_obj, minimum_weight=1):
                    mv = entry.move
                    if mv in board_obj.legal_moves:
                        raw_entries.append((mv, max(1, int(entry.weight))))
        except Exception:
            return []

        if not raw_entries:
            return []

        merged = {}
        for mv, w in raw_entries:
            merged[mv] = merged.get(mv, 0) + w

        sorted_items = sorted(merged.items(), key=lambda kv: kv[1], reverse=True)
        total_w = max(1, sum(w for _, w in sorted_items))

        results = []
        for mv, w in sorted_items:
            pct = (w / total_w) * 100.0
            results.append((mv, board_obj.san(mv), w, pct))
        return results

    def _execute_test_move(self, move):
        if move not in self.board.legal_moves:
            return

        matched_book = next((item for item in self.current_book_moves if item[0] == move), None)

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

        self._update_pgn_display()
        self._update_nav_buttons()
        status_txt, status_col = self._format_sync_status_text()
        self.status_label.config(text=status_txt, fg=status_col)

        if matched_book is not None:
            self.move_verdict_lbl.config(
                text=f"📖 {san_move}: Book Move ({matched_book[3]:.0f}% theory)\nContinuing theory / engine analysis...",
                fg="#10b981"
            )
            self._sync_book_and_engine_state(run_engine=True)
        else:
            self._sync_book_and_engine_state(run_engine=False)
            self._evaluate_tried_move(board_before, board_after, move, san_move)

    def _play_book_move(self, move):
        self._execute_test_move(move)

    def _clear_book_preview_canvases(self):
        for cv in self.book_preview_canvases:
            try:
                cv.destroy()
            except Exception:
                pass
        self.book_preview_canvases = []

    def _set_book_message(self, msg, tag="info_text"):
        self.book_text.config(state="normal", height=2)
        self._clear_book_preview_canvases()
        self.book_text.delete("1.0", tk.END)
        self.book_text.insert(tk.END, msg, tag)
        self.book_text.config(state="disabled")
        self.root.after_idle(lambda: self.book_scroll.set(*self.book_text.yview()))

    def _render_book_moves_list(self, book_moves):
        visible_rows = max(2, min(len(book_moves), 9))
        self.book_text.config(state="normal", height=visible_rows)
        self._clear_book_preview_canvases()
        self.book_text.delete("1.0", tk.END)

        for idx, (mv, san, _w, pct) in enumerate(book_moves):
            if idx > 0:
                self.book_text.insert(tk.END, "\n")

            color = BOOK_ARROW_PALETTE[min(idx, len(BOOK_ARROW_PALETTE) - 1)]
            if idx == 0:
                width, arrowshape = 3.8, (6, 7, 4)
            elif idx == 1:
                width, arrowshape = 2.5, (6, 7, 3)
            elif idx == 2:
                width, arrowshape = 1.8, (5, 6, 3)
            else:
                width, arrowshape = 1.2, (5, 6, 2)

            mini_cv = tk.Canvas(
                self.book_text,
                width=26,
                height=12,
                bg="#121212",
                highlightthickness=0,
                bd=0
            )
            mini_cv.create_line(
                1, 6, 24, 6,
                fill=color,
                width=width,
                arrow=tk.LAST,
                arrowshape=arrowshape,
                capstyle=tk.ROUND
            )
            self.book_preview_canvases.append(mini_cv)

            rank_tag = "book_top" if idx == 0 else "book_row"
            self.book_text.insert(tk.END, f"{idx + 1:>2}. ", rank_tag)
            self.book_text.window_create(tk.END, window=mini_cv, align="center")

            cont_sans = []
            tb = self.board.copy(stack=False)
            tb.push(mv)
            for _step in range(4):
                nxt = self._get_book_moves_for_board(tb)
                if nxt and nxt[0][0] in tb.legal_moves:
                    cont_sans.append(nxt[0][1])
                    tb.push(nxt[0][0])
                else:
                    break

            cont_str = f" -> {' '.join(cont_sans)}" if cont_sans else ""
            link_tag = f"book_mv_{idx}"
            self.book_text.tag_configure(
                link_tag,
                foreground="#fde047" if idx == 0 else "#e5e7eb",
                font=("Consolas", 8, "bold" if idx == 0 else "normal")
            )
            self.book_text.tag_bind(link_tag, "<Button-1>", lambda _e, m=mv: self._play_book_move(m))
            self.book_text.tag_bind(link_tag, "<Enter>", lambda _e: self.book_text.config(cursor="hand2"))
            self.book_text.tag_bind(link_tag, "<Leave>", lambda _e: self.book_text.config(cursor="arrow"))

            move_col = f"{san:<5}"
            pct_col = f"[{pct:>3.0f}%]"
            self.book_text.insert(tk.END, f" {move_col} {pct_col}{cont_str}", link_tag)

        self.book_text.config(state="disabled")
        self.root.after_idle(lambda: self.book_scroll.set(*self.book_text.yview()))

    def _sync_book_and_engine_state(self, run_engine=True):
        eco, name = self._detect_current_opening()
        self.current_opening_code = eco
        self.current_opening_name = name

        book_selected = self.book_var.get()
        want_book = self.show_book_var.get()
        want_top3 = self.show_top3_var.get()
        want_eval = self.show_eval_var.get()

        if want_book and book_selected != "Off (Engine Only)":
            book_moves = self._get_book_moves_for_board(self.board)
        else:
            book_moves = []

        self.current_book_moves = book_moves

        if eco:
            banner_txt = f"📖 {eco} • {name}"
            banner_fg = "#f8fafc"
        else:
            banner_txt = f"📖 {name}"
            banner_fg = "#cbd5e1"

        if want_book and book_moves:
            banner_txt += f"   [{len(book_moves)} book moves]"
        self.opening_title_lbl.config(text=banner_txt, fg=banner_fg)

        if not want_book:
            self.book_meta_lbl.config(text=f"Book: {book_selected} | Disabled", fg="#6b7280")
            self._set_book_message("Check 'Book Moves + All Book Arrows' to show all book moves.", "info_text")
        elif book_selected == "Off (Engine Only)":
            self.book_meta_lbl.config(text="Book: Off (Engine Only)", fg="#fbbf24")
            self._set_book_message("Select a .bin opening book above (e.g. main/rodent.bin).", "warn_text")
        elif book_moves:
            self.book_meta_lbl.config(
                text=f"✓ {book_selected} | {len(book_moves)} book move(s) (click to test)",
                fg="#10b981"
            )
            self._render_book_moves_list(book_moves)
        else:
            self.book_meta_lbl.config(
                text=f"Out of book [{book_selected}] | 0 book moves",
                fg="#9ca3af"
            )
            self._set_book_message("Out of book — no theory moves left for this position.", "info_text")

        book_blocks_top3 = (want_book and len(book_moves) > 0)

        if want_top3 and book_blocks_top3:
            self.analysis_generation += 1
            self.is_analyzing = False
            self.top3_arrows = []
            self.top3_meta_lbl.config(
                text=f"⏸ Paused (In Book: {len(book_moves)} moves)",
                fg="#10b981"
            )
            self._set_top3_message(
                "Paused while book moves are available.\nWill calculate Top 3 Moves automatically once out of book.",
                "info_text"
            )
            self._draw_board()
            if run_engine and want_eval:
                self._request_engine_analysis(skip_top3=True)
            return

        if want_top3 and not run_engine:
            prof = self._get_rank_profile()
            style_tag = self._get_active_style_tag()
            if self.board.turn == chess.WHITE:
                self.side1_header_lbl.config(text=f"⚪ WHITE{style_tag} (to move):", fg="#f8fafc")
            else:
                self.side1_header_lbl.config(text=f"⚫ BLACK{style_tag} (to move):", fg="#fbbf24")
            self.top3_meta_lbl.config(
                text=f"⏳ {prof['rank_short']}{style_tag} | Out of book — preparing Top 3...",
                fg="#fbbf24"
            )
            self._set_top3_message("Out of book — preparing Top 3 Moves...", "warn_text")

        self._draw_board()

        if run_engine and (want_top3 or want_eval):
            self._request_engine_analysis(skip_top3=False)

    def _on_toggle_book(self):
        self._sync_book_and_engine_state(run_engine=True)

    def _configure_ttk_styles(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure(
            "Dark.TCombobox",
            fieldbackground="#1f2937",
            background="#1f2937",
            foreground="#ffffff",
            arrowcolor="#00d4ff",
            bordercolor="#374151",
            lightcolor="#1f2937",
            darkcolor="#1f2937",
            padding=3,
        )
        style.map(
            "Dark.TCombobox",
            fieldbackground=[("readonly", "#1f2937")],
            selectbackground=[("readonly", "#1f2937")],
            selectforeground=[("readonly", "#ffffff")],
            foreground=[("readonly", "#ffffff")],
        )

        self.root.option_add("*TCombobox*Listbox.background", "#18181b")
        self.root.option_add("*TCombobox*Listbox.foreground", "#ffffff")
        self.root.option_add("*TCombobox*Listbox.selectBackground", "#2563eb")
        self.root.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")
        self.root.option_add("*TCombobox*Listbox.font", ("Consolas", 8))

    def _get_max_time_cap(self):
        try:
            return max(0.5, min(10.0, float(self.time_var.get())))
        except Exception:
            return DEFAULT_MAX_TIME_SECONDS

    def _on_preset_changed(self, _event=None):
        chosen = self.preset_var.get()
        cfg = ANALYSIS_PRESETS.get(chosen)
        if not cfg:
            return

        self._applying_preset = True
        try:
            self.elo_var.set(cfg["elo"])
            self.time_var.set(cfg["time"])
        finally:
            self._applying_preset = False

        cap_sec = cfg["time"]
        self.time_value_lbl.config(text=f"⏱ Target Time: {cap_sec:.1f}s")
        self.chk_top3.config(text=f"Top 3 Moves + Arrows ({cap_sec:.1f}s)")
        self._update_elo_labels()
        self._last_applied_elo = None
        self.analysis_generation += 1
        self._sync_book_and_engine_state(run_engine=True)

    def _sync_preset_from_manual_sliders(self):
        if self._applying_preset:
            return
        cur_elo = int(self.elo_var.get())
        cur_time = round(self._get_max_time_cap(), 1)
        matched = None
        for pname, cfg in ANALYSIS_PRESETS.items():
            if cfg["elo"] == cur_elo and round(cfg["time"], 1) == cur_time:
                matched = pname
                break
        self.preset_var.set(matched if matched else CUSTOM_PRESET_LABEL)

    def _on_time_changed(self, _val=None):
        self._sync_preset_from_manual_sliders()
        cap_sec = self._get_max_time_cap()
        self.time_value_lbl.config(text=f"⏱ Target Time: {cap_sec:.1f}s")
        self.chk_top3.config(text=f"Top 3 Moves + Arrows ({cap_sec:.1f}s)")
        self._update_elo_labels()
        self.analysis_generation += 1
        self._sync_book_and_engine_state(run_engine=True)

    # ================= PERSONALITIES & ELO-SCALED BUDGETS =================
    def _format_personality_display_name(self, filename):
        stem = os.path.splitext(os.path.basename(filename))[0]
        cleaned = stem.replace("_", " ").replace("-", " ").strip()
        return " ".join(part.capitalize() for part in cleaned.split())

    def _find_personalities_dir(self, engine_dir=None):
        candidates = []
        if engine_dir:
            candidates.append(os.path.join(engine_dir, "personalities"))
            candidates.append(os.path.join(os.path.dirname(engine_dir), "personalities"))
        candidates.append(os.path.join(BASE_DIR, "Rodent_IV", "personalities"))
        candidates.append(os.path.join(BASE_DIR, "personalities"))

        for d in candidates:
            if os.path.isdir(d):
                return d
        return None

    def _refresh_personality_list(self, engine_dir=None, uci_combo_names=None):
        mapping = {"Default (Standard)": "default.txt"}
        seen_files = {"default.txt", "readme.txt", "---.txt"}

        search_dirs = []
        if engine_dir:
            search_dirs.extend([engine_dir, os.path.dirname(engine_dir)])
        search_dirs.append(os.path.join(BASE_DIR, "Rodent_IV"))

        for d in search_dirs:
            basic_ini = os.path.join(d, "basic.ini")
            if os.path.isfile(basic_ini):
                try:
                    with open(basic_ini, "r", encoding="utf-8", errors="ignore") as f:
                        for raw_line in f:
                            line = raw_line.strip()
                            if not line or line.startswith((";", "#", "[")):
                                continue
                            if "=" in line:
                                label, fname = [x.strip() for x in line.split("=", 1)]
                                fname_base = os.path.basename(fname)
                                if (
                                    fname_base.lower().endswith(".txt")
                                    and fname_base.lower() not in seen_files
                                    and not label.startswith("---")
                                ):
                                    mapping[label] = fname_base
                                    seen_files.add(fname_base.lower())
                except Exception:
                    pass
                break

        pers_dir = self._find_personalities_dir(engine_dir)
        extra_entries = []
        if pers_dir:
            for fname in os.listdir(pers_dir):
                if not fname.lower().endswith(".txt"):
                    continue
                if fname.lower() in seen_files or fname.startswith("---"):
                    continue
                seen_files.add(fname.lower())
                disp = self._format_personality_display_name(fname)
                extra_entries.append((disp, fname))

        if uci_combo_names:
            for item in uci_combo_names:
                if item.lower() in ("default", "default (standard)") or item.startswith("---"):
                    continue
                if item not in mapping and all(item != d for d, _ in extra_entries):
                    extra_entries.append((item, item))

        combined_non_default = [
            (k, v) for k, v in mapping.items() if k != "Default (Standard)"
        ] + extra_entries
        combined_non_default.sort(key=lambda pair: pair[0].lower())

        ordered_map = {"Default (Standard)": "default.txt"}
        for disp, fname in combined_non_default:
            ordered_map[disp] = fname

        self.personality_map = ordered_map
        display_values = list(ordered_map.keys())
        self.personality_combo["values"] = display_values

        if self.personality_var.get() not in ordered_map:
            self.personality_var.set("Default (Standard)")

        count_players = max(0, len(display_values) - 1)
        if count_players > 0:
            self.pers_count_lbl.config(text=f"({count_players})", fg="#00ff66")
        else:
            self.pers_count_lbl.config(text="", fg="#777777")

    def _parse_personality_metadata(self, filename):
        pers_dir = self._find_personalities_dir(self.engine_dir)
        if not pers_dir or not filename:
            return None, ""

        fpath = os.path.join(pers_dir, filename)
        if not os.path.isfile(fpath):
            return None, ""

        parsed_elo = None
        desc_parts = []
        try:
            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                for idx, raw_line in enumerate(f):
                    line = raw_line.strip()
                    if not line:
                        continue
                    if line.startswith((";", "#")):
                        if idx < 4:
                            clean_comment = line.lstrip(";#").strip()
                            if clean_comment and not clean_comment.lower().startswith("author"):
                                desc_parts.append(clean_comment)
                        continue
                    m_elo = re.match(r"^(?:UCI_Elo|Elo)\s*=?\s*(\d+)", line, re.IGNORECASE)
                    if m_elo:
                        parsed_elo = int(m_elo.group(1))
        except Exception:
            pass

        return parsed_elo, " ".join(desc_parts)[:60]

    def _on_personality_changed(self, _event=None):
        selected = self.personality_var.get()
        filename = self.personality_map.get(selected, "default.txt")

        if selected == "Default (Standard)":
            self.personality_desc = ""
        else:
            parsed_elo, desc = self._parse_personality_metadata(filename)
            self.personality_desc = desc
            if parsed_elo is not None:
                clamped_elo = max(800, min(2850, int(round(parsed_elo / 50.0) * 50)))
                self.elo_var.set(clamped_elo)
                self._sync_preset_from_manual_sliders()

        self._update_elo_labels()
        self.analysis_generation += 1
        self._sync_book_and_engine_state(run_engine=True)

    def _get_rank_profile(self, elo=None):
        """
        Maps Elo & Time presets into clean search time + depth budgets.
        Always keeps UCI_LimitStrength=False during analysis so Rodent IV never
        corrupts Top 3 move rankings with random eval_blur noise.
        """
        if elo is None:
            elo = int(self.elo_var.get())

        cap_sec = self._get_max_time_cap()
        preset_cfg = ANALYSIS_PRESETS.get(self.preset_var.get())

        if preset_cfg is not None:
            max_depth = preset_cfg["max_depth"]
            mode_tag = preset_cfg["tag"]
        else:
            if elo >= 2850:
                max_depth = None
            elif elo >= 2500:
                max_depth = 18
            elif elo >= 2200:
                max_depth = 14
            elif elo >= 1900:
                max_depth = 11
            elif elo >= 1600:
                max_depth = 8
            elif elo >= 1300:
                max_depth = 6
            else:
                max_depth = 4
            mode_tag = f"Custom • d{max_depth}" if max_depth else "Custom • Full Depth"

        if elo >= 2850:
            rank_short = "MAX (~2975)"
            rank_desc = "MAX (~2975 Elo)"
        elif elo >= 2400:
            rank_short = f"{elo} Elo"
            rank_desc = f"{elo} Elo (Grandmaster)"
        elif elo >= 2000:
            rank_short = f"{elo} Elo"
            rank_desc = f"{elo} Elo (Master)"
        elif elo >= 1500:
            rank_short = f"{elo} Elo"
            rank_desc = f"{elo} Elo (Intermediate)"
        elif elo >= 1150:
            rank_short = f"{elo} Elo"
            rank_desc = f"{elo} Elo (Club)"
        else:
            rank_short = f"{elo} Elo"
            rank_desc = f"{elo} Elo (Beginner)"

        return {
            "elo": elo,
            "rank_short": rank_short,
            "rank_desc": rank_desc,
            "eff_budget": cap_sec,
            "cap_sec": cap_sec,
            "max_depth": max_depth,
            "mode_tag": mode_tag,
        }

    def _get_active_style_tag(self):
        pers = self.personality_var.get()
        if not pers or pers == "Default (Standard)":
            return ""
        return f" [{pers}]"

    def _update_elo_labels(self):
        prof = self._get_rank_profile()
        elo = self.elo_var.get()
        pers = self.personality_var.get()
        color = "#f59e0b" if elo >= 2850 else ("#10b981" if elo >= 2200 else "#00d4ff")

        if pers and pers != "Default (Standard)":
            self.elo_value_lbl.config(text=f"{pers} • {prof['rank_short']}", fg=color)
        else:
            self.elo_value_lbl.config(text=f"Level: {prof['rank_desc']}", fg=color)

        self.time_hint_lbl.config(
            text=f"{prof['mode_tag']} | {prof['cap_sec']:.1f}s search | {ENGINE_THREADS} threads"
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
        s = raw_san.translate(UNICODE_FIGURINE_TRANSLATION).strip()
        s = re.sub(r'^\d+\.+', '', s)
        s = re.sub(r'e\.p\.', '', s, flags=re.IGNORECASE)
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

    def _infer_castling_rights(self, b):
        rights = 0
        if b.piece_at(chess.E1) == chess.Piece(chess.KING, chess.WHITE):
            if b.piece_at(chess.H1) == chess.Piece(chess.ROOK, chess.WHITE):
                rights |= chess.BB_H1
            if b.piece_at(chess.A1) == chess.Piece(chess.ROOK, chess.WHITE):
                rights |= chess.BB_A1
        if b.piece_at(chess.E8) == chess.Piece(chess.KING, chess.BLACK):
            if b.piece_at(chess.H8) == chess.Piece(chess.ROOK, chess.BLACK):
                rights |= chess.BB_H8
            if b.piece_at(chess.A8) == chess.Piece(chess.ROOK, chess.BLACK):
                rights |= chess.BB_A8
        return rights

    def _find_1_or_2_ply_continuation(self, base_board, target_board_fen):
        """Finds exact 1-ply or 2-ply legal move sequence from base_board to target_board_fen."""
        if base_board is None:
            return None

        for mv1 in base_board.legal_moves:
            b1 = base_board.copy(stack=True)
            b1.push(mv1)
            if b1.board_fen() == target_board_fen:
                return b1

        for mv1 in base_board.legal_moves:
            b1 = base_board.copy(stack=True)
            b1.push(mv1)
            for mv2 in b1.legal_moves:
                b2 = b1.copy(stack=True)
                b2.push(mv2)
                if b2.board_fen() == target_board_fen:
                    return b2

        return None

    def _reconstruct_board_from_payload(self, payload, reference_board):
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

        # Reset known sequence only if a genuinely new game started at move 0
        if target_board_fen == chess.STARTING_BOARD_FEN and len(valid_sans) == 0:
            self.known_san_sequence = []
        elif (
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
                        if {last_mv.from_square, last_mv.to_square}.issubset(hl_squares):
                            hl_matches.append(idx)
                if len(hl_matches) == 1:
                    idx = hl_matches[0]
                    return states[idx].copy(stack=True), (idx, total_plies), full_match_moves
                if hl_matches:
                    matching_indices = hl_matches

            cur_ply = len(reference_board.move_stack) if reference_board is not None else total_plies
            best_idx = min(matching_indices, key=lambda i: abs(i - cur_ply))
            return states[best_idx].copy(stack=True), (best_idx, total_plies), full_match_moves

        # Handle 1-ply / 2-ply lag between board DOM update and move-list DOM update
        if total_plies > 0:
            cont_from_seq = self._find_1_or_2_ply_continuation(states[-1], target_board_fen)
            if cont_from_seq is not None:
                ply_now = len(cont_from_seq.move_stack)
                return cont_from_seq, (ply_now, ply_now), list(cont_from_seq.move_stack)

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

            cont_from_ref = self._find_1_or_2_ply_continuation(reference_board, target_board_fen)
            if cont_from_ref is not None:
                ply_now = len(cont_from_ref.move_stack)
                return cont_from_ref, (ply_now, max(ply_now, total_plies)), list(cont_from_ref.move_stack)

        # Fallback for custom/puzzle positions without move history (do NOT wipe known_san_sequence)
        dom_board.castling_rights = self._infer_castling_rights(dom_board)

        last_moved_color = None
        for sq in hl_squares:
            piece_on_hl = dom_board.piece_at(sq)
            if piece_on_hl is not None:
                last_moved_color = piece_on_hl.color
                break

        if last_moved_color is not None:
            dom_board.turn = not last_moved_color
        elif reference_board is not None and reference_board.board_fen() != target_board_fen:
            dom_board.turn = not reference_board.turn
        else:
            dom_board.turn = chess.WHITE

        if not dom_board.is_valid():
            dom_board.turn = not dom_board.turn
            if not dom_board.is_valid():
                return None, (0, 0), []

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
        new_flipped = bool(payload.get("flipped", False))
        flip_changed = (new_flipped != self.flipped)
        self.flipped = new_flipped

        if flip_changed and self.show_eval_var.get():
            self._draw_eval_bar()

        if (self.sandbox_mode or self.manual_history_nav) and not html_changed and not force_analysis:
            self._update_nav_buttons()
            return

        was_in_review_or_sandbox = self.sandbox_mode or self.manual_history_nav
        self.sandbox_mode = False
        self.sandbox_moves = []
        self.manual_history_nav = False
        self.selected_square = None
        self.legal_targets_for_selected = set()
        self.view_ply = html_ply

        if was_in_review_or_sandbox and html_changed:
            self.move_verdict_lbl.config(
                text="New move detected in live match.\nReturned automatically to live position.",
                fg="#00ff66"
            )

        if full_match_moves and html_ply <= len(full_match_moves):
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

        self._update_pgn_display()
        self._update_nav_buttons()

        status_txt, status_col = self._format_sync_status_text()
        self.status_label.config(text=status_txt, fg=status_col)

        self._sync_book_and_engine_state(run_engine=(board_changed or force_analysis))

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

            self._last_applied_pers = None
            self._last_applied_elo = None
            self._last_applied_book = None

            try:
                engine_dir = os.path.dirname(os.path.abspath(path))
                eng = chess.engine.SimpleEngine.popen_uci(path, cwd=engine_dir)
                self.engine = eng
                self.engine_path = path
                self.engine_dir = engine_dir

                init_opts = {}
                applied_threads = 1
                if "Threads" in eng.options:
                    t_min = eng.options["Threads"].min or 1
                    t_max = eng.options["Threads"].max or 16
                    applied_threads = max(t_min, min(t_max, ENGINE_THREADS))
                    init_opts["Threads"] = applied_threads
                if "Hash" in eng.options:
                    h_min = eng.options["Hash"].min or 16
                    h_max = eng.options["Hash"].max or 2048
                    init_opts["Hash"] = max(h_min, min(h_max, ENGINE_HASH_MB))
                if "UseBook" in eng.options:
                    init_opts["UseBook"] = False
                if "UCI_LimitStrength" in eng.options:
                    init_opts["UCI_LimitStrength"] = False
                if init_opts:
                    try:
                        eng.configure(init_opts)
                    except Exception:
                        pass

                combo_choices = None
                if "Personality" in eng.options and getattr(eng.options["Personality"], "var", None):
                    combo_choices = list(eng.options["Personality"].var)

                self._apply_rodent_difficulty_locked()

                bot_name = os.path.basename(path)

                def on_engine_ready():
                    self._refresh_personality_list(engine_dir, combo_choices)
                    self._refresh_book_list(engine_dir)
                    self.engine_status_lbl.config(
                        text=f"✓ {bot_name} ({applied_threads} Threads, {ENGINE_HASH_MB}MB Hash)",
                        fg="#00ff66"
                    )
                    self._sync_book_and_engine_state(run_engine=True)

                self.root.after(0, on_engine_ready)
            except Exception as e:
                self.engine = None
                self.root.after(0, lambda: self.engine_status_lbl.config(
                    text="Failed to start Rodent IV!",
                    fg="#ff5555"
                ))
                self.root.after(0, lambda: messagebox.showerror(
                    "Rodent IV Error", f"Could not start the engine:\n{e}"
                ))

    def _restart_engine_locked(self):
        if not self.engine_path or not os.path.isfile(self.engine_path):
            return False
        if self.engine:
            try:
                self.engine.kill()
            except Exception:
                pass
            self.engine = None

        self._last_applied_pers = None
        self._last_applied_elo = None
        self._last_applied_book = None

        try:
            engine_dir = os.path.dirname(os.path.abspath(self.engine_path))
            eng = chess.engine.SimpleEngine.popen_uci(self.engine_path, cwd=engine_dir)
            self.engine = eng
            opts = {}
            if "Threads" in eng.options:
                opts["Threads"] = max(eng.options["Threads"].min or 1, min(eng.options["Threads"].max or 16, ENGINE_THREADS))
            if "Hash" in eng.options:
                opts["Hash"] = max(eng.options["Hash"].min or 16, min(eng.options["Hash"].max or 2048, ENGINE_HASH_MB))
            if "UseBook" in eng.options:
                opts["UseBook"] = False
            if "UCI_LimitStrength" in eng.options:
                opts["UCI_LimitStrength"] = False
            if opts:
                eng.configure(opts)
            self._apply_rodent_difficulty_locked()
            return True
        except Exception:
            self.engine = None
            return False

    def _apply_rodent_book_locked(self):
        if not self.engine:
            return
        if self._last_applied_book == "PYTHON_POLYGLOT_ONLY":
            return
        if "UseBook" in self.engine.options:
            try:
                self.engine.configure({"UseBook": False})
            except Exception:
                pass
        self._last_applied_book = "PYTHON_POLYGLOT_ONLY"

    def _apply_rodent_difficulty_locked(self, force_max=False):
        if not self.engine:
            return

        self._apply_rodent_book_locked()

        selected_pers = self.personality_var.get()
        if selected_pers != self._last_applied_pers:
            pers_filename = self.personality_map.get(selected_pers, "default.txt")
            pers_opts = {}
            if "PersonalityFile" in self.engine.options:
                pers_opts["PersonalityFile"] = pers_filename
            elif "Personality" in self.engine.options:
                combo_vars = getattr(self.engine.options["Personality"], "var", None) or []
                if selected_pers == "Default (Standard)":
                    if "Default" in combo_vars:
                        pers_opts["Personality"] = "Default"
                elif selected_pers in combo_vars:
                    pers_opts["Personality"] = selected_pers
            if pers_opts:
                try:
                    self.engine.configure(pers_opts)
                except Exception:
                    pass
            self._last_applied_pers = selected_pers
            self._last_applied_elo = None
            self._last_applied_book = None
            self._apply_rodent_book_locked()

        # Always keep UCI_LimitStrength=False so Rodent IV never injects random eval_blur noise into MultiPV
        if self._last_applied_elo != "CLEAN_ALPHA_BETA":
            if "UCI_LimitStrength" in self.engine.options:
                try:
                    self.engine.configure({"UCI_LimitStrength": False})
                except Exception:
                    pass
            self._last_applied_elo = "CLEAN_ALPHA_BETA"

    def _on_elo_changed(self, _val=None):
        self._sync_preset_from_manual_sliders()
        self._update_elo_labels()
        self.analysis_generation += 1
        self._sync_book_and_engine_state(run_engine=True)

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
        main_container.pack(fill="both", expand=True, padx=14, pady=8)

        right_frame = tk.Frame(
            main_container,
            bg="#0a0a0a",
            width=430,
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

        # --- CHESS.COM-STYLE OPENING BANNER ABOVE THE BOARD ---
        self.opening_banner_frame = tk.Frame(
            self.board_stage_frame,
            bg="#111318",
            highlightthickness=1,
            highlightbackground="#262b36"
        )
        self.opening_banner_frame.pack(side=tk.TOP, fill="x", padx=6, pady=(2, 6))

        self.opening_title_lbl = tk.Label(
            self.opening_banner_frame,
            text="📖 Starting Position",
            bg="#111318",
            fg="#f8fafc",
            font=("Consolas", 9, "bold"),
            anchor="w",
            padx=10,
            pady=4
        )
        self.opening_title_lbl.pack(fill="x")

        # --- BOARD CONTAINER BELOW OPENING BANNER ---
        self.board_center_area = tk.Frame(self.board_stage_frame, bg="#000000")
        self.board_center_area.pack(side=tk.TOP, fill="both", expand=True)

        self.board_row_frame = tk.Frame(self.board_center_area, bg="#000000")
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

        self._apply_controls_layout("top")

        # ================= RIGHT SIDE (ENGINE + PRESETS + BOOK MOVES + TOP 3 MOVES + NAV + PGN) =================
        top_hdr = tk.Frame(right_frame, bg="#0a0a0a")
        top_hdr.pack(fill="x", padx=12, pady=(8, 2))

        tk.Label(
            top_hdr,
            text="RODENT IV ENGINE",
            bg="#0a0a0a",
            fg="#ffffff",
            font=("Consolas", 11, "bold")
        ).pack(side=tk.LEFT)

        self.select_bot_btn = tk.Button(
            top_hdr,
            text="⚙ Change .exe",
            command=self._select_rodent_dialog,
            bg="#1f2937",
            fg="#ffffff",
            activebackground="#374151",
            activeforeground="#ffffff",
            relief="flat",
            font=("Consolas", 8, "bold"),
            padx=8,
            pady=2,
            cursor="hand2"
        )
        self.select_bot_btn.pack(side=tk.RIGHT)

        self.engine_status_lbl = tk.Label(
            right_frame,
            text="Rodent_IV\\rodent-iv-x64.exe not found",
            bg="#0a0a0a",
            fg="#ffaa00",
            font=("Consolas", 8),
            anchor="w"
        )
        self.engine_status_lbl.pack(fill="x", padx=12, pady=(0, 4))

        # --- PRESET + ELO + PLAYER STYLE + OPENING BOOK BOX ---
        diff_frame = tk.Frame(right_frame, bg="#111111", highlightthickness=1, highlightbackground="#222222")
        diff_frame.pack(fill="x", padx=12, pady=(0, 5))

        preset_row = tk.Frame(diff_frame, bg="#111111")
        preset_row.pack(fill="x", padx=12, pady=(6, 3))

        tk.Label(
            preset_row,
            text="🎛 Preset:",
            bg="#111111",
            fg="#f59e0b",
            font=("Consolas", 8, "bold"),
            width=9,
            anchor="w"
        ).pack(side=tk.LEFT, padx=(0, 4))

        preset_values = list(ANALYSIS_PRESETS.keys()) + [CUSTOM_PRESET_LABEL]
        self.preset_combo = ttk.Combobox(
            preset_row,
            textvariable=self.preset_var,
            values=preset_values,
            state="readonly",
            style="Dark.TCombobox",
            font=("Consolas", 8, "bold"),
            width=26
        )
        self.preset_combo.pack(side=tk.LEFT, fill="x", expand=True)
        self.preset_combo.bind("<<ComboboxSelected>>", self._on_preset_changed)

        self.elo_value_lbl = tk.Label(
            diff_frame,
            text="Level: 2000 Elo (Master)",
            bg="#111111",
            fg="#00d4ff",
            font=("Consolas", 9, "bold")
        )
        self.elo_value_lbl.pack(pady=(2, 0))

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
            length=375,
            cursor="hand2"
        )
        self.elo_slider.pack(padx=12, pady=(1, 3))

        pers_row = tk.Frame(diff_frame, bg="#111111")
        pers_row.pack(fill="x", padx=12, pady=(0, 4))

        tk.Label(
            pers_row,
            text="🎭 Player:",
            bg="#111111",
            fg="#e5e7eb",
            font=("Consolas", 8, "bold"),
            width=9,
            anchor="w"
        ).pack(side=tk.LEFT, padx=(0, 4))

        self.personality_combo = ttk.Combobox(
            pers_row,
            textvariable=self.personality_var,
            values=["Default (Standard)"],
            state="readonly",
            style="Dark.TCombobox",
            font=("Consolas", 8, "bold"),
            width=22
        )
        self.personality_combo.pack(side=tk.LEFT, fill="x", expand=True)
        self.personality_combo.bind("<<ComboboxSelected>>", self._on_personality_changed)

        self.pers_count_lbl = tk.Label(
            pers_row,
            text="",
            bg="#111111",
            fg="#777777",
            font=("Consolas", 7)
        )
        self.pers_count_lbl.pack(side=tk.LEFT, padx=(6, 0))

        # --- OPENING BOOK SELECTOR ROW (DEFAULTS TO main/rodent.bin) ---
        book_row = tk.Frame(diff_frame, bg="#111111")
        book_row.pack(fill="x", padx=12, pady=(0, 5))

        tk.Label(
            book_row,
            text="📖 Book:",
            bg="#111111",
            fg="#10b981",
            font=("Consolas", 8, "bold"),
            width=9,
            anchor="w"
        ).pack(side=tk.LEFT, padx=(0, 4))

        self.book_combo = ttk.Combobox(
            book_row,
            textvariable=self.book_var,
            values=["Off (Engine Only)"],
            state="readonly",
            style="Dark.TCombobox",
            font=("Consolas", 8, "bold"),
            width=19
        )
        self.book_combo.pack(side=tk.LEFT, fill="x", expand=True)
        self.book_combo.bind("<<ComboboxSelected>>", self._on_book_changed)

        self.load_book_btn = tk.Button(
            book_row,
            text="📂",
            command=self._select_custom_book_dialog,
            bg="#1f2937",
            fg="#38bdf8",
            activebackground="#374151",
            activeforeground="#ffffff",
            relief="flat",
            font=("Consolas", 8, "bold"),
            padx=5,
            pady=1,
            cursor="hand2"
        )
        self.load_book_btn.pack(side=tk.LEFT, padx=(4, 0))

        self.book_count_lbl = tk.Label(
            book_row,
            text="",
            bg="#111111",
            fg="#777777",
            font=("Consolas", 7)
        )
        self.book_count_lbl.pack(side=tk.LEFT, padx=(4, 0))

        # --- TARGET TIME BOX ---
        time_box = tk.Frame(
            right_frame,
            bg="#111111",
            highlightthickness=1,
            highlightbackground="#222222"
        )
        time_box.pack(fill="x", padx=12, pady=(0, 5))

        self.time_value_lbl = tk.Label(
            time_box,
            text=f"⏱ Target Time: {DEFAULT_MAX_TIME_SECONDS:.1f}s",
            bg="#111111",
            fg="#00ff66",
            font=("Consolas", 9, "bold")
        )
        self.time_value_lbl.pack(pady=(3, 0))

        self.time_slider = tk.Scale(
            time_box,
            from_=0.5,
            to=10.0,
            resolution=0.5,
            orient=tk.HORIZONTAL,
            variable=self.time_var,
            command=self._on_time_changed,
            bg="#111111",
            fg="#cccccc",
            troughcolor="#262626",
            highlightthickness=0,
            showvalue=False,
            sliderlength=16,
            length=375,
            cursor="hand2"
        )
        self.time_slider.pack(padx=12, pady=(1, 1))

        self.time_hint_lbl = tk.Label(
            time_box,
            text=f"Advanced • d12 | {DEFAULT_MAX_TIME_SECONDS:.1f}s search | {ENGINE_THREADS} threads",
            bg="#111111",
            fg="#9ca3af",
            font=("Consolas", 7)
        )
        self.time_hint_lbl.pack(pady=(0, 3))

        # --- 1) POSITION EVALUATION BAR CHECKBOX ---
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
        self.chk_eval.pack(fill="x", padx=14, pady=(0, 0))

        self.eval_detail_lbl = tk.Label(
            right_frame,
            text="Evaluation: disabled",
            bg="#0a0a0a",
            fg="#777777",
            font=("Consolas", 8),
            anchor="w"
        )
        self.eval_detail_lbl.pack(fill="x", padx=34, pady=(0, 2))

        # --- 2) DEDICATED BOOK MOVES CHECKBOX + PANEL ---
        self.chk_book = tk.Checkbutton(
            right_frame,
            text="Book Moves + All Book Arrows",
            variable=self.show_book_var,
            command=self._on_toggle_book,
            bg="#0a0a0a",
            fg="#10b981",
            selectcolor="#1f2937",
            activebackground="#0a0a0a",
            activeforeground="#34d399",
            font=("Consolas", 9, "bold"),
            anchor="w",
            cursor="hand2"
        )
        self.chk_book.pack(fill="x", padx=14, pady=(0, 2))

        self.book_moves_frame = tk.Frame(
            right_frame,
            bg="#121212",
            highlightthickness=1,
            highlightbackground="#1e3a2f"
        )
        self.book_moves_frame.pack(fill="x", padx=12, pady=(0, 5))

        self.book_meta_lbl = tk.Label(
            self.book_moves_frame,
            text="Book: Disabled",
            bg="#161b19",
            fg="#6b7280",
            font=("Consolas", 8, "bold"),
            anchor="w",
            padx=8,
            pady=2
        )
        self.book_meta_lbl.pack(fill="x")

        book_body = tk.Frame(self.book_moves_frame, bg="#121212")
        book_body.pack(fill="x", padx=6, pady=3)
        book_body.columnconfigure(0, weight=1)
        book_body.rowconfigure(0, weight=1)

        self.book_text = tk.Text(
            book_body,
            height=2,
            bg="#121212",
            fg="#e5e7eb",
            relief="flat",
            bd=0,
            highlightthickness=0,
            font=("Consolas", 8),
            wrap="none",
            padx=4,
            pady=1,
            spacing1=1,
            spacing3=1,
            cursor="arrow"
        )
        self.book_text.tag_configure("book_top", foreground="#10b981", font=("Consolas", 8, "bold"))
        self.book_text.tag_configure("book_row", foreground="#38bdf8", font=("Consolas", 8, "bold"))
        self.book_text.tag_configure("info_text", foreground="#6b7280", font=("Consolas", 8))
        self.book_text.tag_configure("warn_text", foreground="#fbbf24", font=("Consolas", 8))
        self.book_text.grid(row=0, column=0, sticky="nsew")

        self.book_scroll = DarkAutoScrollbar(
            book_body,
            command=self.book_text.yview,
            width=7,
            bg="#121212",
            thumb_color="#2a2a2e",
            hover_color="#4b5563",
        )
        self.book_scroll.grid(row=0, column=1, sticky="ns", padx=(2, 0))
        self.book_scroll.grid_remove()
        self.book_text.config(yscrollcommand=self.book_scroll.set)
        self._set_book_message("Check 'Book Moves + All Book Arrows' to show all book moves.", "info_text")

        # --- 3) DEDICATED TOP 3 ENGINE MOVES CHECKBOX + PANEL ---
        self.chk_top3 = tk.Checkbutton(
            right_frame,
            text=f"Top 3 Moves + Arrows ({DEFAULT_MAX_TIME_SECONDS:.1f}s)",
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
        self.chk_top3.pack(fill="x", padx=14, pady=(0, 2))

        self.top3_frame = tk.Frame(
            right_frame,
            bg="#121212",
            highlightthickness=1,
            highlightbackground="#2a2a2a"
        )
        self.top3_frame.pack(fill="x", padx=12, pady=(0, 5))

        self.top3_meta_lbl = tk.Label(
            self.top3_frame,
            text=f"Rank: 2000 Elo | Time: -- / {DEFAULT_MAX_TIME_SECONDS:.1f}s",
            bg="#18181b",
            fg="#60a5fa",
            font=("Consolas", 8, "bold"),
            anchor="w",
            padx=8,
            pady=2
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
        self.side1_header_lbl.pack(fill="x", padx=8, pady=(4, 1))

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
            pady=1,
            cursor="arrow"
        )
        self.top3_text.tag_configure("rank1", foreground="#f59e0b", font=("Consolas", 8, "bold"))
        self.top3_text.tag_configure("rank2", foreground="#38bdf8", font=("Consolas", 8, "bold"))
        self.top3_text.tag_configure("rank3", foreground="#c084fc", font=("Consolas", 8, "bold"))
        self.top3_text.tag_configure("move_text", foreground="#e5e7eb", font=("Consolas", 8))
        self.top3_text.tag_configure("info_text", foreground="#6b7280", font=("Consolas", 8))
        self.top3_text.tag_configure("warn_text", foreground="#fbbf24", font=("Consolas", 8))
        self.top3_text.tag_configure("err_text", foreground="#ff5555", font=("Consolas", 8))
        self.top3_text.pack(fill="x", pady=(0, 4))
        self._set_top3_message("Check box to calculate & show engine arrows.", "info_text")

        # ================= HISTORY NAVIGATION & MOVE VERDICT BOX =================
        sandbox_box = tk.Frame(
            right_frame,
            bg="#121212",
            highlightthickness=1,
            highlightbackground="#2e3b4e"
        )
        sandbox_box.pack(fill="x", padx=12, pady=(0, 5))

        nav_btn_row = tk.Frame(sandbox_box, bg="#121212")
        nav_btn_row.pack(fill="x", padx=8, pady=(5, 4))

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
            pady=3,
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
            pady=3,
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
            pady=3,
            cursor="hand2",
            state="disabled"
        )
        self.exit_try_btn.pack(fill="x", padx=8, pady=(0, 4))

        self.move_verdict_lbl = tk.Label(
            sandbox_box,
            text="Click any piece or book move to test a move,\nor use Backwards / Forwards to review history.",
            bg="#121212",
            fg="#9ca3af",
            font=("Consolas", 8),
            justify="left",
            anchor="nw",
            wraplength=390,
            height=2
        )
        self.move_verdict_lbl.pack(fill="x", padx=8, pady=(0, 5))

        # ================= COMPACT PGN NOTATION BOX =================
        pgn_box = tk.Frame(
            right_frame,
            bg="#121212",
            highlightthickness=1,
            highlightbackground="#262626"
        )
        pgn_box.pack(fill="x", padx=12, pady=(0, 6))

        pgn_header_bar = tk.Frame(pgn_box, bg="#18181b")
        pgn_header_bar.pack(fill="x")

        tk.Label(
            pgn_header_bar,
            text="PGN NOTATION:",
            bg="#18181b",
            fg="#9ca3af",
            font=("Consolas", 8, "bold"),
            anchor="w",
            padx=8,
            pady=2
        ).pack(side=tk.LEFT)

        self.copy_pgn_btn = tk.Button(
            pgn_header_bar,
            text="📋 Copy",
            command=self._copy_pgn_to_clipboard,
            bg="#18181b",
            fg="#60a5fa",
            activebackground="#27272a",
            activeforeground="#93c5fd",
            relief="flat",
            font=("Consolas", 7, "bold"),
            padx=6,
            pady=1,
            cursor="hand2"
        )
        self.copy_pgn_btn.pack(side=tk.RIGHT, padx=4)

        pgn_body = tk.Frame(pgn_box, bg="#0d0d0d")
        pgn_body.pack(fill="x", padx=6, pady=4)
        pgn_body.columnconfigure(0, weight=1)
        pgn_body.rowconfigure(0, weight=1)

        self.pgn_text = tk.Text(
            pgn_body,
            height=3,
            bg="#0d0d0d",
            fg="#00ff66",
            insertbackground="#ffffff",
            relief="flat",
            highlightthickness=0,
            font=("Consolas", 8),
            wrap="word",
            padx=4,
            pady=1,
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

    def _copy_pgn_to_clipboard(self):
        game = chess.pgn.Game.from_board(self.board)
        exporter = chess.pgn.StringExporter(headers=False, variations=False, comments=False)
        pgn_str = game.accept(exporter).strip()
        if not pgn_str or pgn_str == "*":
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(pgn_str)
        self.copy_pgn_btn.config(text="✓ Copied", fg="#00ff66")
        self.root.after(1500, lambda: self.copy_pgn_btn.config(text="📋 Copy", fg="#60a5fa"))

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
            col_w = self.side_bar_width - 12
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
        opening_h = self.opening_bar_height_est

        size_top = max(240, min(left_w - eval_space - margin, left_h - self.top_bar_height_est - opening_h - margin))
        size_side = max(240, min(left_w - self.side_bar_width - eval_space - margin, left_h - opening_h - margin))

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
        if isinstance(event.widget, (tk.Entry, tk.Text, ttk.Combobox)):
            return
        self._step_backwards()

    def _on_right_key(self, event):
        if isinstance(event.widget, (tk.Entry, tk.Text, ttk.Combobox)):
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

        self._update_pgn_display()
        self._update_nav_buttons()

        status_txt, status_col = self._format_sync_status_text()
        self.status_label.config(text=status_txt, fg=status_col)
        self._sync_book_and_engine_state(run_engine=True)

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
                text=f"Match history: move {self.view_ply}/{len(self.match_moves)}.\nClick any piece or book move to test an alternative.",
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
                text=f"Match history: move {self.view_ply}/{len(self.match_moves)}.\nClick any piece or book move to test an alternative.",
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
            text="Returned to live match.\nClick any piece or book move to test a move.",
            fg="#9ca3af"
        )

        self._update_pgn_display()
        self._update_nav_buttons()
        status_txt, status_col = self._format_sync_status_text()
        self.status_label.config(text=status_txt, fg=status_col)

        if self.last_dom_payload:
            self._on_html_board_update(self.last_dom_payload, force_analysis=True)
        else:
            self._sync_book_and_engine_state(run_engine=True)

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
                self._execute_test_move(move)
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

    def _run_search_locked(self, board_obj, time_slice, gen, collect_pvs=False, target_depth=None):
        if self.analysis_generation != gen:
            return None, []

        limit_kwargs = {"time": max(0.05, time_slice)}
        if target_depth is not None:
            limit_kwargs["depth"] = target_depth
        limit = chess.engine.Limit(**limit_kwargs)

        latest_info = None
        seen_root_moves = []

        with self.engine.analysis(board_obj, limit) as analysis:
            for info in analysis:
                if "score" in info:
                    latest_info = info
                if collect_pvs and info.get("pv"):
                    mv0 = info["pv"][0]
                    if mv0 in board_obj.legal_moves and mv0 not in seen_root_moves:
                        seen_root_moves.append(mv0)
                if self.analysis_generation != gen:
                    analysis.stop()
                    break

        return latest_info, seen_root_moves

    def _evaluate_tried_move(self, board_before, board_after, played_move, san_move):
        if not self._ensure_engine_ready():
            self._sync_book_and_engine_state(run_engine=True)
            return

        self.analysis_generation += 1
        gen = self.analysis_generation
        style_tag = self._get_active_style_tag()

        self.move_verdict_lbl.config(
            text=f"⏳ Analyzing {san_move}{style_tag}...",
            fg="#fbbf24"
        )

        def worker():
            mover_is_white = (board_before.turn == chess.WHITE)
            t0 = time.monotonic()
            verdict_msg = None
            verdict_color = "#9ca3af"

            with self.engine_lock:
                if self.engine is not None and self.analysis_generation == gen:
                    try:
                        self._apply_rodent_difficulty_locked(force_max=True)

                        info_before = self.engine.analyse(
                            board_before,
                            chess.engine.Limit(time=0.45)
                        )
                        if self.analysis_generation == gen and info_before and "score" in info_before:
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
                                    chess.engine.Limit(time=0.45)
                                )
                                score_after_obj = info_after["score"].pov(mover_is_white)
                                cp_after = score_after_obj.score(mate_score=10000) / 100.0

                            elapsed = time.monotonic() - t0
                            loss = max(0.0, cp_before - cp_after)
                            is_top_choice = (best_move == played_move)

                            if is_top_choice or loss <= 0.15:
                                verdict = f"🌟 {san_move}: BEST MOVE!"
                                verdict_color = "#00ff66"
                                detail = f"Eval: {cp_after:+.2f} | Time: {elapsed:.1f}s"
                            elif loss <= 0.35:
                                verdict = f"✅ {san_move}: Excellent move!"
                                verdict_color = "#4ade80"
                                detail = f"Diff: -{loss:.2f} | Best: {best_san} ({elapsed:.1f}s)"
                            elif loss <= 0.75:
                                verdict = f"👍 {san_move}: Good move."
                                verdict_color = "#a3e635"
                                detail = f"Diff: -{loss:.2f} | Better: {best_san} ({elapsed:.1f}s)"
                            elif loss <= 1.50:
                                verdict = f"⚠️ {san_move}: Inaccuracy!"
                                verdict_color = "#fbbf24"
                                detail = f"Loss: -{loss:.2f} | Better: {best_san} ({elapsed:.1f}s)"
                            elif loss <= 3.00:
                                verdict = f"❌ {san_move}: Mistake!"
                                verdict_color = "#fb923c"
                                detail = f"Loss: -{loss:.2f} | Best was: {best_san} ({elapsed:.1f}s)"
                            else:
                                verdict = f"💥 {san_move}: BLUNDER!"
                                verdict_color = "#ef4444"
                                detail = f"Loss: -{loss:.2f} | Best was: {best_san} ({elapsed:.1f}s)"

                            verdict_msg = f"{verdict}\n{detail}"
                    except Exception as e:
                        verdict_msg = f"Evaluation error: {e}"
                        verdict_color = "#ff5555"
                        self._restart_engine_locked()

            def finish_verdict():
                if self.analysis_generation != gen:
                    return
                if verdict_msg:
                    self.move_verdict_lbl.config(text=verdict_msg, fg=verdict_color)
                self._sync_book_and_engine_state(run_engine=True)

            self.root.after(0, finish_verdict)

        threading.Thread(target=worker, daemon=True).start()

    # ================= PURE ENGINE TOP 3 MOVES =================
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

    def _quick_move_order_score(self, board_obj, mv):
        score = 0
        if board_obj.is_capture(mv):
            score += 45
        if mv.promotion:
            score += 70
        if board_obj.gives_check(mv):
            score += 35
        to_sq = mv.to_square
        if chess.square_file(to_sq) in (2, 3, 4, 5) and chess.square_rank(to_sq) in (2, 3, 4, 5):
            score += 12
        return score

    def _evaluate_child_move_locked(self, board_obj, mv, time_slice, gen, depth_limit=None):
        mover_is_white = (board_obj.turn == chess.WHITE)
        san_cand = board_obj.san(mv)
        b_child = board_obj.copy(stack=False)
        b_child.push(mv)

        if b_child.is_checkmate():
            mate_str = "#M1" if mover_is_white else "#M-1"
            mate_cp = 10.0 if mover_is_white else -10.0
            return (100000, san_cand, mate_str, san_cand, mate_cp, mv), 1

        if b_child.is_stalemate() or b_child.is_insufficient_material():
            return (0, san_cand, "0.0", san_cand, 0.0, mv), 1

        info, _ = self._run_search_locked(
            b_child, time_slice, gen, collect_pvs=False, target_depth=depth_limit
        )
        if info and "score" in info:
            ev_str, ev_cp, white_sort_cp = self._format_score_white(info["score"])
            mover_sort_cp = white_sort_cp if mover_is_white else -white_sort_cp

            line_sans = [san_cand]
            tb = b_child.copy(stack=False)
            for m in info.get("pv", [])[:2]:
                if m in tb.legal_moves:
                    line_sans.append(tb.san(m))
                    tb.push(m)
                else:
                    break

            return (
                mover_sort_cp,
                san_cand,
                ev_str,
                " ".join(line_sans),
                ev_cp,
                mv,
            ), info.get("depth", 0)

        return (-50000, san_cand, "0.0", san_cand, 0.0, mv), 0

    def _compute_top3_guaranteed_locked(
        self, board_obj, gen, t_start, eff_budget, max_depth=None
    ):
        """
        Interruptible MultiPV + full-legal-move verification.
        Never drops quiet moves (evaluates ALL remaining legal moves if MultiPV
        returns fewer than 3 lines) and always ranks strictly by mover score.
        """
        legal_moves = list(board_obj.legal_moves)
        if not legal_moves:
            return [], 0

        mover_is_white = (board_obj.turn == chess.WHITE)
        target_k = min(3, len(legal_moves))
        max_depth_reached = 0
        evaluated_map = {}

        if len(legal_moves) == 1:
            entry, d = self._evaluate_child_move_locked(
                board_obj, legal_moves[0], max(0.20, eff_budget), gen, depth_limit=max_depth
            )
            return [(1, entry[1], entry[2], entry[3], entry[4], entry[5])], d

        if self.engine and "MultiPV" in self.engine.options:
            try:
                limit_kwargs = {"time": max(0.25, eff_budget)}
                if max_depth is not None:
                    limit_kwargs["depth"] = max_depth
                limit = chess.engine.Limit(**limit_kwargs)

                latest_by_mpv = {}
                with self.engine.analysis(board_obj, limit, multipv=target_k) as analysis:
                    for info in analysis:
                        if self.analysis_generation != gen:
                            analysis.stop()
                            return [], max_depth_reached
                        pv = info.get("pv", [])
                        if pv and "score" in info and pv[0] in board_obj.legal_moves:
                            mpv_idx = info.get("multipv", 1)
                            latest_by_mpv[mpv_idx] = info

                for mpv_idx in sorted(latest_by_mpv.keys()):
                    info = latest_by_mpv[mpv_idx]
                    pv = info.get("pv", [])
                    if not pv or "score" not in info:
                        continue
                    mv0 = pv[0]
                    if mv0 not in board_obj.legal_moves:
                        continue
                    max_depth_reached = max(max_depth_reached, info.get("depth", 0))
                    ev_str, ev_cp, white_sort_cp = self._format_score_white(info["score"])
                    mover_sort_cp = white_sort_cp if mover_is_white else -white_sort_cp
                    tb = board_obj.copy(stack=False)
                    line_sans = []
                    for m in pv[:3]:
                        if m in tb.legal_moves:
                            line_sans.append(tb.san(m))
                            tb.push(m)
                        else:
                            break
                    san0 = board_obj.san(mv0)
                    line_txt = " ".join(line_sans)
                    prev = evaluated_map.get(mv0)
                    if prev is None or mover_sort_cp > prev[0]:
                        evaluated_map[mv0] = (mover_sort_cp, san0, ev_str, line_txt, ev_cp, mv0)

                if len(evaluated_map) >= target_k:
                    sorted_mpv = sorted(evaluated_map.values(), key=lambda x: x[0], reverse=True)
                    results = [
                        (i + 1, san, ev_str, line_txt, ev_cp, mv0)
                        for i, (_, san, ev_str, line_txt, ev_cp, mv0) in enumerate(sorted_mpv[:target_k])
                    ]
                    return results, max_depth_reached
            except Exception:
                pass

        # Full fallback across ALL remaining legal moves (never truncate to 12!)
        remaining_moves = [m for m in legal_moves if m not in evaluated_map]
        remaining_moves.sort(
            key=lambda m: self._quick_move_order_score(board_obj, m),
            reverse=True
        )

        rem_budget = max(0.25, eff_budget - (time.monotonic() - t_start))
        screen_budget = rem_budget * 0.55
        per_screen_slice = max(0.025, screen_budget / max(1, len(remaining_moves)))

        for mv in remaining_moves:
            if self.analysis_generation != gen:
                return [], max_depth_reached
            entry, d = self._evaluate_child_move_locked(
                board_obj, mv, per_screen_slice, gen, depth_limit=max_depth
            )
            max_depth_reached = max(max_depth_reached, d)
            evaluated_map[mv] = entry

        ranked_all = sorted(evaluated_map.values(), key=lambda item: item[0], reverse=True)
        top_verify_candidates = [item[5] for item in ranked_all[:min(4, len(ranked_all))]]

        remaining_time = max(0.15, eff_budget - (time.monotonic() - t_start))
        per_verify_slice = max(0.08, remaining_time / max(1, len(top_verify_candidates)))

        for mv in top_verify_candidates:
            if self.analysis_generation != gen:
                return [], max_depth_reached
            entry, d = self._evaluate_child_move_locked(
                board_obj, mv, per_verify_slice, gen, depth_limit=max_depth
            )
            max_depth_reached = max(max_depth_reached, d)
            evaluated_map[mv] = entry

        final_entries = sorted(evaluated_map.values(), key=lambda item: item[0], reverse=True)
        results = [
            (i + 1, san, ev_str, line_txt, ev_cp, mv0)
            for i, (_, san, ev_str, line_txt, ev_cp, mv0) in enumerate(final_entries[:target_k])
        ]
        return results, max_depth_reached

    # ================= EVALUATION & TOP 3 =================
    def _on_toggle_eval_bar(self):
        if self.show_eval_var.get():
            if not self._ensure_engine_ready():
                self.show_eval_var.set(False)
                return
            self.eval_canvas.pack(side=tk.LEFT, padx=(8, 0))
            self._recalculate_layout_and_board()
            self._draw_eval_bar()
            self._sync_book_and_engine_state(run_engine=True)
        else:
            self.eval_canvas.pack_forget()
            self._recalculate_layout_and_board()
            self.eval_detail_lbl.config(text="Evaluation: disabled", fg="#777777")

    def _on_toggle_top3(self):
        cap_sec = self._get_max_time_cap()
        if self.show_top3_var.get():
            if not self._ensure_engine_ready():
                self.show_top3_var.set(False)
                return
            self._sync_book_and_engine_state(run_engine=True)
        else:
            self.top3_arrows = []
            self._draw_board()
            style_tag = self._get_active_style_tag()
            self.top3_meta_lbl.config(
                text=f"Rank: {self._get_rank_profile()['rank_short']}{style_tag} | Time: -- ({cap_sec:.1f}s)",
                fg="#60a5fa"
            )
            self._set_top3_message("Check box to calculate & show engine arrows.", "info_text")

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

        if self.flipped:
            # User is playing as BLACK -> Black bar at the BOTTOM, White bar at the TOP
            self.eval_canvas.create_rectangle(0, 0, w, white_h, fill="#f3f4f6", outline="")
            self.eval_canvas.create_rectangle(0, white_h, w, h, fill="#262626", outline="")
            self.eval_canvas.create_line(0, h // 2, w, h // 2, fill="#ef4444", width=1)

            if self.current_eval_cp < 0:
                self.eval_canvas.create_text(
                    w // 2, h - 14,
                    text=self.current_eval_text,
                    font=("Consolas", 8, "bold"),
                    fill="#ffffff"
                )
            else:
                self.eval_canvas.create_text(
                    w // 2, 14,
                    text=self.current_eval_text,
                    font=("Consolas", 8, "bold"),
                    fill="#111111"
                )
        else:
            # User is playing as WHITE -> White bar at the BOTTOM, Black bar at the TOP
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

    def _request_engine_analysis(self, skip_top3=False):
        want_top3 = self.show_top3_var.get() and not skip_top3
        want_eval = self.show_eval_var.get()

        if not (want_eval or want_top3):
            return

        if self.engine is None:
            self.pending_analysis_skip_top3 = skip_top3
            if want_top3:
                self._set_top3_message("Engine starting... will calculate automatically.", "warn_text")
            return

        self.pending_analysis_skip_top3 = None

        if not self.board.is_valid():
            if want_top3:
                self._set_top3_message("Waiting for stable board position...", "info_text")
            return

        if self.board.is_game_over():
            self.top3_arrows = []
            self._draw_board()
            if self.board.is_checkmate():
                winner = "Black" if self.board.turn == chess.WHITE else "White"
                msg = f"Checkmate! {winner} wins."
                self.current_eval_cp = -10.0 if self.board.turn == chess.WHITE else 10.0
                self.current_eval_text = "#M0"
            else:
                msg = "Game over (Draw / Stalemate)."
                self.current_eval_cp = 0.0
                self.current_eval_text = "0.0"

            if want_eval:
                self._draw_eval_bar()
                self.eval_detail_lbl.config(text=msg, fg="#00ff66")
            if want_top3:
                self._set_top3_message(msg, "info_text")
            return

        self.analysis_generation += 1
        gen = self.analysis_generation
        self.is_analyzing = True

        board_snapshot = self.board.copy(stack=False)
        fen_snapshot = board_snapshot.fen()
        prof = self._get_rank_profile()
        style_tag = self._get_active_style_tag()
        ui_start = time.monotonic()

        active_is_white = (board_snapshot.turn == chess.WHITE)
        if active_is_white:
            self.side1_header_lbl.config(text=f"⚪ WHITE{style_tag} (to move):", fg="#f8fafc")
        else:
            self.side1_header_lbl.config(text=f"⚫ BLACK{style_tag} (to move):", fg="#fbbf24")

        if want_top3:
            self.top3_meta_lbl.config(
                text=f"⏳ {prof['rank_short']}{style_tag} | 0.0s ({prof['cap_sec']:.1f}s)",
                fg="#fbbf24"
            )
            self._set_top3_message("Calculating all 3 best engine moves...", "warn_text")

        if want_eval:
            self.eval_detail_lbl.config(
                text=f"Evaluating ({prof['rank_short']}{style_tag}): calculating...",
                fg="#fbbf24"
            )

        def tick_timer():
            if not self.is_analyzing or self.analysis_generation != gen:
                return
            elapsed = time.monotonic() - ui_start
            if want_top3:
                self.top3_meta_lbl.config(
                    text=f"⏳ {prof['rank_short']}{style_tag} | {elapsed:.1f}s ({prof['cap_sec']:.1f}s)",
                    fg="#fbbf24"
                )
            self.root.after(150, tick_timer)

        self.root.after(150, tick_timer)

        threading.Thread(
            target=self._run_engine_worker,
            args=(board_snapshot, fen_snapshot, want_top3, gen, prof, style_tag),
            daemon=True
        ).start()

    def _run_engine_worker(self, board_snapshot, fen_snapshot, want_top3, gen, prof, style_tag):
        side1_lines = []
        best_eval_cp = 0.0
        best_eval_str = "0.0"
        max_reached_depth = 0
        error_msg = None
        total_elapsed = 0.0
        completed_for_gen = False

        with self.engine_lock:
            if self.engine is None or self.analysis_generation != gen:
                return
            t_start = time.monotonic()
            try:
                self._apply_rodent_difficulty_locked(force_max=False)
                legal_moves = list(board_snapshot.legal_moves)

                if not legal_moves:
                    side1_lines = []
                elif not want_top3:
                    res, _ = self._run_search_locked(
                        board_snapshot,
                        time_slice=prof["eff_budget"],
                        gen=gen,
                        collect_pvs=False,
                        target_depth=prof["max_depth"],
                    )
                    if res and "score" in res:
                        best_eval_str, best_eval_cp, _ = self._format_score_white(res["score"])
                        max_reached_depth = res.get("depth", 0)
                else:
                    side1_lines, d1 = self._compute_top3_guaranteed_locked(
                        board_snapshot,
                        gen=gen,
                        t_start=t_start,
                        eff_budget=prof["eff_budget"],
                        max_depth=prof["max_depth"],
                    )
                    max_reached_depth = max(max_reached_depth, d1)

                    if side1_lines:
                        best_eval_str = side1_lines[0][2]
                        best_eval_cp = side1_lines[0][4]
                completed_for_gen = (self.analysis_generation == gen)
            except Exception as e:
                error_msg = str(e)
                self._restart_engine_locked()
                completed_for_gen = (self.analysis_generation == gen)
            total_elapsed = time.monotonic() - t_start

        def update_ui():
            if self.analysis_generation != gen:
                return

            self.is_analyzing = False

            if self.board.fen() != fen_snapshot:
                # Board changed while worker finished -> immediately re-trigger for current board
                self._sync_book_and_engine_state(run_engine=True)
                return

            if not completed_for_gen:
                return

            if error_msg:
                self.top3_arrows = []
                self._draw_board()
                if want_top3:
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
                    text=f"Score: {best_eval_str} ({who}) [{prof['rank_short']}{style_tag}{depth_tag}, {total_elapsed:.2f}s]",
                    fg="#00ff66"
                )

            if want_top3:
                self.top3_meta_lbl.config(
                    text=f"✓ {prof['rank_short']}{style_tag} | {total_elapsed:.2f}s ({prof['cap_sec']:.1f}s){depth_tag}",
                    fg="#00d4ff"
                )

                active_is_white = (board_snapshot.turn == chess.WHITE)
                if active_is_white:
                    self.side1_header_lbl.config(text=f"⚪ WHITE{style_tag} (to move):", fg="#f8fafc")
                else:
                    self.side1_header_lbl.config(text=f"⚫ BLACK{style_tag} (to move):", fg="#fbbf24")

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

    # ================= BOARD DRAWING (COORDINATES + BOOK/ENGINE ARROWS) =================
    def _toggle_flip(self):
        self.flipped = not self.flipped
        self._draw_board()
        if self.show_eval_var.get():
            self._draw_eval_bar()

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
        self._update_pgn_display()
        self._update_nav_buttons()
        self._sync_book_and_engine_state(run_engine=True)

    def _square_to_canvas_center(self, square):
        file_idx = chess.square_file(square)
        rank_idx = chess.square_rank(square)
        col = 7 - file_idx if self.flipped else file_idx
        row = rank_idx if self.flipped else 7 - rank_idx
        sq = self.board_size / 8.0
        return (col + 0.5) * sq, (row + 0.5) * sq

    def _draw_single_arrow(self, move, color, width, arrow_shape):
        sq = self.board_size / 8.0
        x1, y1 = self._square_to_canvas_center(move.from_square)
        x2, y2 = self._square_to_canvas_center(move.to_square)

        dx = x2 - x1
        dy = y2 - y1
        dist = math.hypot(dx, dy)
        if dist < 1e-3:
            return

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

    def _draw_move_arrows(self):
        sq = self.board_size / 8.0

        # 1) When Book Moves is active and book moves exist: draw ALL possible book arrows!
        if self.show_book_var.get() and self.current_book_moves:
            total = len(self.current_book_moves)
            for idx in range(total - 1, -1, -1):
                mv = self.current_book_moves[idx][0]
                color = BOOK_ARROW_PALETTE[min(idx, len(BOOK_ARROW_PALETTE) - 1)]
                if idx == 0:
                    width = max(8, round(sq * 0.20))
                    arrow_shape = (round(sq * 0.32), round(sq * 0.36), round(sq * 0.20))
                elif idx == 1:
                    width = max(5, round(sq * 0.13))
                    arrow_shape = (round(sq * 0.24), round(sq * 0.27), round(sq * 0.14))
                elif idx == 2:
                    width = max(3.5, round(sq * 0.085))
                    arrow_shape = (round(sq * 0.19), round(sq * 0.22), round(sq * 0.11))
                else:
                    width = max(2.2, round(sq * 0.055))
                    arrow_shape = (round(sq * 0.15), round(sq * 0.18), round(sq * 0.09))

                self._draw_single_arrow(mv, color, width, arrow_shape)
            return

        # 2) Otherwise, if Top 3 Engine Moves is active, draw the 3 engine arrows
        if not self.show_top3_var.get() or not self.top3_arrows:
            return

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
            self._draw_single_arrow(move, color, width, arrow_shape)

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

                if col == 0:
                    self.canvas.create_text(
                        x1 + coord_pad,
                        y1 + coord_pad,
                        text=str(rank_idx + 1),
                        anchor="nw",
                        font=("Consolas", coord_px, "bold"),
                        fill=coord_fg
                    )

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