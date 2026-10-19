
import re


MESSAGE_PATTERN = re.compile(
    r"^(?:"
    r"\[(?P<ios_date>\d{1,2}/\d{1,2}/\d{2,4}),\s*"
    r"(?P<ios_time>\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM)?)\]\s*"
    r"(?P<ios_content>.*)"
    r"|"
    r"(?P<android_date>\d{1,2}/\d{1,2}/\d{2,4}),\s*"
    r"(?P<android_time>\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM)?)\s*-\s*"
    r"(?P<android_content>.*)"
    r")$",
    re.IGNORECASE,
)


def parse_whatsapp_text(raw_text: str) -> list[dict]:
    messages = []
    current = None

    for line in raw_text.splitlines():
        match = MESSAGE_PATTERN.match(line)

        if match:
            if current is not None:
                messages.append(current)

            date = match.group("ios_date") or match.group("android_date")
            time = match.group("ios_time") or match.group("android_time")
            content = (
                match.group("ios_content")
                if match.group("ios_content") is not None
                else match.group("android_content")
            )

            # A message normally has the form "Sender: message".
            if ": " in content:
                sender, text = content.split(": ", 1)
            else:
                sender, text = "System", content

            current = {
                "message_id": len(messages) + 1,
                "timestamp_text": f"{date}, {time}",
                "sender": sender,
                "text": text,
            }

        elif current is not None:
            # Attach continuation lines to the previous message.
            current["text"] += "\n" + line

    if current is not None:
        messages.append(current)

    return messages
