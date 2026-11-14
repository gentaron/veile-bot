import os

from linebot import LineBotApi
from linebot.models import TextSendMessage


def main():
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    user_id = os.environ.get("LINE_USER_ID")
    if not token or not user_id:
        raise RuntimeError("LINE_CHANNEL_ACCESS_TOKEN and LINE_USER_ID are required")

    line_bot_api = LineBotApi(token)
    line_bot_api.push_message(
        user_id,
        TextSendMessage(text="おはよう～ \n 今日も頑張っていきましょう！"),
    )


if __name__ == "__main__":
    main()
