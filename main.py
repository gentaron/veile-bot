"""後方互換のシム。

旧 ``python main.py`` は info.json に直書きしたトークンで固定文言を push して
いた。実体は ``veile_bot`` パッケージへ移したので、ここは CLI に委譲する。

    python -m veile_bot run --dry-run
"""

from __future__ import annotations

import sys

from veile_bot.cli import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or ["run"]))
