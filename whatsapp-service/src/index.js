/**
 * WhatsApp Service for DSA Case OS
 *
 * Per-case WhatsApp integration with QR code linking
 * Each case gets its own WhatsApp session that can be linked via QR code
 */

const { Client, LocalAuth } = require('whatsapp-web.js');
const express = require('express');
const QRCode = require('qrcode');
const { v4: uuidv4 } = require('uuid');
const bodyParser = require('body-parser');
const cors = require('cors');

const app = express();
const PORT = process.env.WHATSAPP_SERVICE_PORT || 3001;

// Middleware
app.use(cors());
app.use(bodyParser.json());

// Store active WhatsApp clients by session_id
const clients = new Map(); // session_id -> { client, qrCode, status, caseId }

// Store message callbacks
const messageHandlers = [];

/**
 * Initialize a new WhatsApp client for a case
 */
async function initializeClient(sessionId, caseId) {
    try {
        console.log(`[WhatsApp] Initializing client for session: ${sessionId}, case: ${caseId}`);

        const client = new Client({
            authStrategy: new LocalAuth({
                clientId: sessionId,
                dataPath: './whatsapp-sessions'
            }),
            puppeteer: {
                headless: true,
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

        // Store client info
        const clientInfo = {
            client,
            status: 'initializing',
            caseId,
            qrCode: null,
            linkedNumber: null
        };

        clients.set(sessionId, clientInfo);

        // QR Code event
        client.on('qr', async (qr) => {
            console.log(`[WhatsApp] QR Code generated for session: ${sessionId}`);
            try {
                const qrCodeDataURL = await QRCode.toDataURL(qr);
                clientInfo.qrCode = qrCodeDataURL;
                clientInfo.status = 'qr_ready';
            } catch (err) {
                console.error(`[WhatsApp] Error generating QR code:`, err);
            }
        });

        // Ready event
        client.on('ready', () => {
            console.log(`[WhatsApp] Client ready for session: ${sessionId}`);
            clientInfo.status = 'ready';
            clientInfo.linkedNumber = client.info.wid.user;
        });

        // Authenticated event
        client.on('authenticated', () => {
            console.log(`[WhatsApp] Client authenticated for session: ${sessionId}`);
            clientInfo.status = 'authenticated';
        });

        // Message event
        client.on('message', async (message) => {
            console.log(`[WhatsApp] Received message on session ${sessionId}:`, message.body);

            // Notify all registered handlers
            const messageData = {
                sessionId,
                caseId,
                messageId: message.id.id,
                from: message.from,
                to: message.to,
                body: message.body,
                type: message.type,
                timestamp: message.timestamp,
                hasMedia: message.hasMedia
            };

            // Call backend webhook (if configured)
            notifyBackend('message', messageData);
        });

        // Disconnected event
        client.on('disconnected', (reason) => {
            console.log(`[WhatsApp] Client disconnected for session ${sessionId}:`, reason);
            clientInfo.status = 'disconnected';
        });

        // Initialize client
        await client.initialize();

        return { success: true, sessionId };

    } catch (error) {
        console.error(`[WhatsApp] Error initializing client:`, error);
        return { success: false, error: error.message };
    }
}

/**
 * Notify backend about events (webhook)
 */
async function notifyBackend(eventType, data) {
    const backendUrl = process.env.BACKEND_WEBHOOK_URL || 'http://localhost:8000/api/webhooks/whatsapp';

    try {
        const response = await fetch(backendUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                event: eventType,
                data
            })
        });

        if (!response.ok) {
            console.error(`[WhatsApp] Failed to notify backend: ${response.statusText}`);
        }
    } catch (error) {
        console.error(`[WhatsApp] Error notifying backend:`, error.message);
    }
}

// ============================================================
// API ENDPOINTS
// ============================================================

/**
 * Health check
 */
app.get('/health', (req, res) => {
    res.json({
        status: 'ok',
        activeSessions: clients.size,
        uptime: process.uptime()
    });
});

/**
 * Generate QR code for a case
 * POST /generate-qr
 * Body: { caseId: string }
 */
