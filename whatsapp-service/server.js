/**
 * WhatsApp Service for DSA Case OS
 * 
 * Provides QR code generation and message sending capabilities
 * using WhatsApp Web.js
 */

const express = require('express');
const bodyParser = require('body-parser');
const cors = require('cors');
const { Client, LocalAuth } = require('whatsapp-web.js');
const QRCode = require('qrcode');

const app = express();
const PORT = process.env.PORT || 3001;

// Middleware
app.use(cors());
app.use(bodyParser.json());

// In-memory session storage (case_id -> session)
const sessions = new Map();

// Session status: 'initializing', 'qr_generated', 'ready', 'disconnected'

// ====================================================================
// HEALTH CHECK
// ====================================================================
app.get('/health', (req, res) => {
  res.json({ status: 'ok', service: 'whatsapp', timestamp: new Date().toISOString() });
});

// ====================================================================
// GENERATE QR CODE
// ====================================================================
app.post('/generate-qr', async (req, res) => {
  const { caseId } = req.body;

  if (!caseId) {
    return res.status(400).json({ success: false, error: 'caseId is required' });
  }

  console.log(`[${caseId}] Generating QR code...`);

  try {
    // Check if session already exists
    const existingSession = sessions.get(caseId);

    if (existingSession) {
      console.log(`[${caseId}] Session already exists with status: ${existingSession.status}`);

      // If already ready, return success immediately
      if (existingSession.status === 'ready') {
        return res.json({
          success: true,
          sessionId: existingSession.sessionId,
          qrCode: null,
          status: 'ready',
          linkedNumber: existingSession.linkedNumber
        });
      }

      // If has QR code, return it
      if (existingSession.qrCode) {
        return res.json({
          success: true,
          sessionId: existingSession.sessionId,
          qrCode: existingSession.qrCode,
          status: existingSession.status
        });
      }

      // If initializing, destroy old client and create new
      console.log(`[${caseId}] Destroying old session to create new one`);
      try {
        await existingSession.client.destroy();
      } catch (e) {
        console.log(`[${caseId}] Error destroying old client:`, e.message);
      }
      sessions.delete(caseId);
    }

    // Create new WhatsApp client for this case
    const client = new Client({
      authStrategy: new LocalAuth({ clientId: caseId }),
      puppeteer: {
        headless: true,
        executablePath: process.env.PUPPETEER_EXECUTABLE_PATH || '/usr/bin/chromium',
        args: [
          '--no-sandbox',
          '--disable-setuid-sandbox',
          '--disable-dev-shm-usage',
          '--disable-accelerated-2d-canvas',
          '--no-first-run',
          '--no-zygote',
          '--disable-gpu'
        ]
      }
    });

    let qrCodeData = null;
    const sessionId = `whatsapp_${caseId}_${Date.now()}`;

    // Store session
    sessions.set(caseId, {
      sessionId,
      caseId,
      client,
      status: 'initializing',
      qrCode: null,
      linkedNumber: null
    });

    // QR code event
    client.on('qr', async (qr) => {
      console.log(`[${caseId}] QR code received`);
      
      // Generate base64 QR code image
      qrCodeData = await QRCode.toDataURL(qr);
      
      // Update session
      const session = sessions.get(caseId);
      session.qrCode = qrCodeData;
      session.status = 'qr_generated';
      sessions.set(caseId, session);
    });

    // Ready event (WhatsApp linked)
    client.on('ready', () => {
      console.log(`[${caseId}] WhatsApp client ready!`);
      const session = sessions.get(caseId);
      session.status = 'ready';
      session.linkedNumber = client.info.wid.user; // Phone number
      sessions.set(caseId, session);
    });

    // Disconnected event
    client.on('disconnected', (reason) => {
      console.log(`[${caseId}] WhatsApp disconnected:`, reason);
      const session = sessions.get(caseId);
      if (session) {
        session.status = 'disconnected';
        sessions.set(caseId, session);
      }
    });

    // Initialize client
    client.initialize();

    // Wait for QR code (max 10 seconds)
    const maxWait = 10000;
    const checkInterval = 500;
    let waited = 0;

    while (!qrCodeData && waited < maxWait) {
      await new Promise(resolve => setTimeout(resolve, checkInterval));
      waited += checkInterval;
      const session = sessions.get(caseId);
      if (session && session.qrCode) {
        qrCodeData = session.qrCode;
      }
    }

    if (!qrCodeData) {
      return res.status(500).json({ 
        success: false, 
        error: 'QR code generation timeout' 
      });
    }

    res.json({
      success: true,
      sessionId,
      qrCode: qrCodeData,
      status: 'qr_generated'
    });

  } catch (error) {
    console.error(`[${caseId}] Error generating QR:`, error);

    // If browser already running error, clean up and suggest retry
    if (error.message && error.message.includes('browser is already running')) {
      console.log(`[${caseId}] Browser already running, cleaning up session`);
      sessions.delete(caseId);
      return res.status(500).json({
        success: false,
        error: 'Session conflict - please try again in a few seconds'
      });
    }

    res.status(500).json({
      success: false,
      error: error.message
    });
  }
});

