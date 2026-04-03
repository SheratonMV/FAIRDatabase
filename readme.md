# FAIRDatabase

Steps to set up and use the Microbiome FAIR Database locally.

---

## Table of Contents

- [Quick Start (Docker)](#quick-start-docker)
- [Quick Start (Podman)](#quick-start-podman)
- [Development Setup (Run Flask locally)](#development-setup-run-flask-locally)
- [Running Tests](#running-tests)
- [Application Routes](#application-routes)
  - [Authentication](#authentication)
  - [Dashboard](#dashboard)
  - [Data Management](#data-management)
  - [Privacy Routes](#privacy-routes)

---

## Quick Start (Docker)

The fastest way to get everything running. Requires only [Docker](https://docs.docker.com/get-docker/) installed.

There are two ways to start the application: an automatic setup for quickly testing it out, and a manual setup if you want to set your own passwords.

### Option A: Fully Automatic Setup (Zero Config)

If you just want to try it out quickly and don't care about setting your own passwords, use the automatic setup:

```bash
# 1. Generate all required passwords and configuration files automatically
bash scripts/bootstrap.sh --auto

# 2. Start the application
cd backend
docker compose up -d
```

> **Note:** The generated passwords (including the one for the Supabase Studio dashboard) will be printed in your terminal output. Save them somewhere safe!

### Option B: Manual Setup (Set Your Own Passwords)

If you want to choose your own passwords for better security or local development:

#### 1. Create the Environment File

```bash
cp backend/.env.example backend/.env
```

#### 2. Configure Environment Variables

Open the newly created `backend/.env` file in any text editor. You **must** change the following three variables from `change-me` to secure passwords of your choice:

- `POSTGRES_PASSWORD`: The password for your PostgreSQL database. Make this secure.
- `DASHBOARD_PASSWORD`: The password you will use to log into the Supabase Studio dashboard (the username is always `supabase`).
- `SECRET_KEY`: A secret key used by the Flask application to keep user sessions secure. A long, random string of characters works best.

**Optional Variables (Leave as defaults unless needed):**
- `SITE_URL`: Where the app runs (default: `http://localhost:5000`).
- `SMTP_*`: Email server settings. Leave blank if you don't need the app to send real emails.
- `DISABLE_SIGNUP`: Set to `true` to stop new users from registering.
- `ENABLE_EMAIL_AUTOCONFIRM`: Set to `true` so new users don't have to verify their email address (great for local testing).

#### 3. Bootstrap and Launch

Once your `.env` file is saved, run the bootstrap script. This will use your passwords to generate all the necessary security keys (like JWT tokens) and configure the database.

```bash
# Generate keys and configs based on your .env file
bash scripts/bootstrap.sh

# Start all the services in the background
cd backend
docker compose up -d
```

### Access the Application

Once the services are running, you can access the different parts of the application in your web browser:

| Service | URL | Description |
|---|---|---|
| **Main Application** | http://localhost:5000 | The main FAIRDatabase website where users log in and manage data. |
| **Database Dashboard** | http://localhost:3000 | Supabase Studio: A visual interface to view and manage your database tables. (Login with username `supabase` and your `DASHBOARD_PASSWORD`). |
| **API Endpoint** | http://localhost:8000 | The underlying Supabase API URL (usually only needed for development). |

To get started, go to http://localhost:5000/auth/register to create your first user account.

### Stopping and Resetting

If you need to stop the application or want to wipe the data and start over:

```bash
cd backend

# Stop all services but KEEP your data
docker compose down

# Stop all services AND DELETE all data (factory reset)
docker compose down -v
```

---

## Quick Start (Podman)

```bash
# One-time setup
bash scripts/podman-setup.sh

# Then same workflow as Docker
cp backend/.env.example backend/.env
# Edit backend/.env with your passwords
bash scripts/bootstrap.sh
cd backend
podman-compose up -d
```

---

## Running Tests

### Containerized tests (recommended)

Run the full test suite against the live Supabase stack:

```bash
cd backend

# Unit + integration tests (pytest)
docker compose -f docker-compose.yml -f docker-compose.test.yml run --rm test-runner

# Edge function tests (security, output validation, Aitchison distance)
docker compose -f docker-compose.yml -f docker-compose.test.yml run --rm edge-test-runner
```

### Local tests (without Docker)

Requires a running Supabase instance and Python venv:

```bash
cd backend
source venv/bin/activate
export PYTHONPATH=$(pwd)/..
./run_test.sh                     # excludes slow tests
pytest                            # all tests including slow ones
pytest tests/auth/test_authentication.py -v   # single file
```

---

## Development Setup (Run Flask locally)

If you are a developer and prefer to run the Flask application directly on your machine (outside of Docker) so you can easily edit the code, while keeping the Supabase database inside Docker.

### Dependencies

- Python 3.10
- Node.js 18.17+ (for Supabase CLI, optional)

### Supabase setup

1. Set your passwords and bootstrap:
    ```bash
    cp backend/.env.example backend/.env
    # Edit backend/.env with your passwords as described in the Quick Start
    bash scripts/bootstrap.sh
    ```

2. Start only the database and Supabase services (this will still run in Docker):
    ```bash
    cd backend
    docker compose up -d
    ```

### Flask setup

1. Navigate to the `backend` directory:
    ```bash
    cd backend
    ```

2. Set up a Python virtual environment to isolate your dependencies:
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

3. Install the required Python packages:
    ```bash
    pip install -r requirements.txt
    ```

4. Update your `backend/.env` file so the local Flask app knows how to connect to the Dockerized database. Change these values in your `.env` file:
    ```
    POSTGRES_HOST=127.0.0.1
    POSTGRES_PORT=5433
    SUPABASE_URL=http://localhost:8000
    ```

5. Start the Flask development server:
    ```bash
    ./run.sh
    ```
    
The application will now be running at `http://localhost:5000` and will automatically reload if you make changes to the Python code.

---

## Application Routes

### Authentication

#### `/auth/login` (**POST**) – Logs in a user. Requires a JSON body with the following fields:

- `username` (string)
- `password` (string)

#### Responses:
- **200**: Redirect to dashboard upon successful login.
- **400**: Missing username or password in the request.
- **401**: Invalid username or password.
- **429**: Too many requests (rate-limited).

#### `/auth/register` (**POST**) – Registers a new user. Requires a JSON body with the following fields:
- `email` (string)
- `username` (string)
- `password` (string)

In addition to that, both `email` and `username` must be unique.

#### Responses:
- **200**: Redirect to homepage upon successful registration.
- **400**: Missing form data or weak password.
- **429**: Too many requests (rate-limited).
- **500**: Internal server error (including retryable errors).

---

### Dashboard

#### `/dashboard` (**GET**) – Displays the user dashboard. Requires the user to be logged in.

#### Responses:
- **200**: Renders the dashboard page with the user's email and the current request path.

#### `/upload` (**POST**) – Uploads a CSV file, processes it, and stores chunks in PostgreSQL tables. Requires a multipart form-data body with the following fields:

- `file` (file): The CSV file to upload. This field is required.
- `description` (string, optional): An optional description of the file.
- `origin` (string, optional): The origin/source of the data.

#### Responses:
- **200**: File uploaded and processed successfully.
- **400**: Error during file processing (e.g., missing file, invalid CSV format).

#### `/display` (**GET**, **POST**) – Searches and downloads filtered database tables as zipped CSV files. Requires the user to be logged in.

#### Parameters:
- `user` (session, string): The session identifier of the logged-in user.
- `search_term` (session, array of strings): A list of search parameters:
  - `column_name` (string): The column to search.
  - `match_value` (string): The value to match against.
  - `is_zero_filter` (boolean): Flag to filter for rows where the value is zero.

#### Responses:
- **200**: A ZIP file containing matched table CSVs.
- **400**: Invalid input or query failure.
- **401**: User not logged in.
- **404**: No matching data found.
- **500**: Query execution or schema failure.

#### `/update` (**GET**, **POST**) – Renders and handles user update requests. Requires the user to be logged in.

#### Parameters:
- `user_email` (session, string): The email of the logged-in user.

#### Responses:
- **200**: Renders the update page for the user.
- **401**: User not logged in.
- **404**: Column not found in any table.
- **500**: Internal server error during update operation.

#### `/table_preview` (**GET**, **POST**) – Previews the table data and displays metadata statistics. Requires the user to be logged in.

#### Parameters:
- `search_term` (session, string, optional): The term used to search within table columns.
- `table_name` (query, string, required): The name of the table to preview.

#### Responses:
- **200**: Renders the preview of the table with metadata statistics.
- **400**: Table name is missing or invalid request.
- **401**: User not logged in.
- **404**: Table not found in the specified schema.
- **500**: Internal server error during data fetching or query execution.

#### `/return_to_dashboard` (**GET**) – Returns the user to the dashboard and resets session flags related to file upload and data review. Requires the user to be logged in.

#### Parameters:
- `user_email` (session, string): The email of the currently logged-in user.

#### Responses:
- **200**: Renders the dashboard page and resets session flags.
- **401**: User not logged in.

---

### Data Management

#### `/data_generalization` (**GET**, **POST**) – Perform data generalization through a user-guided, stepwise process. Users can upload a CSV file, review and drop columns, address missing values, select quasi-identifiers, and perform mappings for data generalization.

#### Parameters:
- `file` (formData, file): CSV file to upload for processing (optional).
- `submit_button` (formData, string): Indicates the form action submitted by the user (required). 

#### Responses:
- **200**: Data generalization form rendered, or after successful file upload and form submission.
- **401**: User not authenticated.
- **400**: Bad input or session error, such as no file uploaded or an expired session.

#### `/consolidated_return` (**GET**, **POST**) – Handles step transitions in the data generalization workflow by updating session states and redirecting to the appropriate view.

#### Parameters:
- `state` (formData, string, required): A step identifier (`"1"`, `"2"`, `"3"`, or `"4"`) used to reset or progress the session in the generalization process.

#### Responses:
- **302**: Redirect to the `/data_generalization` page with updated session context depending on the provided state.

#### `/p29score` (**GET**, **POST**) – Handles the calculation of the p29 privacy risk score based on selected quasi-identifiers and sensitive attributes from the uploaded dataset.

#### Parameters:
- `submit_button` (formData, string, required): Indicates the submitted action (e.g., "Calculate Score").
- `quasi_identifiers` (formData, array of strings, optional): List of selected quasi-identifying columns.
- `sensitive_attributes` (formData, array of strings, optional): List of selected sensitive attribute columns.

#### Responses:
- **200**:
  - On GET: Renders the p29 score form.
  - On POST: Renders form with calculated p29 score if valid input is provided.
- **400**:
  - If session is expired or file is missing/corrupt.
  - If quasi-identifiers and sensitive attributes overlap or are not provided.

---

### Index Route

`/` (**GET**) – Renders the homepage based on whether the user is authenticated.

#### Responses:
- **200**:
  - If the user is logged in (`"user"` in session): renders `/dashboard/dashboard.html`.
  - If the user is not logged in: renders `/auth/login.html`.
- **401**: Not explicitly returned, but unauthenticated access implicitly results in rendering the login page.

---

### Privacy Processing Route

`/privacy_processing` (**GET**) – Runs privacy enforcement and computes privacy metrics on the uploaded dataset.

#### Responses:
- **200**:
  - If the uploaded file exists and is valid, renders `/data/privacy_processing.html` with:
    - `p29` score
    - `k-anonymity`, `l-diversity`, `t-closeness` values
    - Lists of problems and reasons (top 10 each)
- **400**:
  - If the uploaded file is missing, empty, or cannot be read
  - If the session is expired or `uploaded_filepath` is not found
- **401**:
  - Returned if the user is not authenticated (enforced via `@login_required(api=True)`)

---

`/differential_privacy` (**GET**, **POST**) – Adds differential privacy noise to selected columns of the uploaded dataset.

#### Responses:
- **200**:
  - **GET**: Renders `/privacy/differential_privacy.html` with a list of columns (excluding quasi-identifiers and sensitive attributes).
  - **POST**: If valid columns are selected, adds noise, updates the dataset, and re-renders the page with confirmation.
- **400**:
  - If the uploaded file is missing or unreadable.
  - If selected columns are invalid (e.g., overlapping or incomplete selection).
- **401**:
  - Returned if the user is not authenticated (enforced via `@login_required(api=True)`).
