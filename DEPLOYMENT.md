# Deployment Guide

## Production Files

The following files are required for deployment:

### Core Application
- ✅ `app.py` - Main application (self-contained, no external dependencies)
- ✅ `centers.json` - Center data
- ✅ `requirements.txt` - Production dependencies

### Docker Deployment
- ✅ `Dockerfile` - Container configuration
- ✅ `docker-compose.yml` - Orchestration (optional)
- ✅ `.dockerignore` - Excludes unnecessary files from image

### Configuration
- ✅ `.gitignore` - Git exclusions

## Deployment Methods

### Method 1: Docker (Recommended)

```bash
# Build the image
docker build -t lawash-tool .

# Run the container
docker run -d -p 3000:3000 --name lawash-api lawash-tool

# Or use docker-compose
docker-compose up -d
```

### Method 2: Direct Python

```bash
# Install dependencies
pip install -r requirements.txt

# Run with Gunicorn (production)
gunicorn --bind 0.0.0.0:3000 --workers 4 --threads 2 --timeout 60 app:app

# Or run with Flask (development only)
python app.py
```

## Environment Variables

The application uses these environment variables (all optional):

- `FLASK_APP` - Application entry point (default: `app.py`)
- `PYTHONUNBUFFERED` - Disable Python output buffering (default: `1`)

## Health Check

```bash
curl http://localhost:3000/health
```

Expected response:
```json
{"status": "healthy", "service": "lawash-tool"}
```

## API Endpoints

### POST /api/chat
Search for centers

**Request:**
```json
{
  "message": "Peru 38 Barcelona"
}
```

**Response:**
```json
{
  "response": "I believe you're referring to **Peru 38** in Barcelona.<br>Center ID: 406<br>Code: ES0295<br>Location: Peru 38"
}
```

### GET /health
Health check endpoint

## Production Checklist

- [x] All test files removed
- [x] Only production dependencies in `requirements.txt`
- [x] Gunicorn configured for production
- [x] Non-root user in Docker
- [x] CORS enabled
- [x] Logging configured
- [x] Health check endpoint
- [x] `.dockerignore` configured
- [x] `.gitignore` configured

## File Structure

```
lawash-tool/
├── app.py                    # Main application (PRODUCTION)
├── centers.json              # Center data (PRODUCTION)
├── requirements.txt          # Production dependencies (PRODUCTION)
├── Dockerfile                # Docker config (PRODUCTION)
├── docker-compose.yml        # Docker orchestration (PRODUCTION)
├── .dockerignore             # Docker exclusions (PRODUCTION)
├── .gitignore                # Git exclusions
├── requirements-dev.txt      # Development dependencies (DEV ONLY)
├── README.md                 # Documentation
└── SEARCH_IMPROVEMENTS.md    # Technical notes
```

## Notes

- `app.py` is completely self-contained with no external Python file dependencies
- All search logic, normalization, and scoring is in `app.py`
- The application loads `centers.json` at startup
- No database required - all data is in-memory
- Stateless design - can scale horizontally

## Troubleshooting

### Port already in use
```bash
# Find process using port 3000
lsof -i :3000

# Kill the process
kill -9 <PID>
```

### Dependencies not found
```bash
# Reinstall dependencies
pip install --no-cache-dir -r requirements.txt
```

### Docker build fails
```bash
# Clean build
docker build --no-cache -t lawash-tool .
```
