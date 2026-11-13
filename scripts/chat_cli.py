"""Talk to the agent in the terminal (no audio, no server).  Needs ANTHROPIC_API_KEY.
Run:  python scripts/chat_cli.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import agent  # noqa: E402

sid = "cli"
print("Type a message (Ctrl+C to quit). Tool calls are shown in grey.\n")
while True:
    try:
        msg = input("You: ").strip()
    except (KeyboardInterrupt, EOFError):
        break
    if not msg:
        continue
    out = agent.chat(sid, msg)
    for t in out["tool_calls"]:
        print(f"\033[90m  -> {t['tool']}({t['input']})\033[0m")
    print(f"Assistant: {out['reply']}\n")