app.post('/generate-qr', async (req, res) => {
    try {
        const { caseId } = req.body;

        if (!caseId) {
            return res.status(400).json({ error: 'caseId is required' });
        }

        // Generate unique session ID
        const sessionId = `case_${caseId}_${uuidv4().split('-')[0]}`;

        // Initialize client
        const result = await initializeClient(sessionId, caseId);

        if (!result.success) {
            return res.status(500).json({ error: result.error });
        }

        // Wait for QR code (max 30 seconds)
        const startTime = Date.now();
        while (Date.now() - startTime < 30000) {
            const clientInfo = clients.get(sessionId);
            if (clientInfo && clientInfo.qrCode) {
                return res.json({
                    success: true,
                    sessionId,
                    qrCode: clientInfo.qrCode,
                    status: clientInfo.status
                });
            }
            await new Promise(resolve => setTimeout(resolve, 500));
        }

        return res.status(408).json({ error: 'QR code generation timeout' });

    } catch (error) {
        console.error('[WhatsApp] Error in generate-qr:', error);
        res.status(500).json({ error: error.message });
    }
});

/**
 * Get session status
 * GET /session/:sessionId
 */
app.get('/session/:sessionId', (req, res) => {
    const { sessionId } = req.params;
    const clientInfo = clients.get(sessionId);

    if (!clientInfo) {
        return res.status(404).json({ error: 'Session not found' });
    }

    res.json({
        sessionId,
        caseId: clientInfo.caseId,
        status: clientInfo.status,
        linkedNumber: clientInfo.linkedNumber,
        hasQrCode: !!clientInfo.qrCode
    });
});

/**
 * Send message
 * POST /send-message
 * Body: { sessionId, to, message }
 */
app.post('/send-message', async (req, res) => {
    try {
        const { sessionId, to, message } = req.body;

        if (!sessionId || !to || !message) {
            return res.status(400).json({ error: 'sessionId, to, and message are required' });
        }

        const clientInfo = clients.get(sessionId);

        if (!clientInfo) {
            return res.status(404).json({ error: 'Session not found' });
        }

        if (clientInfo.status !== 'ready') {
            return res.status(400).json({ error: `Session not ready. Status: ${clientInfo.status}` });
        }

        // Format number for WhatsApp (must include country code)
        const chatId = to.includes('@c.us') ? to : `${to}@c.us`;

        // Send message
        const sentMessage = await clientInfo.client.sendMessage(chatId, message);

        res.json({
            success: true,
            messageId: sentMessage.id.id,
            timestamp: sentMessage.timestamp
        });

    } catch (error) {
        console.error('[WhatsApp] Error sending message:', error);
        res.status(500).json({ error: error.message });
    }
});

/**
 * Disconnect session
 * POST /disconnect
 * Body: { sessionId }
 */
app.post('/disconnect', async (req, res) => {
    try {
        const { sessionId } = req.body;

        if (!sessionId) {
            return res.status(400).json({ error: 'sessionId is required' });
        }

        const clientInfo = clients.get(sessionId);

        if (!clientInfo) {
            return res.status(404).json({ error: 'Session not found' });
        }

        // Destroy client
        await clientInfo.client.destroy();
        clients.delete(sessionId);

        res.json({ success: true, message: 'Session disconnected' });

    } catch (error) {
        console.error('[WhatsApp] Error disconnecting session:', error);
        res.status(500).json({ error: error.message });
    }
});

/**
 * Get QR code
 * GET /qr-code/:sessionId
 */
app.get('/qr-code/:sessionId', (req, res) => {
    const { sessionId } = req.params;
    const clientInfo = clients.get(sessionId);

    if (!clientInfo) {
        return res.status(404).json({ error: 'Session not found' });
    }

    if (!clientInfo.qrCode) {
        return res.status(404).json({ error: 'QR code not yet generated' });
    }

    res.json({
        sessionId,
        qrCode: clientInfo.qrCode,
        status: clientInfo.status
    });
});

// Start server
app.listen(PORT, () => {
    console.log(`[WhatsApp Service] Running on port ${PORT}`);
    console.log(`[WhatsApp Service] Backend webhook: ${process.env.BACKEND_WEBHOOK_URL || 'http://localhost:8000/api/webhooks/whatsapp'}`);
});

// Graceful shutdown
process.on('SIGINT', async () => {
    console.log('[WhatsApp Service] Shutting down...');
    for (const [sessionId, clientInfo] of clients.entries()) {
        try {
            await clientInfo.client.destroy();
            console.log(`[WhatsApp Service] Destroyed session: ${sessionId}`);
        } catch (error) {
            console.error(`[WhatsApp Service] Error destroying session ${sessionId}:`, error);
        }
    }
    process.exit(0);
});
