# Waypoint Agentic UI Guide

## What's New

Waypoint now features a **conversational, agentic interface** powered by OpenAI GPT-4:

### 🗣️ Natural Conversation
- Tell your story in your own words
- Complain about the cancellation
- Ask questions about options
- Get empathetic responses

### 🎤 Voice Input
- Click the microphone button
- Speak your situation
- Automatic speech-to-text conversion
- Works in Chrome, Edge, and Safari

### 📷 Image Analysis
- Upload boarding pass photos
- Take pictures of cancellation notices
- GPT-4 Vision extracts flight details automatically
- No manual data entry needed

### 💬 Conversational Flow
1. **Tell me what happened** — Describe your cancellation in your own words
2. **I'll understand** — GPT-4 extracts the details (origin, destination, times, etc.)
3. **Here are your options** — Ranked flights appear with tradeoffs
4. **Which one works?** — Just tell me "I'll take option 2"
5. **Approve checkpoints** — Review and approve each step
6. **Done!** — Ticket issued, audit trail ready

## Setup

### 1. Get Your OpenAI API Key

1. Go to https://platform.openai.com/api-keys
2. Sign in or create an account
3. Click "Create new secret key"
4. Copy the key (starts with `sk-...`)

### 2. Add Key to .env

Edit the `.env` file in the waypoint directory:

```bash
OPENAI_API_KEY=sk-your-actual-key-here
```

### 3. Run the App

```bash
cd /Users/prakash/Atlas/waypoint
source venv/bin/activate
python run.py
```

Open http://localhost:5000

## Usage Examples

### Example 1: Conversational

**You:** "My flight from KUL to SIN got cancelled! I was supposed to leave tomorrow at 8am and I have a meeting at 9am, I really need to get there!"

**Waypoint:** "I completely understand how frustrating this must be. Missing a meeting is stressful. Let me help you find a replacement flight right away.

I see you need to get from KUL to SIN, departing tomorrow around 8am, and you must arrive before 9am for your meeting. Let me search for options that can get you there on time."

*[Shows ranked options]*

### Example 2: Voice Input

1. Click 🎤 button
2. Say: "My flight AK700 from Kuala Lumpur to Singapore was cancelled. I need to get there by 1pm tomorrow."
3. Click 🎤 again to stop
4. Waypoint extracts details and searches

### Example 3: Image Upload

1. Click 📷 button
2. Take photo of boarding pass or cancellation email
3. Waypoint analyzes with GPT-4 Vision
4. Extracts PNR, flight number, airports, times
5. Starts search automatically

### Example 4: Mixed Input

**You:** *[uploads image]* "Here's my booking confirmation. The airline just emailed me saying it's cancelled."

**Waypoint:** "I've analyzed your booking confirmation. I can see:
- Booking reference: ABC123
- Flight: AK700
- Route: KUL to SIN
- Departure: September 15, 2026 at 08:00

I'm sorry about the cancellation. Let me find you replacement options right away."

## Features

### Intelligent Extraction

GPT-4 understands natural language and extracts:
- Airport codes (IATA or city names)
- Dates and times (any format)
- Number of passengers
- Hard deadlines ("must arrive before...")
- Booking references (PNR)
- Flight numbers

### Empathetic Responses

The agent:
- Acknowledges your frustration
- Validates your concerns
- Explains what it's doing
- Asks clarifying questions when needed

### Image Analysis

GPT-4 Vision can read:
- Boarding passes
- Booking confirmations
- Cancellation emails
- Screenshots of flight details
- Handwritten notes

### Conversational Checkpoints

Instead of rigid forms, checkpoints appear in the conversation:

**Waypoint:** "I found a great option — AK700 departing at 8:15am, arriving 9:15am, $220. This gets you to your meeting on time. I need your approval to proceed with booking. Take a look at the checkpoint card above and let me know if you approve."

**You:** "Looks good, approved!"

**Waypoint:** "Perfect! Verifying the offer now..."

## Technical Details

### Voice Recognition
- Uses Web Speech API
- Works in modern browsers
- No additional setup needed
- Falls back to text input if unavailable

### Image Processing
- Images sent to GPT-4 Vision API
- Base64 encoding for upload
- Supports JPEG, PNG, GIF
- Max size: 20MB

### Conversation Memory
- Context maintained across messages
- Extracted details confirmed with user
- Can handle corrections ("Actually, I meant 2 passengers")

### Error Handling
- Graceful fallback if OpenAI unavailable
- Clear error messages
- Retry suggestions

## API Endpoints

```bash
# Chat with the agent
POST /api/chat
{
  "message": "My flight was cancelled..."
}

# Analyze image
POST /api/analyze-image
{
  "image": "base64-encoded-image-data"
}

# All other endpoints remain the same
```

## Troubleshooting

### "I'm having trouble connecting right now"
- Check your OPENAI_API_KEY in .env
- Verify the key starts with `sk-`
- Ensure you have OpenAI API credits

### Voice input not working
- Use Chrome, Edge, or Safari
- Allow microphone permissions
- Check browser console for errors

### Image analysis fails
- Ensure image is clear and readable
- Try different lighting
- Check file size (max 20MB)
- Supported formats: JPEG, PNG, GIF

### "No API key provided"
- Make sure .env file exists
- Restart the Flask server after adding key
- Check for typos in the key

## Cost Considerations

OpenAI API usage (approximate):
- Chat message: ~$0.01-0.03
- Image analysis: ~$0.03-0.05
- Full booking flow: ~$0.20-0.50

For a hackathon demo, costs are minimal. For production, consider:
- Caching common responses
- Using GPT-3.5 for simple queries
- Rate limiting
- User quotas

## Next Steps

1. Add your OpenAI API key to `.env`
2. Run the app: `python run.py`
3. Try the conversational interface
4. Test voice input
5. Upload a boarding pass photo
6. Complete a full booking flow

Enjoy the agentic experience! 🚀
