# AoE2 Analytics Platform - Setup Guide

## Prerequisites

- Docker & Docker Compose (recommended for local dev)
- Or:
  - Python 3.11+
  - Node.js 18+
  - PostgreSQL 15+
  - Redis 7+

## Quick Start with Docker

```bash
git clone https://github.com/TheScienceCo/League.git
cd League
cp .env.example .env
docker compose up --build
```

Services will be available at:
- **Web UI**: http://localhost:3000
- **API Docs**: http://localhost:8000/docs
- **API Health**: http://localhost:8000/health

The database seeds itself on first startup with mock data and an example replay analysis.

## Manual Setup (Without Docker)

### 1. Backend Setup

#### Create Virtual Environment
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
cd backend
pip install -r requirements.txt
```

#### Database Setup
```bash
# Create database
createdb aoe2
createuser aoe2 -P  # Enter password when prompted

# Set DATABASE_URL in .env
export DATABASE_URL="postgresql://aoe2:password@localhost:5432/aoe2"

# Run migrations
alembic upgrade head
```

#### Start API
```bash
make api
# or
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 2. Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000 in your browser.

### 3. Redis Setup (Optional but Recommended)

```bash
# Start Redis
redis-server

# Or with Docker
docker run -d -p 6379:6379 redis:7
```

## Configuration

### Environment Variables

Copy `.env.example` to `.env` and customize:

```bash
# Application
ENVIRONMENT=local
DEBUG=true
LOG_LEVEL=INFO

# Database
DATABASE_URL=postgresql://aoe2:aoe2@localhost:5432/aoe2

# Redis (optional)
REDIS_URL=redis://localhost:6379/0

# Replay Processing
REPLAY_STORAGE_PATH=/tmp/aoe2_replays
REPLAY_PARSER_TYPE=mock  # Use 'mock' for testing
GAME_STATE_SNAPSHOT_INTERVAL_SECONDS=10

# Analytics
SKILL_GAP_MIN_SAMPLES=100
SKILL_GAP_ELO_BANDS=1000,1200,1400,1600,1800,2000,9999
```

## Running Tests

### Backend Tests
```bash
cd backend
pytest tests/ -v

# Specific test file
pytest tests/test_replay_pipeline.py -v

# With coverage
pytest --cov=app tests/
```

### Frontend Tests
```bash
cd frontend
npm run test
```

## Development Workflow

### Adding a New Feature

1. **Create database migration** (if needed)
   ```bash
   cd backend
   alembic revision --autogenerate -m "describe_change"
   ```

2. **Implement service logic** (backend)
   ```
   backend/app/services/...
   ```

3. **Add API endpoint** (backend)
   ```
   backend/app/api/v1/...
   ```

4. **Update schemas** for validation (backend)
   ```
   backend/app/schemas/aoe2.py
   ```

5. **Add tests** (backend)
   ```
   backend/tests/...
   ```

6. **Add page/component** (frontend)
   ```
   frontend/app/... or frontend/components/...
   ```

7. **Test in browser**
   ```bash
   cd frontend
   npm run dev
   ```

8. **Commit with clear message**
   ```bash
   git add -A
   git commit -m "Add feature description"
   ```

### Common Commands

#### Backend
```bash
make api              # Start API server
make worker           # Start background worker
make test             # Run tests
make migrate          # Run migrations
make demo             # Generate demo data
make lint             # Run linters
```

#### Frontend
```bash
npm run dev           # Start dev server
npm run build         # Build for production
npm run test          # Run tests
npm run lint          # Run linters
```

## Database Migrations

### Create Migration
```bash
cd backend
alembic revision --autogenerate -m "add_column_to_matches"
```

### Review Migration
```bash
# Edit backend/alembic/versions/XXXX_add_column_to_matches.py
# Check upgrade() and downgrade() functions
```

### Apply Migration
```bash
# Single database
alembic upgrade head

# Or through Docker
docker compose exec api alembic upgrade head
```

### Rollback Migration
```bash
alembic downgrade -1   # Rollback one migration
alembic downgrade XXXX # Rollback to specific version
```

## Replay Testing

