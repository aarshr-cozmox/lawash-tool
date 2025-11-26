# LaWash Center Finder API

Backend API for querying laundry center information using natural language.

## Quick Start with Docker

### Build and Run
```bash
# Build the image
docker build -t lawash-api .

# Run the container
docker run -p 3000:3000 lawash-api
```

### Using Docker Compose
```bash
# Start the service
docker-compose up -d

# View logs
docker-compose logs -f

# Stop the service
docker-compose down
```

## API Usage

**Endpoint:** `POST http://localhost:3000/api/chat`

**Request:**
```json
{
  "message": "center code for SAN SEBASTIAN at GUIPUZCOA"
}
```

**Response:**
```json
{
  "response": "I believe you're referring to **Antzieta Pasealekua 31** in DONOSTIA/SAN SEBASTIAN.<br>Center ID: 322<br>Code: ES0252<br>Location: ANTZIETA PASEALEKUA 31"
}
```

## Example Queries

```bash
# Query by city and province
curl -X POST http://localhost:3000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "center in Barcelona"}'

# Query with typos (fuzzy matching)
curl -X POST http://localhost:3000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Angara do Hero simo"}'

# Query by location
curl -X POST http://localhost:3000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Puerto Santa at Cadiz"}'
```

## Features

- ✅ 324 centers across Spain and Portugal
- ✅ Fuzzy matching for typos and misspellings
- ✅ Accent-insensitive search
- ✅ Smart dual-location matching (city + province)
- ✅ Voice AI ready

## Deployment

### Production Deployment

1. **Build the image:**
   ```bash
   docker build -t lawash-api:latest .
   ```

2. **Push to registry (optional):**
   ```bash
   docker tag lawash-api:latest your-registry/lawash-api:latest
   docker push your-registry/lawash-api:latest
   ```

3. **Deploy:**
   ```bash
   docker run -d -p 3000:3000 --name lawash-api lawash-api:latest
   ```

### Environment Variables

- `FLASK_APP`: Application entry point (default: `app.py`)
- `PYTHONUNBUFFERED`: Enable unbuffered output for logs (default: `1`)

## Health Check

The API includes a health check endpoint that can be used for monitoring:

```bash
curl -X POST http://localhost:3000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "test"}'
```

## Technical Details

- **Framework:** Flask
- **Python Version:** 3.11
- **Dependencies:** Flask, Pandas
- **Port:** 3000
- **Search Algorithm:** Hybrid fuzzy + token matching with weighted scoring
