## FAIRDatabase
Steps to setup the Microbiome FAIR database locally:

**Supabase and Docker setup:**
1. Download and install Docker
2. Clone Supabase repository using: `git clone --depth 1 https://github.com/supabase/supabase`
3. To avoid errors when composing, go to the docker-compose.yml file and comment out the line `GOTRUE_EXTERNAL_ANONYMOUS_USERS_ENABLED: ${ENABLE_ANONYMOUS_USERS}`
4. Open terminal or powershell and go to the docker folder using `cd supabase/docker`
5. Copy .env.example as .env using `cp .env.example .env`
6. Edit the .env file to insert credentials, to make it secure follow instructions at https://supabase.com/docs/guides/self-hosting/docker#securing-your-services. For a simple setup, change the following fields: POSTGRES_PASSWORD, JWT_SECRET, ANON_KEY, SERVICE_ROLE_KEY, DASHBOARD_USERNAME and DASHBOARD_PASSWORD
7. Pull the latest images using `docker compose pull`
8. Remove logflare integration if not required. A sample docker compose file is included in the developer files
9. Start the services (in detached mode) using `docker compose up -d`
10. Then, open the Supabase dashboard using the localhost `http://localhost:8000`
11. In this dashboard, add yourself as a user in the authentication tab.

**App.py:**
1. Edit the `SUPABASE_PUBLIC_KEY` using the `ANON_KEY` defined in the .env file. 
2. Edit the Postgres connection password in all relevant areas, such as these lines: 
`database_connection = psycopg2.connect(host="localhost",port="5432",database="",user="postgres",password="<password>")`
3. Run the app.py file (you could use: python app.py from terminal)
5. You can use the "Running on http://xxx.xxx.xxx.xxx" IP to access the interface. 

Steps to integrate Microbiome FAIR database with LLM (ChatGPT in this case)
1. Clone the chatgpt plugin repo from https://github.com/openai/chatgpt-retrieval-plugin
2. install supabase cli with npm i supabase --save-dev
