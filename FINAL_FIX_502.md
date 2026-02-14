# Final Fix for 502 Errors

## The Problem
Railway assigns a dynamic PORT environment variable, but we were hardcoding port 5173.

## The Solution
Updated `vite.config.js` to use `process.env.PORT` or default to 5173:

```javascript
export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: parseInt(process.env.PORT) || 5173,
  },
  preview: {
    host: '0.0.0.0',
    port: parseInt(process.env.PORT) || 5173,
  },
})
```

## Files Changed
- ✅ `frontend/vite.config.js` - Now reads PORT from environment
- ✅ `frontend/package.json` - Simplified start script

## What This Fixes
- ✅ Railway can now connect to the correct dynamic port
- ✅ 502 errors will be gone
- ✅ www.credilo.in will start working after DNS propagates

## Push This Fix Now!
