# DSA Case OS Frontend - Setup Guide

## Quick Start

### 1. Install Dependencies

```bash
cd frontend
npm install
```

This will install all required packages including:
- React 18 with Vite
- React Router v6
- Tailwind CSS
- Axios & React Query
- React Hook Form
- Lucide React icons
- React Dropzone
- React Hot Toast

### 2. Start Development Server

```bash
npm run dev
```

The app will run at: **http://localhost:5173**

### 3. Backend Setup

Make sure the backend API is running at: **http://localhost:8000**

If your backend runs on a different port, update `src/api/client.js`:

```javascript
const API_BASE_URL = 'http://localhost:YOUR_PORT/api/v1';
```

## Available Scripts

- `npm run dev` - Start development server
- `npm run build` - Build for production
- `npm run preview` - Preview production build
- `npm run lint` - Run ESLint

## Features Checklist

✅ **Authentication**
- Login/Register pages
- JWT token management
- Protected routes

✅ **Dashboard**
- Case overview cards with status badges
- Quick stats (total cases, completeness, etc.)
- Search by borrower name
- Click cards to view details

✅ **New Case Wizard**
- Step 1: Basic info (borrower, entity type, program)
- Step 2: Document upload (drag-drop, multi-file)
- Step 3: Confirmation

✅ **Case Detail (5 Tabs)**
- **Documents**: View uploads, types, confidence
- **Checklist**: Program-specific requirements
- **Profile**: Borrower feature vector
- **Eligibility**: Run scoring, view lender matches
- **Report**: Generate & download PDF

✅ **Copilot**
- AI chat interface
- Suggestion chips
- Real-time responses

✅ **Lender Directory**
- Browse all lenders
- Search by name
- Filter by pincode

## Project Structure

```
src/
├── api/
│   ├── client.js       # Axios instance with auth
│   └── services.js     # All API calls
├── components/
│   ├── layout/
│   │   ├── Header.jsx
│   │   ├── Layout.jsx
│   │   └── Sidebar.jsx
│   └── ui/
│       ├── Badge.jsx
│       ├── Button.jsx
│       ├── Card.jsx
│       ├── Input.jsx
│       ├── Loading.jsx
│       ├── Modal.jsx
│       ├── ProgressBar.jsx
│       ├── Select.jsx
│       └── index.js
├── pages/
│   ├── auth/
│   │   ├── Login.jsx
│   │   └── Register.jsx
│   ├── CaseDetail.jsx
│   ├── Copilot.jsx
│   ├── Dashboard.jsx
│   ├── Lenders.jsx
│   ├── NewCase.jsx
│   └── Settings.jsx
├── utils/
│   ├── auth.js         # Auth helpers
│   ├── constants.js    # App constants
│   └── format.js       # Formatters
├── App.jsx             # Routes & providers
└── main.jsx            # Entry point
```

## API Integration

All backend endpoints are integrated in `src/api/services.js`:

### Cases
- `POST /api/v1/cases/` - Create case
- `GET /api/v1/cases/` - List cases
- `GET /api/v1/cases/{id}` - Get case
- `PATCH /api/v1/cases/{id}` - Update case
- `POST /api/v1/cases/{id}/upload` - Upload documents
- `GET /api/v1/cases/{id}/checklist` - Get checklist
- `GET /api/v1/cases/{id}/manual-prompts` - Manual prompts

### Documents
- `GET /api/v1/documents/{id}/ocr-text` - OCR text
- `POST /api/v1/documents/{id}/reclassify` - Reclassify

### Extraction
- `POST /api/v1/extraction/case/{id}/extract` - Run extraction
- `GET /api/v1/extraction/case/{id}/fields` - Extracted fields
- `GET /api/v1/extraction/case/{id}/features` - Feature vector

### Eligibility
- `POST /api/v1/eligibility/case/{id}/score` - Run scoring
- `GET /api/v1/eligibility/case/{id}/results` - Get results

### Reports
- `POST /api/v1/reports/case/{id}/generate` - Generate report
- `GET /api/v1/reports/case/{id}/report/pdf` - Download PDF

### Lenders
- `GET /api/v1/lenders/` - List all lenders
- `GET /api/v1/lenders/by-pincode/{pincode}` - Filter by pincode

### Copilot
- `POST /api/v1/copilot/query` - Chat query

## Design System

### Colors
- **Primary**: `#2563EB` (blue-600)
- **Accent**: `#10B981` (green-500)

### Components
All reusable UI components are in `src/components/ui/`:
- Button (variants: primary, secondary, success, danger, outline)
- Card (with hover effect)
- Badge (variants: default, primary, success, warning, danger, info)
- Input (with label and error)
- Select (with options)
- Loading (with spinner)
- ProgressBar
- Modal

### Layout
- Sidebar navigation (fixed left)
- Header with user info (fixed top)
- Responsive design for all screen sizes

## Authentication Flow

1. User visits `/login` or `/register`
2. Submit credentials
3. Receive JWT token from backend
4. Store token in `localStorage`
5. Axios interceptor adds token to all requests
6. On 401 error, redirect to login

## State Management

- **React Query** for server state (API data)
- **React Hook Form** for form state
- **localStorage** for auth tokens
- **React Hot Toast** for notifications

## Troubleshooting

### Port already in use
If port 5173 is busy, Vite will use the next available port (5174, 5175, etc.)

### API connection errors
- Ensure backend is running at `http://localhost:8000`
- Check browser console for CORS issues
- Verify API base URL in `src/api/client.js`

### Build errors
```bash
rm -rf node_modules package-lock.json
npm install
```

### Styling not working
```bash
npm run build
# Then check if Tailwind is properly configured
```

## Production Build

```bash
npm run build
```

Output will be in `dist/` folder. Serve with:

```bash
npm run preview
```

Or deploy to any static hosting (Vercel, Netlify, etc.)

## Next Steps

1. Install dependencies: `npm install`
2. Start dev server: `npm run dev`
3. Open browser: http://localhost:5173
4. Create account or login
5. Start creating cases!

## Support

For issues or questions, refer to the main README.md or check the API documentation.
