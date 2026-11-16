# ♟️ Chess.com HTML Live Tracker + Rodent IV

A real-time desktop chess companion and analysis board for **Chess.com**. Instead of relying on fragile screen capture or OCR, it reads the board state, move history, and square highlights directly from the browser's DOM via a lightweight local HTTP bridge, pairing live synchronization with the **Rodent IV** UCI chess engine.

---

## ✨ Features

- **100% Accurate HTML Sync:** Reads pieces, board orientation, highlights, and move lists directly from Chess.com in real time (Chrome, Edge, and Firefox supported).
- **Full History Navigation:** Step backward or forward through previous moves on Chess.com—the tracker automatically detects which ply you are viewing and updates turn rights and evaluations accordingly.
- **Dual Top-3 Move Suggestions:** Displays the **Top 3 distinct best moves for both White and Black** after every move, capped at a strict **5-second** total calculation window.
- **Live Position Evaluation Bar:** Dynamic centipawn/mate evaluation bar synced to the active position.
- **Adjustable Engine Strength:** Scale Rodent IV's playing strength from **800 Elo** up to **MAX (~2975 Elo)**.
- **"Try Move" Sandbox Mode:** Pause live sync at any moment to test hypothetical moves directly on the board and get instant move classifications (*Best Move, Excellent, Good, Inaccuracy, Mistake, Blunder*), then return to the live match with one click.
- **Responsive Resizable UI:** Resize or maximize the window freely—the chessboard and evaluation bar scale dynamically while keeping controls compact.

---

## 📁 Expected Folder Structure

```text
ChessReader/
├── chess_tracker.py        # Main application
├── chess_extension/        # Auto-generated Manifest V3 browser extension on first run
├── Rodent_IV/              # Engine folder (downloaded separately - see tutorial below)
│   ├── rodent-iv-x64.exe
│   ├── books/
│   └── personalities/
└── README.md
```

---

## 🚀 Installation

### 1. Prerequisites & Python Dependencies

Make sure you have **Python 3.8+** installed (with `tkinter` enabled, which is included by default on Windows).

1. Clone this repository:
   ```bash
   git clone https://github.com/mihneavk/ChessTracker.git
   cd ChessTracker
   ```
2. Install the required Python libraries:
   ```bash
   pip install chess numpy
   ```

---

### 2. Installing the Rodent IV Engine (Required)

> **Note:** Due to engine redistribution and licensing rules, the **Rodent IV** binaries are not included in this repository and must be downloaded separately.

1. Download the official **Rodent IV** archive (`FinalRodent.7z`) directly from the author's website:  
   👉 [http://www.pkoziol.cal24.pl/rodent/FinalRodent.7z](http://www.pkoziol.cal24.pl/rodent/FinalRodent.7z)
2. Extract the contents of **`FinalRodent.7z`** (using 7-Zip, WinRAR, or Windows 11's built-in archive extractor) into a folder named **`Rodent_IV`** inside the main project directory (next to `chess_tracker.py`).
3. Verify that the executable path looks like this:
   ```text
   ChessReader/Rodent_IV/rodent-iv-x64.exe
   ```
   *(Keep the accompanying `personalities/` and `books/` folders inside `Rodent_IV/` so the engine loads its configuration properly.)*

> **Alternative / Custom Engines:**  
> If you place `rodent-iv-x64.exe` in a different folder—or if you want to use another UCI engine such as **Stockfish**—launch the app, click **`⚙ Change Engine (.exe)`** in the top-right panel, and select your engine executable manually.

---

## 🌐 Connecting Your Browser (Chrome / Edge / Firefox)

1. Start the Python application:
   ```bash
   python chess_tracker.py
   ```
   *(On first launch, the app automatically generates the `chess_extension/` folder.)*

2. Choose one of the two connection methods:

### Method A: Local Browser Extension (Recommended)
- **Chrome / Edge:**
  1. Open `chrome://extensions` (or `edge://extensions`).
  2. Enable **Developer mode** in the top-right corner.
  3. Click **Load unpacked** and select the generated **`chess_extension`** folder.
- **Firefox:**
  1. Open `about:debugging#/runtime/this-firefox`.
  2. Click **Load Temporary Add-on...** and select `manifest.json` inside the **`chess_extension`** folder.

### Method B: Tampermonkey Userscript
1. Install the **Tampermonkey** extension in your browser *(in Chrome, make sure **Developer mode** and **Allow User Scripts** are enabled under `chrome://extensions` -> Tampermonkey -> Details)*.
2. In the app, click **`🌐 Connect Browser (HTML)`** -> **`📋 Copy Tampermonkey Script`**.
3. Create a new script in Tampermonkey, paste the code, and press **`Ctrl + S`** to save.

3. Open **Chess.com** (or refresh your active tab with `F5`). The badge at the top of the app will turn green (**`● HTML Connected`**).

---

## ⚠️ Disclaimer

This tool is intended strictly for **post-game analysis, study, and offline/unrated practice**. Do not use engine assistance during rated online games, as doing so violates Chess.com's Fair Play Policy.
