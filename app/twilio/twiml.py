from __future__ import annotations

from typing import Any


def create_twiml_response(
    *,
    say: str | None = None,
    play: str | None = None,
    gather: dict[str, Any] | None = None,
    hangup: bool = False,
) -> str:
    """
    Create TwiML response for Twilio.

    Args:
        say: Text to say (uses Polly by default)
        play: URL of audio file to play
        gather: Configuration for gathering user input
        hangup: Whether to hangup after

    Returns:
        TwiML XML string
    """
    parts = ['<?xml version="1.0" encoding="UTF-8"?>', '<Response>']

    if gather:
        parts.append(_build_gather(gather))

    if say:
        voice = gather.get("voice", "Polly.Joanna") if gather else "Polly.Joanna"
        language = gather.get("language", "en-US") if gather else "en-US"
        parts.append(f'  <Say voice="{voice}" language="{language}">{_escape_xml(say)}</Say>')

    if play:
        parts.append(f'  <Play>{_escape_xml(play)}</Play>')

    if hangup:
        parts.append('  <Hangup/>')

    parts.append('</Response>')
    return '\n'.join(parts)


def _build_gather(config: dict[str, Any]) -> str:
    """Build <Gather> element."""
    input_type = config.get("input", "speech")
    action = config.get("action", "/twilio/voice")
    method = config.get("method", "POST")
    timeout = config.get("timeout", 3)
    language = config.get("language", "en-US")
    speech_timeout = config.get("speech_timeout", "auto")
    speech_model = config.get("speech_model", "phone_call")

    attrs = [
        f'input="{input_type}"',
        f'action="{action}"',
        f'method="{method}"',
        f'timeout="{timeout}"',
        f'language="{language}"',
        f'speechTimeout="{speech_timeout}"',
        f'speechModel="{speech_model}"',
    ]

    say_text = config.get("say")
    play_url = config.get("play")

    if say_text or play_url:
        parts = [f'  <Gather {" ".join(attrs)}>']
        if say_text:
            voice = config.get("voice", "Polly.Joanna")
            parts.append(
                f'    <Say voice="{voice}" language="{language}">{_escape_xml(say_text)}</Say>'
            )
        if play_url:
            parts.append(f'    <Play>{_escape_xml(play_url)}</Play>')
        parts.append("  </Gather>")
        return "\n".join(parts)

    return f'  <Gather {" ".join(attrs)}/>'


def _escape_xml(text: str) -> str:
    """Escape XML special characters."""
    return (
        text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def create_stream_twiml(*, stream_url: str, track: str = "both_tracks") -> str:
    """
    Create TwiML for media streaming.

    Args:
        stream_url: WebSocket URL for streaming
        track: Which audio track to stream (inbound_track, outbound_track, both_tracks)

    Returns:
        TwiML XML string
    """
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Start>
    <Stream url="{_escape_xml(stream_url)}" track="{track}"/>
  </Start>
  <Pause length="60"/>
</Response>"""


def get_polly_voice(language: str) -> str:
    """Get appropriate Polly voice for language."""
    voice_map = {
        "en": "Polly.Joanna",
        "ru": "Polly.Tatyana",
        "uk": "Polly.Tatyana",  # No Ukrainian voice, use Russian
        "sk": "Polly.Maja",  # Polish as fallback for Slovak
    }
    lang_code = language[:2] if language else "en"
    return voice_map.get(lang_code, "Polly.Joanna")


def get_twilio_language(language: str) -> str:
    """Map language code to Twilio locale."""
    lang_code = language[:2] if language else "en"
    locale_map = {
        "en": "en-US",
        "ru": "ru-RU",
        "uk": "uk-UA",
        "sk": "sk-SK",
    }
    return locale_map.get(lang_code, "en-US")
