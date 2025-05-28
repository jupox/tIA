# AI Decision Support Tool

## Description

The AI Decision Support Tool is a web application built with Reflex.dev that helps users make informed decisions. Users can input a prompt or question, and the tool leverages AI (simulated via OpenAI's GPT models) and asynchronous task processing with Celery and Redis to:
1.  Retrieve relevant information (simulated).
2.  Process this information to generate potential options and a concise summary.
3.  Display these results to the user.

The application uses Supabase as a PostgreSQL database for storing prompts and their associated results.

## Prerequisites

*   Python 3.10+
*   Poetry (for dependency management, optional but recommended)
*   Access to a Supabase project (for PostgreSQL database)
*   Access to an OpenAI API key (for AI functionalities)
*   Redis server (for Celery message broker and backend)

## Setup Instructions

### 1. Clone the Repository

```bash
git clone <your-repository-url>
cd <repository-name>
```

### 2. Install Dependencies

If you have Poetry:
```bash
poetry install
```
Otherwise, using pip with the `requirements.txt` (ensure it's up to date):
```bash
pip install -r requirements.txt
```
You might need to add `/home/swebot/.local/bin` (or similar, depending on your pip user install location) to your `PATH` if commands like `reflex` or `celery` are not found after installation.
```bash
export PATH="$PATH:/home/swebot/.local/bin" 
```
(Replace `/home/swebot/.local/bin` with your actual local bin directory if different.)

### 3. Environment Variables

Create a `.env` file in the root directory of the project or set the following environment variables in your shell:

```env
# Supabase Configuration
SUPABASE_URL="YOUR_SUPABASE_PROJECT_URL"
SUPABASE_KEY="YOUR_SUPABASE_ANON_OR_SERVICE_ROLE_KEY"

# OpenAI API Configuration
OPENAI_API_KEY="YOUR_OPENAI_API_KEY"

# Redis Configuration (for Celery)
# Default is redis://localhost:6379/0 if not set
REDIS_URL="redis://your-redis-host:your-redis-port/0" 
```
*   Replace placeholder values with your actual credentials.
*   The `SUPABASE_KEY` can be the `anon` key if you have appropriate Row Level Security (RLS) policies, or the `service_role` key for backend operations (be cautious with the service role key, especially in client-facing code, though here it's used server-side and by Celery workers).

### 4. Supabase Database Schema

You need to create two tables in your Supabase project: `prompts` and `results`.

**Table: `prompts`**

| Column        | Type                        | Constraints                               | Description                                     |
| :------------ | :-------------------------- | :---------------------------------------- | :---------------------------------------------- |
| `id`          | `integer`                   | Primary Key, Auto-incrementing (Identity) | Unique identifier for the prompt                |
| `user_prompt` | `text`                      | Not Null                                  | The prompt text submitted by the user           |
| `status`      | `text`                      | Not Null, Default: 'pending'              | Current processing status of the prompt         |
| `created_at`  | `timestamp with time zone`  | Not Null, Default: `now()`                | Timestamp when the prompt was created           |
| `updated_at`  | `timestamp with time zone`  | Not Null, Default: `now()`                | Timestamp when the prompt was last updated      |

**SQL for `prompts` table:**
```sql
CREATE TABLE prompts (
    id SERIAL PRIMARY KEY,
    user_prompt TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Optional: Trigger to automatically update updated_at timestamp
CREATE OR REPLACE FUNCTION trigger_set_timestamp()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER set_prompts_updated_at
BEFORE UPDATE ON prompts
FOR EACH ROW
EXECUTE FUNCTION trigger_set_timestamp();
```

**Table: `results`**

| Column              | Type                        | Constraints                               | Description                                        |
| :------------------ | :-------------------------- | :---------------------------------------- | :------------------------------------------------- |
| `id`                | `integer`                   | Primary Key, Auto-incrementing (Identity) | Unique identifier for the result                   |
| `prompt_id`         | `integer`                   | Foreign Key (references `prompts.id`)     | Links to the corresponding prompt                  |
| `raw_data`          | `jsonb`                     | Nullable                                  | Raw data retrieved (e.g., from web search, AI)     |
| `processed_options` | `jsonb`                     | Nullable                                  | Structured options extracted from raw data         |
| `summary`           | `text`                      | Nullable                                  | AI-generated summary of the information            |
| `created_at`        | `timestamp with time zone`  | Not Null, Default: `now()`                | Timestamp when the result entry was created        |
| `updated_at`        | `timestamp with time zone`  | Not Null, Default: `now()`                | Timestamp when the result entry was last updated   |

**SQL for `results` table:**
```sql
CREATE TABLE results (
    id SERIAL PRIMARY KEY,
    prompt_id INTEGER NOT NULL REFERENCES prompts(id) ON DELETE CASCADE,
    raw_data JSONB,
    processed_options JSONB,
    summary TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER set_results_updated_at
BEFORE UPDATE ON results
FOR EACH ROW
EXECUTE FUNCTION trigger_set_timestamp();
```

**Note on RLS (Row Level Security):** If you are using the `anon` key for Supabase, ensure you have appropriate RLS policies set up on the `prompts` and `results` tables to allow read/write access as needed by your application logic. For backend services like Celery workers, using the `service_role` key bypasses RLS.

## Running the Application

### 1. Start Redis Server

Ensure your Redis server is running. If you installed it locally, it might already be running. Otherwise, start it:
```bash
redis-server
```
(This command might vary based on your Redis installation.)

### 2. Start the Reflex Development Server

This server handles the frontend and the API endpoints for the Reflex application.
```bash
reflex init # If you haven't already initialized the project structure
reflex run
```
The application should be accessible at `http://localhost:3000`.

### 3. Start the Celery Worker

Open a new terminal window/tab in the project directory.
Make sure your environment variables (especially `REDIS_URL`, `SUPABASE_URL`, `SUPABASE_KEY`, `OPENAI_API_KEY`) are available in this terminal session.
If using Poetry, you can run `poetry shell` first.

To start the Celery worker:
```bash
celery -A app.celery_app worker -l info 
```
*   `app.celery_app` points to the Celery application instance defined in `app/celery_app.py`.
*   `-l info` sets the logging level to info.

You should see the worker connect to Redis and discover the tasks defined in `app/tasks.py`.

## How to Use

1.  Open your web browser and navigate to `http://localhost:3000`.
2.  Enter your decision prompt or question into the input field (e.g., "What are the pros and cons of learning Python vs. JavaScript for web development?").
3.  Click the "Submit Prompt" button.
4.  The application will indicate that the prompt is being processed. You'll see a prompt ID.
5.  Click the "Refresh Results" button periodically.
    *   The status message will update as the background tasks (information retrieval, summarization) complete.
    *   If there are errors during processing, an error message will be displayed.
6.  Once processing is complete, the "Summary" and "Processed Options" sections will be populated with the AI-generated content.

## Conceptual Deployment Notes

Deploying this application involves several components:

1.  **Reflex Application (Frontend & Backend API):**
    *   Can be deployed using services like Vercel, Netlify (for static export if applicable, though Reflex usually runs a server), or on a VPS/PaaS that supports Python web applications (e.g., Heroku, AWS Elastic Beanstalk, Google App Engine).
    *   The Reflex server needs to be running.
    *   Environment variables must be configured in the deployment environment.

2.  **Celery Workers:**
    *   Need to be run as separate processes on a server or a worker service (e.g., Heroku workers, AWS ECS tasks).
    *   They require access to the same environment variables as the Reflex app (especially for Redis, Supabase, and OpenAI).
    *   Multiple workers can be run for scalability.
    *   A process manager like `supervisor` is recommended to keep Celery workers running in production.

3.  **Redis:**
    *   Use a managed Redis service (e.g., Redis Labs, AWS ElastiCache, Google Memorystore) or self-host a Redis instance.
    *   Ensure Celery workers and the Reflex app (if it needs to directly interact with Celery results, though not typical in this setup) can connect to Redis.

4.  **Supabase:**
    *   Supabase is already a hosted service, so no separate deployment is needed for the database itself.
    *   Ensure network rules (if any) allow connections from your deployed Reflex app and Celery workers.

5.  **Environment Variables:**
    *   Securely manage all environment variables (Supabase URL/keys, OpenAI API key, Redis URL) in your deployment environment. Do not hardcode them.

**General Workflow for Deployment:**
*   Containerize the Reflex app and Celery workers using Docker for easier deployment and management.
*   Set up a CI/CD pipeline to automate testing and deployment.
*   Configure logging and monitoring for all components.

This README provides a comprehensive guide to understanding, setting up, and running the AI Decision Support Tool.

## Running with Docker

This application can be run using Docker and Docker Compose, which simplifies dependency management and deployment.

**Prerequisites:**
*   Docker installed (https://docs.docker.com/get-docker/)
*   Docker Compose installed (https://docs.docker.com/compose/install/)

**Configuration:**

1.  **Ensure you have a `.env` file** in the project root directory. This file should contain your environment variables. For Docker Compose to work correctly with the provided configuration, ensure the following are set:
    ```env
    SUPABASE_URL="YOUR_SUPABASE_PROJECT_URL"
    SUPABASE_KEY="YOUR_SUPABASE_ANON_OR_SERVICE_ROLE_KEY"
    OPENAI_API_KEY="YOUR_OPENAI_API_KEY"
    REDIS_URL="redis://redis:6379/0" 
    ```
    *   **Important:** `REDIS_URL` must be set to `redis://redis:6379/0` for the `web` and `worker` services to connect to the `redis` service defined in `docker-compose.yml`.
    *   The Supabase instance is expected to be externally accessible; this Docker setup does not containerize Supabase.

**Running the Application:**

1.  **Build and Start Services:**
    Open your terminal in the project root directory and run:
    ```bash
    docker-compose up --build -d
    ```
    *   `--build`: Forces Docker Compose to build the images from your Dockerfile before starting the services.
    *   `-d`: Runs the services in detached mode (in the background).

    This command will:
    *   Pull the Redis image if you don't have it.
    *   Build the Docker image for your application (for both `web` and `worker` services using the same Dockerfile).
    *   Start the Redis, web (Reflex app), and Celery worker services.

2.  **Accessing the Application:**
    Once the services are up, the web application should be accessible at `http://localhost:3000`.

3.  **Viewing Logs:**
    To view the logs from the web server or the Celery worker:
    ```bash
    docker-compose logs web
    docker-compose logs worker
    ```
    You can also follow logs in real-time:
    ```bash
    docker-compose logs -f web
    docker-compose logs -f worker
    ```

4.  **Stopping the Application:**
    To stop all running services:
    ```bash
    docker-compose down
    ```
    This will stop and remove the containers. If you want to remove the volumes as well (like the `redis_data` volume), you can use `docker-compose down -v`.
