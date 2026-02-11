# Frontend Routing Update

## Add Landing Page to Routes

Update `frontend/src/App.tsx` to show landing page before login:

```tsx
import LandingPage from './pages/LandingPage';

// In your routes:
<Routes>
  <Route path="/" element={<LandingPage />} />
  <Route path="/login" element={<LoginPage />} />
  <Route path="/register" element={<RegisterPage />} />

  {/* Protected routes */}
  <Route element={<ProtectedRoute />}>
    <Route path="/dashboard" element={<Dashboard />} />
    <Route path="/cases" element={<CasesList />} />
    {/* ... other routes */}
  </Route>
</Routes>
```

## Install Framer Motion

```bash
cd ~/Downloads/dsa-case-os/frontend
npm install framer-motion lucide-react
```

## Or Use Docker:

```bash
cd ~/Downloads/dsa-case-os
docker exec -it dsa_case_os_frontend npm install framer-motion lucide-react
```

Then restart frontend:
```bash
docker compose restart frontend
```