### Using Mock Parser

The mock parser generates deterministic replay data for testing:

```bash
# API: POST /api/v1/aoe2/replays/upload
curl -X POST \
  -F "file=@test_replay.aoe2record" \
  http://localhost:8000/api/v1/aoe2/replays/upload
```

### Using Real Replays (Future)

When replay parser is integrated:

1. Place `.aoe2record` file in `data/samples/`
2. Upload through web UI or API
3. Check processing status at `/api/v1/aoe2/replays/{id}/status`
4. View results at `/matches/{id}`

## Troubleshooting

### Database Connection Issues
```bash
# Check PostgreSQL is running
psql -U aoe2 -d aoe2 -c "SELECT 1"

# If connection refused, verify DATABASE_URL in .env
# Format: postgresql://user:password@host:port/dbname
```

### Redis Connection Issues
```bash
# Check Redis is running
redis-cli ping
# Should return: PONG

# If not available, remove REDIS_URL from .env
# Application will work without it (no caching)
```

### Tests Failing
```bash
# Reinstall dependencies
cd backend
pip install -r requirements.txt --force-reinstall

# Run specific test with verbose output
pytest tests/test_replay_pipeline.py::TestReplayParser -vv

# Check test fixtures are available
pytest --fixtures tests/test_replay_pipeline.py
```

### API Not Starting
```bash
# Check for syntax errors
python -m py_compile backend/app/main.py

# Check imports
cd backend && python -c "from app.main import create_app; app = create_app()"

# Check logs
docker compose logs api  # If using Docker
```

### Frontend Build Issues
```bash
# Clear cache and rebuild
cd frontend
rm -rf .next node_modules
npm install
npm run build
```

## Monitoring & Debugging

### API Logs
```bash
# Docker Compose
docker compose logs -f api

# Or directly
uvicorn app.main:app --reload --log-level debug
```

### Database Queries
```bash
# Enable query logging in .env
DB_ECHO=true

# Or directly in PostgreSQL
psql aoe2
\set VERBOSITY verbose
SELECT * FROM players;
```

### Redis Cache
```bash
redis-cli
KEYS *              # List all keys
GET key_name        # Get value
DEL key_name        # Delete key
FLUSHALL           # Clear all cache
```

## Performance Tuning

### Database
```sql
-- Check indexes
\d matches
\d events

-- Add index if needed
CREATE INDEX idx_matches_created_at ON matches(created_at DESC);
```

### Connection Pool
```bash
# In .env
DB_POOL_SIZE=10        # Connections to maintain
DB_MAX_OVERFLOW=20     # Additional connections under load
```

## Production Deployment

### Build Docker Images
```bash
docker build -t aoe2-api:latest -f backend/Dockerfile .
docker build -t aoe2-web:latest -f frontend/Dockerfile .
```

### Deploy with Docker Compose
```bash
docker compose -f docker-compose.yml up -d

# Or with stack
docker stack deploy -c docker-compose.yml aoe2
```

### Verify Deployment
```bash
curl http://localhost:8000/health
curl http://localhost:3000
```

### Logs & Monitoring
```bash
docker compose logs -f api
docker compose ps
docker compose stats
```

## Backup & Restore

### Database Backup
```bash
pg_dump aoe2 > backup.sql

# Restore
psql aoe2 < backup.sql
```

### Docker Volume Backup
```bash
docker run --rm -v aoe2_postgres_data:/data \
  -v $(pwd):/backup \
  ubuntu tar czf /backup/postgres.tar.gz -C /data .
```

## Getting Help

- **API Documentation**: http://localhost:8000/docs
- **Architecture**: See `docs/ARCHITECTURE.md`
- **Schema**: See `docs/SCHEMA.md` (generated from models)
- **Issues**: GitHub Issues
- **Discussions**: GitHub Discussions

## Next Steps

1. ✅ Core architecture and services
2. → Frontend dashboard implementation
3. → Database seeding with sample data
4. → Peer comparison baseline calculation
5. → ML skill gap models
6. → Advanced visualizations
7. → Leaderboard integration

Happy analyzing! 🎮📊
