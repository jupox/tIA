# AI Decision Support Tool

## Description

The AI Decision Support Tool is a web application built with Reflex.dev that helps users make informed decisions. Users can input a prompt or question, and the tool leverages AI (simulated via OpenAI's GPT models) and asynchronous task processing with Celery and Redis to:
1.  Retrieve relevant information (simulated).
2.  Process this information to generate potential options and a concise summary.
3.  Display these results to the user.

The application uses Supabase as a PostgreSQL database for storing prompts and their associated results. This README provides instructions for two main setup methods: running the entire stack (including Supabase) with Docker, or running the application natively with Python and connecting to an external Supabase instance.

## Core Technologies

*   **Frontend & Backend API:** [Reflex.dev](https://reflex.dev/)
*   **Database:** [Supabase](https://supabase.com/) (PostgreSQL)
*   **AI Integration:** [OpenAI Python Library](https://github.com/openai/openai-python)
*   **Task Queue:** [Celery](https://docs.celeryq.dev/)
*   **Message Broker/Celery Backend:** [Redis](https://redis.io/)
*   **Containerization:** [Docker](https://www.docker.com/) & [Docker Compose](https://docs.docker.com/compose/)

## Running with Docker (Recommended for Local Development)

This is the recommended method for local development as it sets up the application and a full local Supabase stack (including database, auth, storage, etc.) in a containerized environment.

**Prerequisites:**
*   Docker installed (https://docs.docker.com/get-docker/)
*   Docker Compose installed (https://docs.docker.com/compose/install/)

**Configuration (`.env` file):**

Before running the application with Docker Compose, you need to set up your environment variables.

1.  **Create `.env` from Example**:
    Copy the example environment file `.env.example` to a new file named `.env` in the project root directory:
    ```bash
    cp .env.example .env
    ```

2.  **Edit `.env` with Your Values**:
    Open the `.env` file and modify the placeholder values. Pay close attention to the following:

    *   **Project Specific Configuration**:
        *   `OPENAI_API_KEY`: **MUST CHANGE**. Your actual OpenAI API key.

    *   **Service Connection URLs (for project services `web` and `worker` within Docker):**
        *   `REDIS_URL=redis://redis:6379/0`: This tells your `web` and `worker` services to connect to the `redis` service (defined in `docker-compose.yml`) on its default port within the Docker network. **Generally, do not change this when running with Docker Compose.**
        *   `SUPABASE_URL=http://kong:8000`: This tells your `web` and `worker` services (server-side, e.g., for `get_supabase_client()`) to connect to the local Supabase stack via the `kong` API gateway service within the Docker network. **Generally, do not change this when running with Docker Compose.**

    *   **Supabase Keys for Project Services**:
        *   `SUPABASE_ANON_KEY`: Your Supabase anonymous key. The default in `.env.example` is a common one for local Supabase development.
        *   `SUPABASE_SERVICE_ROLE_KEY`: Your Supabase service role key. The default in `.env.example` is a common one for local Supabase development.
        *   *Note*: These keys are also used by the internal Supabase services (like Kong) via `ANON_KEY` and `SERVICE_ROLE_KEY` variables. Ensure consistency if you change them from the defaults.

    *   **Critical Supabase Variables (MUST CHANGE in `.env` for security and proper functioning of the local Supabase stack):**
        *   `POSTGRES_PASSWORD`: Choose a strong password for the local PostgreSQL database.
        *   `JWT_SECRET`: A strong, random secret for JWT signing (at least 32 characters).
        *   `SECRET_KEY_BASE`: A strong, random secret for Realtime functionality.
        *   `VAULT_ENC_KEY`: A strong, random secret for Supabase Vault (encryption at rest for secrets).

    *   **Supabase Public URL and Ports (for host access and external references):**
        *   `SUPABASE_PUBLIC_URL=http://localhost:8000`: This is how services like Supabase Studio and your frontend (client-side) will refer to the Supabase API from your host machine. `8000` should match the host port mapped to `kong` service's internal port `8000` (defined by `KONG_HTTP_PORT` in `.env`).
        *   `KONG_HTTP_PORT=8000`: Host port for Kong's HTTP listener.
        *   `SITE_URL=http://localhost:3000`: URL of your Reflex frontend, used for email redirects from Supabase Auth. `3000` should match the host port mapped to your `web` service.
        *   `POSTGRES_PORT_SUPAVISOR=54322`: Example host port for accessing the Supabase database directly via the Supavisor connection pooler. The internal port for Supavisor is usually `5432`.

    *   **Other Supabase Variables**:
        *   The `.env.example` file lists many other variables used by the Supabase stack (e.g., for Auth, Storage, SMTP). The defaults provided are generally suitable for local development. For example, SMTP is configured to point to a non-existent `mailhog` service; if you need local email testing, you would add a MailHog service to your `docker-compose.yml` or use an external SMTP service.

**Running the Application with Docker Compose:**

1.  **Ensure No Port Conflicts**:
    The `docker-compose.yml` file maps several ports to your host machine (e.g., 8000 for Kong, 3000 for the web app, 6379 for Redis, 54322 for Supavisor/Postgres). Ensure these ports are free on your machine or adjust them in the `.env` file (for Supabase ports) or `docker-compose.yml` (for project service ports).

2.  **Build and Start Services**:
    Open your terminal in the project root directory (where `docker-compose.yml` and `.env` are located) and run:
    ```bash
    docker-compose up --build -d
    ```
    *   `--build`: Forces Docker Compose to build the images from your Dockerfile (for `web` and `worker` services) before starting the services.
    *   `-d`: Runs the services in detached mode (in the background).

    This command will:
    *   Pull official images for Supabase services and Redis if you don't have them locally.
    *   Build the Docker image for your application.
    *   Start all defined services, including the full Supabase stack and your application's `web`, `worker`, and `redis` services.

3.  **Initializing Local Supabase Database Schema**:
    After starting the Docker services, the local Supabase database (`supabase-db` service) will be running but will not yet contain the project-specific `prompts` and `results` tables. You need to apply the schema manually:

    *   **Option A (Recommended: Using a DB Tool)**:
        1.  Connect to the local PostgreSQL instance using a database tool (e.g., DBeaver, pgAdmin, or `psql` CLI).
        2.  Connection details:
            *   Host: `localhost`
            *   Port: The value of `POSTGRES_PORT_SUPAVISOR` in your `.env` file (e.g., `54322`).
            *   User: `postgres`
            *   Password: The value of `POSTGRES_PASSWORD` in your `.env` file.
            *   Database: `postgres` (or the value of `POSTGRES_DB` if changed).
        3.  Once connected, execute the SQL `CREATE TABLE` statements for the `prompts` and `results` tables. These SQL statements are provided in the "Supabase Database Schema" section further down in this README.

    *   **Option B (Alternative: Using `docker exec`)**:
        1.  Ensure the `supabase-db` container is running: `docker ps` should list `supabase-db`.
        2.  Copy the SQL statements for `prompts` and `results` tables from the "Supabase Database Schema" section into a temporary file on your host machine (e.g., `schema.sql`).
        3.  Copy this SQL file into the `supabase-db` container:
            ```bash
            docker cp schema.sql supabase-db:/tmp/schema.sql
            ```
        4.  Execute the SQL file using `psql` inside the container:
            ```bash
            docker exec -i supabase-db psql -U postgres -d postgres -f /tmp/schema.sql
            ```
        This method is more complex and is generally less convenient than using a standard database tool.

4.  **Accessing the Application**:
    *   **Web Application**: Once the services are up and the schema is initialized, the Reflex web application should be accessible at `http://localhost:3000`.
    *   **Supabase Studio**: The local Supabase Studio dashboard should be accessible at `http://localhost:${KONG_HTTP_PORT}` (e.g., `http://localhost:8000`). Log in with the default credentials or as configured in your `.env` file.

5.  **Viewing Logs**:
    To view the logs from any service:
    ```bash
    docker-compose logs <service_name>
    # Example:
    docker-compose logs web
    docker-compose logs worker
    docker-compose logs supabase-db 
    ```
    To follow logs in real-time:
    ```bash
    docker-compose logs -f <service_name>
    ```

6.  **Stopping the Application**:
    To stop all running services:
    ```bash
    docker-compose down
    ```

7.  **Data Persistence (Local Supabase)**:
    *   The Supabase database data is persisted in the `./volumes/db/data` directory on your host machine (this path is mapped to the `db` service's data directory in `docker-compose.yml`).
    *   Supabase storage files (if used) are persisted in `./volumes/storage`.
    *   This data will survive `docker-compose stop` and `docker-compose down`.
    *   **To remove all persisted data (including the database and storage), run:**
        ```bash
        docker-compose down -v
        ```
        **Caution**: This command deletes the data in the named volumes and any other volumes associated with the services if they are not configured to persist beyond the container's lifecycle. For the local Supabase setup, this effectively resets your local database.

---

## Native Python Setup (Without Docker)

This section describes how to run the application natively using Python. This method requires you to manage Python, Redis, and Supabase (typically a cloud-hosted instance) separately.

**Prerequisites (Native Setup):**
*   Python 3.10+
*   Poetry (for dependency management, optional but recommended) or `pip`.
*   An accessible Redis server.
*   An accessible Supabase project (e.g., a free tier project on [Supabase Cloud](https://supabase.com/)).
*   An OpenAI API key.

**1. Clone the Repository:**
```bash
git clone <your-repository-url>
cd <repository-name>
```

**2. Install Dependencies:**
If you have Poetry:
```bash
poetry install
```
Otherwise, using pip with `requirements.txt`:
```bash
pip install -r requirements.txt
```
You might need to add your local Python bin directory (e.g., `/home/swebot/.local/bin`) to your `PATH` if commands like `reflex` or `celery` are not found after installation.

**3. Environment Variables (Native Setup):**
Create a `.env` file in the root directory or set environment variables in your shell.
```env
# --- Project Specific Config ---
OPENAI_API_KEY=your_openai_api_key_here

# --- Service Connection URLs ---
# For connecting to your self-managed Redis and Supabase instances.
REDIS_URL=redis://your_redis_host:your_redis_port/0 # e.g., redis://localhost:6379/0 if Redis is local

# For a cloud Supabase instance, get these from your Supabase project dashboard:
SUPABASE_URL=YOUR_SUPABASE_PROJECT_URL # e.g., https://xyz.supabase.co
SUPABASE_ANON_KEY=YOUR_SUPABASE_ANON_KEY
SUPABASE_SERVICE_ROLE_KEY=YOUR_SUPABASE_SERVICE_KEY # Use with caution, for backend only
```
*   **Important:** For `SUPABASE_URL`, `SUPABASE_ANON_KEY`, and `SUPABASE_SERVICE_ROLE_KEY`, use the actual credentials from your cloud-hosted Supabase project (or a self-hosted Supabase instance if you are managing one outside of the Docker setup provided here).

**4. Supabase Database Schema (Native Setup):**
Ensure the `prompts` and `results` tables are created in your Supabase database. Use the SQL statements provided in the "Supabase Database Schema" section below. You can execute these via the SQL Editor in your Supabase project dashboard.

**5. Running the Application (Native Setup):**

*   **Start Redis Server:**
    Ensure your Redis server is running and accessible via the `REDIS_URL` configured in your `.env` file.
    ```bash
    # Example if Redis is local:
    redis-server 
    ```

*   **Start the Reflex Development Server:**
    This server handles the frontend and the API endpoints.
    ```bash
    reflex init # If you haven't already initialized the project structure
    reflex run
    ```
    The application should be accessible at `http://localhost:3000`.

*   **Start the Celery Worker:**
    Open a new terminal window/tab in the project directory. Ensure environment variables are loaded.
    ```bash
    celery -A app.celery_app worker -l info
    ```

---

## Supabase Database Schema

The following SQL statements define the necessary tables for the application. These should be applied to your Supabase database (either the local Dockerized one or your cloud instance).

**Table: `prompts`**
*(SQL for `prompts` table as previously defined - no change)*
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
*(SQL for `results` table as previously defined - no change)*
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
**Note on RLS (Row Level Security):** If you are using the `anon` key for Supabase (especially a cloud instance), ensure you have appropriate RLS policies set up on the `prompts` and `results` tables to allow read/write access as needed by your application logic. For backend services like Celery workers using the `service_role` key, RLS is bypassed.

---

## How to Use (Applies to Both Setups)

1.  Open your web browser and navigate to `http://localhost:3000`.
2.  Enter your decision prompt or question into the input field (e.g., "What are the pros and cons of learning Python vs. JavaScript for web development?").
3.  Click the "Submit Prompt" button.
4.  The application will indicate that the prompt is being processed. You'll see a prompt ID.
5.  Click the "Refresh Results" button periodically.
    *   The status message will update as the background tasks (information retrieval, summarization) complete.
    *   If there are errors during processing, an error message will be displayed.
6.  Once processing is complete, the "Summary" and "Processed Options" sections will be populated with the AI-generated content.

---

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
    *   Ensure Celery workers and the Reflex app can connect to Redis.

4.  **Supabase:**
    *   For production, typically use a Supabase Cloud project.
    *   Ensure network rules (if any) allow connections from your deployed Reflex app and Celery workers.

5.  **Environment Variables:**
    *   Securely manage all environment variables (Supabase URL/keys, OpenAI API key, Redis URL) in your deployment environment. Do not hardcode them.

**General Workflow for Deployment:**
*   Containerize the Reflex app and Celery workers using Docker for easier deployment and management (as per the Docker setup described).
*   Set up a CI/CD pipeline to automate testing and deployment.
*   Configure logging and monitoring for all components.

This README provides a comprehensive guide to understanding, setting up, and running the AI Decision Support Tool.
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
