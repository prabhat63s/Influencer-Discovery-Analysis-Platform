# CreatosConnect Backend

The robust backend API for the CreatosConnect platform, built with FastAPI. It powers influencer discovery, analysis, and report generation using AI and data scrapping.

## 🚀 Features

*   **Dynamic Search**: Natural language search for influencers using AI and web scraping (Selenium, Google Search).
*   **Deep Analysis**: AI-driven insights and detailed metrics for influencer profiles.
*   **Report Generation**: Automated PDF reports for stakeholders (ReportLab, WeasyPrint).
*   **Authentication**: Secure user authentication and session management.
*   **Task Queue**: Asynchronous background processing with Celery and Redis.
*   **Agent Assist**: Monitoring and knowledge assistant integration.

## 🛠️ Tech Stack

*   **Framework**: [FastAPI](https://fastapi.tiangolo.com/) (Python 3.13+)
*   **Database**: SQLAlchemy (Async), Aiosqlite (Dev), PostgreSQL (Prod)
*   **Async Tasks**: Celery, Redis
*   **AI/LLM**: OpenAI, Google Gemini (GenerativeAI)
*   **Scraping**: Selenium, Google Search Results
*   **Testing**: Pytest

## 📋 Prerequisites

*   Python 3.13+
*   Redis (for Celery task queue)
*   Chrome/Chromium (for Selenium scraping)

## ⚙️ Setup & Installation

1.  **Clone the repository:**
    ```bash
    git clone <repository-url>
    cd backend
    ```

2.  **Create and activate a virtual environment:**
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # On Windows: .venv\Scripts\activate
    ```

3.  **Install dependencies:**
    ```bash
    # Install standard dependencies
    pip install -r requirements.txt
    
    # Install playwrigh/selenium drivers if needed
    # (Check specific driver requirements)
    ```

4.  **Environment Configuration:**
    Create a `.env` file in the root directory using the provided example:
    ```bash
    cp .env.example .env
    ```
    
    ### 🗄️ Database Configuration
    The backend supports both SQLite (default for dev) and PostgreSQL (production).
    
    *   **Development (SQLite)**: 
        Leave `DATABASE_URL` empty in `.env`. The app will automatically create `creatos_connect.db` in the root.
        ```ini
        DATABASE_URL=
        ```
        
    *   **Production (PostgreSQL)**:
        Set the `DATABASE_URL` with your async PostgreSQL connection string.
        ```ini
        DATABASE_URL=postgresql+asyncpg://user:password@host:port/dbname
        ```

    ### 🔑 other Secrets
    Fill in your API keys in `.env` (OpenAI, Gemini, SerAPI, BrightData, Redis).
    ```ini
    SECRET_KEY=your_secure_random_string
    OPENAI_API_KEY=sk-...
    ...
    ```

## 🏃‍♂️ Running the Application

### 1. Start the API Server
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
The API will be available at `http://localhost:8000`.
Interactive docs: `http://localhost:8000/docs`.

### 2. Start Celery Worker (for background tasks)
```bash
celery -A app.worker worker --loglevel=info
```

## 📂 Project Structure

```
backend/
├── app/
│   ├── config/         # Configuration settings
│   ├── controllers/    # Business logic & request handling
│   ├── endpoints/      # API Route definitions
│   ├── middleware/     # Custom middleware (auth, logging)
│   ├── models/         # Database models (Pydantic/SQLAlchemy)
│   ├── services/       # Core services (Scraping, AI, Reports)
│   └── utils/          # Helper utilities
├── storage/            # Local storage for uploads/reports
├── tests/              # Unit and integration tests
├── .env                # Environment variables
└── requirements.txt    # Python dependencies
```
