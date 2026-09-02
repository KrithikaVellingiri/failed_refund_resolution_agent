# Failed-Refund Resolution Agent

## Prerequisites
- Python 3.10+
- PostgreSQL

## Database Setup
Create a PostgreSQL database for the project:
```sql
CREATE DATABASE failed_refund_agent;
```

## Environment Setup
1. Copy the example env file:
```bash
cd backend
cp .env.example .env
```
2. Update the `.env` file with your actual `DATABASE_URL` if needed.

## Installing Dependencies
Create a virtual environment and install dependencies:
```bash
cd backend
python -m venv venv
# Windows: venv\Scripts\activate
# Linux/Mac: source venv/bin/activate
pip install -r requirements.txt
```

## Running the Application
Start the FastAPI server:
```bash
cd backend
uvicorn app.main:app --reload
```

## Testing
Verify the health endpoint and database connectivity:
```bash
curl http://localhost:8000/health
```
Expected response:
```json
{"status": "ok"}
```
