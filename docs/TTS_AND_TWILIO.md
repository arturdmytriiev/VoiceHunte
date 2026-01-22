# TTS and Twilio Integration Guide

## Overview

VoiceHunte now includes:
- **OpenAI TTS Streaming** - Real-time text-to-speech conversion
- **Twilio Voice Integration** - Handle phone calls with voice AI

## TTS (Text-to-Speech) API

### Endpoint: `POST /tts/stream`

Stream audio from OpenAI TTS in real-time.

**Request Body:**
```json
{
  "text": "Hello! Welcome to our restaurant.",
  "voice": "alloy",
  "model": "tts-1",
  "response_format": "mp3",
  "speed": 1.0
}
```

**Parameters:**
- `text` (required): Text to convert to speech
- `voice` (optional): Voice to use - `alloy`, `echo`, `fable`, `onyx`, `nova`, `shimmer` (default: `alloy`)
- `model` (optional): `tts-1` or `tts-1-hd` (default: `tts-1`)
- `response_format` (optional): `mp3`, `opus`, `aac`, `flac`, `wav`, `pcm` (default: `mp3`)
- `speed` (optional): Speech speed from 0.25 to 4.0 (default: 1.0)

**Response:**
- Streaming audio in the specified format
- Content-Type: `audio/mpeg` (or appropriate type)

**Example using curl:**
```bash
curl -X POST http://localhost:8000/tts/stream \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello from VoiceHunte!", "voice": "nova"}' \
  --output response.mp3
```

**Example using Python:**
```python
import requests

response = requests.post(
    "http://localhost:8000/tts/stream",
    json={
        "text": "Hello! How can I help you today?",
        "voice": "alloy",
        "response_format": "mp3"
    },
    stream=True
)

with open("output.mp3", "wb") as f:
    for chunk in response.iter_content(chunk_size=4096):
        if chunk:
            f.write(chunk)
```

## Twilio Voice Integration

### Setup

1. **Install Dependencies:**
```bash
poetry install
```

2. **Configure Environment Variables:**
```bash
TWILIO_ACCOUNT_SID=your_account_sid
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_PHONE_NUMBER=your_twilio_phone_number
OPENAI_API_KEY=your_openai_api_key
```

3. **Configure Twilio Webhooks:**

In your Twilio Console, configure your phone number webhooks:

**Voice Configuration:**
- When a call comes in: `POST https://yourdomain.com/twilio/incoming`
- Status callback: `POST https://yourdomain.com/twilio/status`

### Webhook Endpoints

#### 1. `POST /twilio/incoming`
Handles incoming phone calls.

**Twilio automatically sends:**
- `CallSid`: Unique call identifier
- `From`: Caller's phone number
- `To`: Called phone number

**Returns:** TwiML response with initial greeting and speech gathering

#### 2. `POST /twilio/voice`
Processes voice input from callers.

**Twilio automatically sends:**
- `SpeechResult`: Transcribed speech from caller
- `CallSid`: Call identifier
- `Confidence`: Speech recognition confidence (0-1)

**Returns:** TwiML response with AI-generated answer

#### 3. `POST /twilio/status`
Receives call status updates (ringing, in-progress, completed, etc.)

**Twilio automatically sends:**
- `CallSid`: Call identifier
- `CallStatus`: Current status

### Call Flow

```
1. User calls Twilio number
   ↓
2. Twilio sends webhook to /twilio/incoming
   ↓
3. VoiceHunte returns TwiML greeting
   ↓
4. User speaks
   ↓
5. Twilio transcribes speech, sends to /twilio/voice
   ↓
6. VoiceHunte processes with AI agent
   ↓
7. Returns TwiML with response
   ↓
8. Repeat 4-7 if clarification needed
   ↓
9. Call ends
```

### TwiML Response Format

VoiceHunte uses Amazon Polly voices through Twilio:

**Supported Languages:**
- English: `Polly.Joanna`
- Russian: `Polly.Tatyana`
- Ukrainian: `Polly.Tatyana` (fallback)
- Slovak: `Polly.Maja` (Polish fallback)

### Local Development with ngrok

For testing Twilio webhooks locally:

```bash
# Start ngrok
ngrok http 8000

# Copy the HTTPS URL (e.g., https://abc123.ngrok.io)
# Configure in Twilio Console:
# - Incoming call: https://abc123.ngrok.io/twilio/incoming
# - Status callback: https://abc123.ngrok.io/twilio/status
```

### Testing

**Test TTS endpoint:**
```bash
curl -X POST http://localhost:8000/tts/stream \
  -H "Content-Type: application/json" \
  -d '{"text": "Testing TTS", "voice": "nova"}' \
  -o test.mp3 && afplay test.mp3  # Mac
```

**Test with Twilio:**
1. Configure webhooks in Twilio Console
2. Call your Twilio phone number
3. Follow voice prompts
4. Check logs: `docker compose logs -f api`

### Conversation Storage

All phone calls are stored in the database:
- Call metadata in `calls` table
- Each turn (user input + AI response) in `turns` table
- Audio files referenced in `audio_files` table

Query call history:
```sql
SELECT * FROM calls WHERE call_id = 'CA1234567890abcdef';
SELECT * FROM turns WHERE call_id = 'CA1234567890abcdef' ORDER BY turn_id;
```

### Error Handling

The system handles:
- **Empty speech**: Asks user to repeat
- **Low confidence**: Still processes (can add threshold)
- **Missing entities**: Asks clarifying questions
- **API failures**: Returns graceful error message

### Production Considerations

1. **Security**: Validate Twilio requests using signature verification
2. **Rate Limiting**: Implement per-number rate limits
3. **Monitoring**: Track call duration, transcription accuracy, agent performance
4. **Costs**: Monitor OpenAI API usage (Whisper for STT, TTS for voice)
5. **Scaling**: Use async processing for long-running calls

### Next Steps

- [ ] Add signature verification for Twilio webhooks
- [ ] Implement WebSocket streaming for real-time conversations
- [ ] Add call recording storage to S3/Cloud Storage
- [ ] Create admin dashboard for call analytics
- [ ] Add multi-language voice selection based on detected language
- [ ] Implement voice biometrics for customer identification
