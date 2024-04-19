Steps to setup the Microbiome FAIR database locally:
1. Download and install Docker
2. Clone Supabase repository from https://github.com/supabase/supabase
3. Open terminal or powershell and set current directory to supabase/docker (cd supabase/docker)
4. Copy .env.example as .env (cp .env.example .env for linux & copy .env.example .env for windows)
5. Edit the .env file to insert credentials, to make it secure follow instructions at https://supabase.com/docs/guides/self-hosting/docker#securing-your-services
For a simple setup, change the following fields:POSTGRES_PASSWORD, JWT_SECRET, ANON_KEY, SERVICE_ROLE_KEY, DASHBOARD_USERNAME and DASHBOARD_PASSWORD 
6. Use Docker compose (docker compose pull)
7. Start the services with docker compose up -d (remove -d if you do not wish to detach the process)
8. Now edit the credentials and other necessary steps in the app.py file
9. Run the app.py file (you could use: python app.py from terminal)
10. Set timeout value to a large value in line 811 of _client.py in httpx package (or change with arguments)
10. You can use the "Running on http://xxx.xxx.xxx.xxx" IP to access the dashboard for uploading and querying data
11. Users can be manually added through http://xxx.xxx.xxx.xxx:xxxx/project/default/auth/users

Steps to integrate Microbiome FAIR database with LLM (ChatGPT in this case)
1. Clone the chatgpt plugin repo from https://github.com/openai/chatgpt-retrieval-plugin
2. install supabase cli with npm i supabase --save-dev