// ====================================================================
// GET SESSION STATUS
// ====================================================================
app.get('/session/:sessionId', (req, res) => {
  const { sessionId } = req.params;

  // Find session by sessionId
  let foundSession = null;
  for (const [caseId, session] of sessions.entries()) {
    if (session.sessionId === sessionId) {
      foundSession = session;
      break;
    }
  }

  if (!foundSession) {
    return res.status(404).json({ error: 'Session not found' });
  }

  res.json({
    sessionId: foundSession.sessionId,
    caseId: foundSession.caseId,
    status: foundSession.status,
    linkedNumber: foundSession.linkedNumber,
    hasQrCode: !!foundSession.qrCode
  });
});

// ====================================================================
// SEND MESSAGE
// ====================================================================
app.post('/send-message', async (req, res) => {
  const { sessionId, to, message } = req.body;

  if (!sessionId || !to || !message) {
    return res.status(400).json({ 
      success: false, 
      error: 'sessionId, to, and message are required' 
    });
  }

  // Find session
  let foundSession = null;
  for (const [caseId, session] of sessions.entries()) {
    if (session.sessionId === sessionId) {
      foundSession = session;
      break;
    }
  }

  if (!foundSession) {
    return res.status(404).json({ 
      success: false, 
      error: 'Session not found' 
    });
  }

  if (foundSession.status !== 'ready') {
    return res.status(400).json({ 
      success: false, 
      error: `Session not ready (status: ${foundSession.status})` 
    });
  }

  try {
    // Format phone number (add @c.us if not present)
    const formattedNumber = to.includes('@') ? to : `${to}@c.us`;

    // Send message
    const sentMessage = await foundSession.client.sendMessage(formattedNumber, message);

    res.json({
      success: true,
      messageId: sentMessage.id.id,
      timestamp: sentMessage.timestamp
    });

  } catch (error) {
    console.error(`Error sending message:`, error);
    res.status(500).json({ 
      success: false, 
      error: error.message 
    });
  }
});

// ====================================================================
// DISCONNECT SESSION
// ====================================================================
app.post('/disconnect/:sessionId', async (req, res) => {
  const { sessionId } = req.params;

  // Find and remove session
  let foundCaseId = null;
  for (const [caseId, session] of sessions.entries()) {
    if (session.sessionId === sessionId) {
      foundCaseId = caseId;
      break;
    }
  }

  if (!foundCaseId) {
    return res.status(404).json({ error: 'Session not found' });
  }

  const session = sessions.get(foundCaseId);
  
  try {
    if (session.client) {
      await session.client.destroy();
    }
    sessions.delete(foundCaseId);
    
    res.json({ success: true, message: 'Session disconnected' });
  } catch (error) {
    console.error('Error disconnecting:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

// ====================================================================
// START SERVER
// ====================================================================
app.listen(PORT, () => {
  console.log(`🚀 WhatsApp Service running on http://localhost:${PORT}`);
  console.log(`   Ready to serve QR codes and send messages!`);
});
