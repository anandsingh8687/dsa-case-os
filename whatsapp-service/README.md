# WhatsApp Service for DSA Case OS

## Overview

This Node.js microservice provides WhatsApp integration for the DSA Case OS platform using WhatsApp Web.js.

## Features

- ✅ QR code generation for WhatsApp linking
- ✅ Send messages to customers
- ✅ Session management per case
- ✅ Health check endpoint

## API Endpoints

### Health Check
```
GET /health
```

### Generate QR Code
```
POST /generate-qr
Body: { "caseId": "CASE-20260210-0014" }
Response: { "success": true, "sessionId": "...", "qrCode": "data:image/png;base64,..." }
```

### Get Session Status
```
GET /session/:sessionId
Response: { "sessionId": "...", "status": "ready", "linkedNumber": "..." }
```

### Send Message
```
POST /send-message
Body: { "sessionId": "...", "to": "919876543210", "message": "Hello!" }
Response: { "success": true, "messageId": "..." }
```

## Running Locally

```bash
npm install
npm start
```

## Running with Docker

```bash
docker build -t dsa-whatsapp .
docker run -p 3001:3001 dsa-whatsapp
```

## Environment Variables

- `PORT` - Server port (default: 3001)

## Dependencies

- `express` - Web framework
- `whatsapp-web.js` - WhatsApp Web API
- `qrcode` - QR code generation
- `puppeteer` - Browser automation (bundled with whatsapp-web.js)

## Session Storage

Sessions are stored in memory. For production, consider using Redis or database-backed storage.

## Notes

- Each case gets its own WhatsApp session
- QR codes are generated on-demand
- Sessions persist until explicitly disconnected
- Chrome/Puppeteer runs in headless mode inside Docker
