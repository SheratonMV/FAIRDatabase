# FAIRDatabase

Steps to set up and use the Microbiome FAIR Database locally.

---

## Table of Contents

- [Dependencies](#dependencies)
- [Setup (Debian/Ubuntu)](#setup-debianubuntu)
- [Usage](#usage)
- [Development Instructions](#development-instructions)
- [Application Routes](#application-routes)
  - [Authentication](#authentication)
  - [Dashboard](#dashboard)
  - [Data Management](#data-management)
  - [Privacy Routes](#privacy-routes)

---

## Dependencies

### Minimally Required

- Node.js 18.17.0
- Python 3.10

### Recommended

- Node.js 20.15.0 (LTS)
- Python 3.10
- python3-venv

---

## Setup (Debian/Ubuntu)

### Supabase and Docker setup

1. Download and install Docker Desktop from https://www.docker.com/products/docker-desktop/

2. Clone the Supabase repository:
    ```bash
    git clone --depth 1 https://github.com/supabase/supabase
    ```

3. To avoid errors when composing, go to the `docker-compose.yml` file and comment out the line:
    ```bash
    GOTRUE_EXTERNAL_ANONYMOUS_USERS_ENABLED: ${ENABLE_ANONYMOUS_USERS}
    ```

4. Open the `docker` folder inside the Supabase directory:
    ```bash
    cd supabase/docker
    ```

5. Copy `.env.example` as `.env`:
    ```bash
    cp .env.example .env
    ```

6. Edit the `.env` file to insert credentials, make sure to follow instructions at:
    ```bash
    https://supabase.com/docs/guides/self-hosting/docker#securing-your-services
    ```

    For a simple setup, change the following fields:
    ```bash
    POSTGRES_PASSWORD, JWT_SECRET, ANON_KEY, SERVICE_ROLE_KEY, DASHBOARD_USERNAME and DASHBOARD_PASSWORD
    ```

7. Pull the latest images:
    ```bash
    docker compose pull
    ```

8. Remove logflare integration if not required. A sample docker-compose file is included in the developer files.

9. Edit the follwing field inside `docker-compose.yml` file:
    ```bash
    GOTRUE_MAILER_AUTOCONFIRM: true
    ```


11. Start the services (in detached mode):
    ```bash
    docker compose up -d
    ```

12. Open the Supabase dashboard:
    ```bash
    http://localhost:8000
    ```

    In this dashboard, add yourself as a user in the authentication tab.

### Flask setup

Assuming the current working directory is the root of the project:

1. Navigate to the `backend` directory:
    ```bash
    cd backend
    ```

2. Sync dependencies using uv (automatically creates virtual environment):
    ```bash
    uv sync --all-groups
    ```

3. Activate the virtual environment (optional, uv run handles this automatically):
    ```bash
    source .venv/bin/activate
    ```

4. Set up the environment:
    ```bash
    touch .env
    ```

5. Edit the created `.env` file using any code editor to configure the credentials generated during the finalization of the Supabase Docker setup:
    ```
    SECRET_KEY=<SECRET_KEY_BASE>
    UPLOAD_FOLDER=./uploads
    ALLOWED_EXTENSIONS=csv

    SUPABASE_URL=http://localhost:8000
    SUPABASE_KEY=<ANON_KEY>
    SUPABASE_SERVICE_KEY=<SERVICE_KEY>

    POSTGRES_DB_NAME=postgres
    POSTGRES_USER=postgres
    POSTGRES_SECRET=<POSTGRES_PASSWORD>
    POSTGRES_PORT=5433
    POSTGRES_HOST=127.0.0.1
    ```

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
