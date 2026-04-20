# Connecting AeroTriage to WhatsApp

You can connect WhatsApp so that:

1. **Incoming** messages from a patient are treated as symptoms, run through triage, and the patient is added to the queue (with their number stored as `mobile`).
2. **Outgoing** messages to the patient’s number send queue position and expected wait (e.g. “You are position 3. Expected wait ~10 min.”).

## Options

| Option | Use case | Notes |
|--------|----------|--------|
| **Twilio WhatsApp Sandbox** | Quick testing | Twilio gives you a sandbox number; users send a join code to opt in. |
| **Twilio WhatsApp API (production)** | Production | Requires WhatsApp Business API approval and Twilio number. |
| **WhatsApp Business API (Meta)** | Production | Direct Meta integration; more setup. |

Below we assume **Twilio** (sandbox or production). The same webhook and backend logic work for any provider that can send HTTP POST to your server.

## 1. Backend: webhook and triage

The app already has:

- **POST /triage**  
  Body: `{ "symptoms": "text", "mobile": "+1234567890" }`  
  Runs the full pipeline and stores the patient with `mobile`. Response includes `patient_id`, `severity`, `queue_position`, etc.

- **GET /queue**  
  Returns the ordered queue; each entry has `mobile`, `expected_wait_minutes`, `position`.

So the backend can:

- Accept an **incoming** WhatsApp event (via Twilio webhook), take the message body as `symptoms` and the sender as `mobile`, and call the same triage logic.
- Use the triage response + GET /queue to build a **reply** (position, expected wait) and send it back via Twilio’s API.

## 2. Webhook endpoint (Twilio-style)

Twilio sends a **POST** to your URL with form fields such as:

- `Body` — message text (patient’s symptoms).
- `From` — sender’s WhatsApp number (e.g. `whatsapp:+919876543210`).

**POST /webhooks/whatsapp**:

1. Accepts `application/x-www-form-urlencoded`: `Body` (message text), `From` (sender number).
2. Multi-step flow: first message (symptoms) → triage result and expected wait (no queue yet) → user replies **YES** → prompt for name → prompt for phone → create patient, add to queue, reply with “Appointment confirmed” and expected wait (from learned queue logic).
3. Returns **TwiML** so Twilio sends the reply in the same request.

Your server must be **publicly reachable** (e.g. ngrok) for Twilio to call this URL.

### Development: ngrok (no code install)

- Do **not** install or run ngrok from application code.
- From your machine, run: **`ngrok http 8000`** (with the backend running on port 8000).
- Copy the HTTPS URL ngrok shows (e.g. `https://abc123.ngrok.io`).
- In Twilio, set the webhook URL to: **`https://<ngrok-url>/webhooks/whatsapp`** (e.g. `https://abc123.ngrok.io/webhooks/whatsapp`).

## 3. Twilio setup (high level)

1. **Twilio account**  
   Sign up at twilio.com, get Account SID and Auth Token.

2. **WhatsApp Sandbox**  
   In Twilio Console → Messaging → Try it out → Send a WhatsApp message. Follow the steps to join the sandbox (send the join code from your phone).

3. **Webhook URL**  
   When configuring the sandbox (or your WhatsApp number), set “When a message comes in” to:  
   `https://YOUR_PUBLIC_URL/webhooks/whatsapp`  
   Method: POST.

4. **Environment**  
   Set `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, and optionally `TWILIO_WHATSAPP_FROM` (e.g. `whatsapp:+14155238886` for sandbox). The webhook uses these to send the reply via Twilio’s API.

## 4. Sending the reply (Twilio API)

The webhook returns TwiML so Twilio sends the reply in the same request. If you prefer to send the reply in a **second** request (e.g. after async processing), you can call Twilio’s REST API from your backend:

```text
POST https://api.twilio.com/2010-04-01/Accounts/{AccountSid}/Messages.json
Body: To=whatsapp:+919876543210&From=whatsapp:+14155238886&Body=You are position 3. Expected wait ~10 min.
Auth: Basic base64(AccountSid:AuthToken)
```

Use the `mobile` you stored (e.g. `whatsapp:+919876543210`) as `To`, and your Twilio WhatsApp number as `From`.

## 5. Flow summary

1. Patient sends: “I have chest pain.” → Twilio POSTs to **POST /webhooks/whatsapp** with `Body` and `From`.
2. Backend runs triage in **preview mode** (no patient/queue yet); replies with severity band (e.g. High 4/5), short advice, expected wait (from learned queue logic), and “Reply YES to confirm.”
3. Patient replies **YES** → backend asks: “Please enter your name.”
4. Patient sends name → backend asks: “Please confirm your phone number or type a new one.”
5. Patient sends phone (or confirms) → backend creates patient, adds to queue, stores reasoning; replies: “Appointment confirmed. Expected wait: ~X min.” (X from learned queue data).

Conversation state is stored in Redis (key `whatsapp:conv:{From}`) with TTL 1 hour. Expected wait is never hardcoded; it uses the same learned averages as GET /queue.

For implementation details, see the route in **backend/main.py**, **backend/whatsapp_handler.py**, and **backend/whatsapp_state.py**.
