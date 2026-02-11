# DSA Case OS - Frontend

A React frontend application for the DSA Case OS credit intelligence platform for business loan DSAs in India.

## Tech Stack

- **React 18** with Vite
- **React Router v6** for routing
- **Tailwind CSS** for styling
- **Axios** + **React Query** (TanStack Query) for API calls
- **React Hook Form** for forms
- **Lucide React** for icons
- **React Dropzone** for file uploads
- **React Hot Toast** for notifications

## Getting Started

### Prerequisites

- Node.js 16+ and npm
- Backend API running at `http://localhost:8000`

### Installation

```bash
npm install
```

### Development

```bash
npm run dev
```

The app will be available at `http://localhost:5173`

### Production Build

```bash
npm run build
npm run preview
```

## Project Structure

```
src/
├── api/              # API client and services
├── components/       # Reusable components
│   ├── layout/       # Sidebar, Header, Layout
│   └── ui/           # Button, Card, Badge, Input, etc.
├── pages/            # Page components
├── utils/            # Utilities (auth, constants, formatting)
├── App.jsx           # Main app with routing
└── main.jsx          # Entry point
```

## Features

1. **Authentication**: Login/Register with JWT
2. **Dashboard**: Case cards, stats, search
3. **New Case Wizard**: 3-step case creation with document upload
4. **Case Detail**: 5 tabs (Documents, Checklist, Profile, Eligibility, Report)
5. **Copilot**: AI chat for lender queries
6. **Lender Directory**: Browse and filter lenders

## API Configuration

Update the API base URL in `src/api/client.js` if needed:

```javascript
const API_BASE_URL = 'http://localhost:8000/api/v1';
```

## Design System

- Primary: `#2563EB` (blue-600)
- Accent: `#10B981` (green-500)
- Fully responsive with Tailwind CSS

## License

Proprietary
