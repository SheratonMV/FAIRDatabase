### TO DO ###
# query metadata

# levels of access
# layout
# Open AI

from flask import Flask, session, request, render_template, redirect, url_for, make_response
import matplotlib.pyplot as plt

import plotly.graph_objs as go
from supabase import create_client, Client
from werkzeug.utils import secure_filename
from zipfile import ZipFile
from hashlib import sha256
from io import StringIO, BytesIO
import pandas as pd
import psycopg2
import zipfile
import math
import time
import os
import re
import io
import json

app = Flask(__name__)
app.secret_key = os.urandom(1)

SUPABASE_URL = 'http://localhost:8000'
SUPABASE_PUBLIC_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.ewogICJyb2xlIjogImFub24iLAogICJpc3MiOiAic3VwYWJhc2UiLAogICJpYXQiOiAxNzE0ODYwMDAwLAogICJleHAiOiAxODcyNjI2NDAwCn0.87CKUUqmCE6oZhyExthSKEDCGBnuZqhTdOUbgQtxsCE'

supabase = create_client(SUPABASE_URL, SUPABASE_PUBLIC_KEY)
client: Client = supabase

def filter_characters(string):
    filtered_string = re.sub(r'[^a-zA-Z0-9_]', '_', string)
    return filtered_string


@app.route('/')
def home():
    if 'user' in session:
        return render_template('dashboard.html')
    return render_template('login.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    email_user = request.form['email'] 
    password_user = request.form['password'] 

    user = client.auth.sign_in_with_password({ "email": email_user, "password": password_user })
    if 'error' not in user: 
        session['email'] = email_user
        print (dir(session), session.update({"user":1}))
        users_table = client.table('users')
        user = users_table.select().eq('email', email_user).single()
        return redirect('/dashboard')
        
        if user:
            return redirect('/dashboard')
        else:
            return 'User not found'
        
    else:
        return 'Login failed'
    

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'GET':
        return render_template('register.html')
    if request.method == 'POST':
        if 'Login' in request.form:
            return redirect('/')
        else:
            email = request.form['email']
            password = request.form['password']
            resp = client.auth.sign_up(email, password)
            print("DIT IS DE RESPONSE: ", resp)
            if 'error' not in resp:
                user = resp['user']
                user_id = user['id']
                client.table('auth.users').update({'password': password}).eq('id', user_id).execute()
                return redirect('/')
            else:
                if resp['code'] is not None:
                    return render_template('register.html', error_message=resp['msg'])
                else:
                    return render_template('register.html', error_message='Unknown error')

@app.route('/dashboard')
def dashboard():
    if 'user' in session:
        user_email = session['email']

        return render_template('dashboard.html', user_email=user_email,current_path=request.path)
    else:
        return redirect('/')

@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if 'user' in session:
        user_email = session['email']
        if request.method == 'POST':       
            
            uploaded_file = request.files['file']
            
            if uploaded_file.filename == '':
                return render_template('upload.html', error_message='No file selected.', user_email=user_email, current_path=request.path)
            elif not uploaded_file and uploaded_file.filename.endswith('.csv'):
                return render_template('upload.html', error_message='Invalid file format. Please upload a .txt file.', user_email=user_email, current_path=request.path)
        
            elif uploaded_file and uploaded_file.filename.endswith('.csv'):
                upload_timer = time.time()
        
                uploaded_file.save('uploadfolder/' + secure_filename(uploaded_file.filename))
                
                with open('uploadfolder/' + secure_filename(uploaded_file.filename), 'r') as uploaded_file_load:
                    file_loaded_lines = uploaded_file_load.readlines()
                    
                    # Get input from user
                    description = request.form['description']
                    origin = request.form['origin']

                    # Table name creation based on time uploaded
                    time_c = time.gmtime()
                    time_c_text = ( f"_{time_c.tm_year}{time_c.tm_mon}{time_c.tm_mday}{time_c.tm_hour}{time_c.tm_min}{time_c.tm_sec}")
                    file_name = str(secure_filename(uploaded_file.filename)).rsplit('.', 1)[0] + time_c_text
                    
                    # Connect to database
                    database_connection = psycopg2.connect(host="localhost",port="5432",database="",user="postgres",password="7sJYfI5dHJs27zie2Cpy")
                    cursor_database = database_connection.cursor()

                    # Set column limit to 1200, leaving space for adding columns
                    column_limit = 1200     # Supabase soft locks at 1600 
                    
                    # Split sequence values from patient value
                    all_column_names = file_loaded_lines[0].strip().split(',')
                    column_names = all_column_names[1:]
                    column_patient = all_column_names[0]
                    
                    # Set amount of sub tables
                    table_amount = math.ceil(len(all_column_names)/column_limit)

                    # For every sub table upload to 
                    for i in range(table_amount):
                        j = i + 1
                        # Table name creation
                        table_name = f"{file_name}_p{j}"
                        
                        
                        # Set upper and lower bound for columns per sub table
                        column_lower_limit = column_limit * i
                        column_upper_limit = column_limit * j
                        

                        columnz = column_names[column_lower_limit:column_upper_limit]
                        print("-------------------------------------------")
                        print(len(all_column_names))
                        print(column_lower_limit,column_upper_limit)
                        print(len(column_names))
                        print(len(columnz))

                        # Filter for impermissible column characters
                        columns_filtered = [filter_characters(item) for item in columnz] 
                        print(len(columns_filtered))
                        # Query preparation
                        columns_text_c = ", ".join([f'{column} INT' for column in columns_filtered]) # used for table creation
                        columns_text_i = ", ".join([f'{column}' for column in columns_filtered]) # used for value insertion
                        print(len(columns_text_c))
                        # Table creation query
                        sql_query = f"CREATE TABLE _realtime.{table_name} (rowid SERIAL PRIMARY KEY,{column_patient} VARCHAR NOT NULL, metadata TEXT, {columns_text_c});"
                        cursor_database.execute(sql_query)
                        
                        
                        database_connection.commit()

                        # total amount of rows minus the column row
                        total_lines = len(file_loaded_lines) 
                        
                        for row in file_loaded_lines[1:]:
                            
                            # Get row and split sequence values from patient value
                            all_row_values = row.strip().split(',')
                            row_values = all_row_values[1:]
                            row_patient_column = all_row_values[0]

                            # Set upper and lower bound for columns for row
                            row_values = row_values[column_lower_limit:column_upper_limit]

                            # Query preparation
                            values_text_i = ", ".join([f"{value}" for value in row_values])
                            
                            # base_dict = {column_names[0]:row_values[0]}
                            # dict_to_append = {column_names_test[i]: row_values_i[i] for i in range(len(column_names_test))}
                            # base_dict.update(dict_to_append)
                            # supabase.table(file_name).insert(base_dict).execute()

                            # Value insertion query
                            query = f"INSERT INTO _realtime.{table_name}  ({column_patient},{columns_text_i}) VALUES ('{sha256(row_patient_column.encode('utf-8')).hexdigest()}', {values_text_i});"
                            cursor_database.execute(query)

                        # Add table info to metadata table
                        meta_query = f"INSERT INTO _realtime.metadata_tables (table_name, main_table, description, origin) VALUES ('{table_name}','{file_name}','{description}','{origin}')"
                        cursor_database.execute(meta_query)     
                            
                    database_connection.commit()  
                    database_connection.close()

                # Remove file locally
                os.remove('uploadfolder/' + uploaded_file.filename)
                
                # Clear progress from session
                session.pop('progress', None)
                
                # Display time
                upload_timer = str(round(time.time() - upload_timer, 2))
                print(f"--- {upload_timer.replace('.', ',')[:5]} seconds, {total_lines} rows, {len(all_column_names)} columns---")   

                return "File uploaded successfully."
        else:
            return render_template('upload.html', user_email=user_email, current_path=request.path)
    else:
        return redirect('/')


@app.route('/search', methods=['GET', 'POST'])
def search():
    if 'user' in session:
        user_email = session['email']
        if request.method == 'GET':
            upload_timer = time.time()
            # Connect to database
            database_connection = psycopg2.connect(host="localhost", port="5432", database="", user="postgres", password="7sJYfI5dHJs27zie2Cpy")
            cursor_database = database_connection.cursor()

            # Get table names from the 'public' schema
            sql_query = "SELECT DISTINCT table_name FROM information_schema.tables WHERE table_schema = 'public'"
            cursor_database.execute(sql_query)
            table_names = cursor_database.fetchall()
            table_names = [table[0] for table in table_names]

            database_connection.close()

            # Render template with table names
            upload_timer = str(round(time.time() - upload_timer, 2))
            print(f"--- {upload_timer.replace('.', ',')[:5]} seconds, ")
            return render_template('search.html', table_names=table_names, user_email=user_email, current_path=request.path)

        elif request.method == 'POST':
            if 'Download' not in request.form:
                search_term = request.form.get('search', '')
                seq_na = request.form.get('value0')
                seq_a = request.form.get('value1')
                session["search_term"] = [search_term, seq_a, seq_na]

                # Connect to database
                database_connection = psycopg2.connect(host="localhost", port="5432", database="", user="postgres", password="7sJYfI5dHJs27zie2Cpy")
                cursor_database = database_connection.cursor()

                sql_query = f"SELECT DISTINCT table_name FROM information_schema.columns WHERE column_name LIKE '%{search_term}%' AND table_schema = 'public'"
                cursor_database.execute(sql_query)
                search_results = cursor_database.fetchall()
                search_results = [result[0] for result in search_results]

                database_connection.close()

                # Retrieve the original table names to always display them
                database_connection = psycopg2.connect(host="localhost", port="5432", database="", user="postgres", password="7sJYfI5dHJs27zie2Cpy")
                cursor_database = database_connection.cursor()

                sql_query = "SELECT DISTINCT table_name FROM information_schema.tables WHERE table_schema = 'public'"
                cursor_database.execute(sql_query)
                table_names = cursor_database.fetchall()
                table_names = [table[0] for table in table_names]

                database_connection.close()

                return render_template('search.html', search_results=search_results, search_term=search_term, 
                                       table_names=table_names, user_email=user_email, current_path=request.path)
            if 'Download' in request.form:
                return redirect(url_for('display'))

    else:
        return redirect('/')

    

@app.route('/display', methods=['GET', 'POST'])
def display():
    if 'user' in session:
        user_email = session['email']
        print(request.method, session.get("search_term"))
        upload_timer = time.time()
        if request.method == 'GET' and session.get("search_term") != None:
            # Get search term
            search_term = session.get("search_term")

            # Database connection
            database_connection = psycopg2.connect(host="localhost",port="5432",database="",user="postgres",password="7sJYfI5dHJs27zie2Cpy")
            cursor_database = database_connection.cursor()
            
            # Get tables where search term is part of
            sql_query = f"SELECT table_name, column_name FROM information_schema.columns WHERE column_name like '%{search_term[0]}%'"
            cursor_database.execute(sql_query)
            table_names = cursor_database.fetchall()
            
            
            results = {}
            search_results = list()
            totalrows = 0
            totalcolumns = 0

            if search_term[1] != None and search_term[2] != None:
                for table, column in table_names:
                    query_rows = f"Select * FROM _realtime.{table}"
                    cursor_database.execute(query_rows)
                    rows = cursor_database.fetchall()
                    totalrows += len(rows)
                    
                    # Get columns
                    query_columns = f"SELECT column_name FROM information_schema.columns WHERE table_schema = '_realtime' AND table_name = '{table}'"
                    cursor_database.execute(query_columns)
                    columns = cursor_database.fetchall()

                    # Make dataframe of table for export
                    columns = [column[0] for column in columns]
                    df = pd.DataFrame(list(rows),columns=columns)
                    df.drop(df.columns[[0]], axis=1, inplace=True)
                    #df = df.to_dict(orient='records')
                    totalcolumns += len(columns)
                    
                    results[table] = df
                    search_results.append([table, len(rows)])
                    

            elif search_term[1] != None:
                for table, column in table_names:
                    # Get rows
                    query_rows = f"Select * FROM _realtime.{table} WHERE {column} > 0"
                    cursor_database.execute(query_rows)
                    rows = cursor_database.fetchall()
                    totalrows += len(rows)
                    
                    # Get columns
                    query_columns = f"SELECT column_name FROM information_schema.columns WHERE table_schema = '_realtime' AND table_name = '{table}'"
                    cursor_database.execute(query_columns)
                    columns = cursor_database.fetchall()

                    # Make dataframe of table for export
                    columns = [column[0] for column in columns]
                    df = pd.DataFrame(list(rows),columns=columns)
                    df.drop(df.columns[[0]], axis=1, inplace=True)
                    totalcolumns += len(columns)
                    
                    results[table] = df
                    search_results.append([table, len(rows)])

            elif search_term[2] != None:
                for table, column in table_names:
                    query_rows = f"Select * FROM _realtime.{table} WHERE {column} = 0"
                    cursor_database.execute(query_rows)
                    rows = cursor_database.fetchall()
                    totalrows += len(rows)
                    
                    # Get columns
                    query_columns = f"SELECT column_name FROM information_schema.columns WHERE table_schema = '_realtime' AND table_name = '{table}'"
                    cursor_database.execute(query_columns)
                    columns = cursor_database.fetchall()
                    totalcolumns += len(columns)

                    # Make dataframe of table for export
                    columns = [column[0] for column in columns]
                    df = pd.DataFrame(list(rows),columns=columns)
                    df.drop(df.columns[[0]], axis=1, inplace=True)
                    #df = df.to_dict(orient='records')
                    
                    results[table] = df
                    search_results.append([table, len(rows)])

            database_connection.close()
            memory_file = BytesIO()
            
            with zipfile.ZipFile(memory_file, "w") as zf:
                for table, df in results.items():
                    csv_buffer = StringIO()
                    df.to_csv(csv_buffer, index=False)
                    zf.writestr(f"{table}.csv", csv_buffer.getvalue())

            memory_file.seek(0)

            response = make_response(memory_file.getvalue())
            response.headers['Content-Disposition'] = 'attachment; filename=tables.zip'
            response.headers['Content-Type'] = 'application/octet-stream'
            print(f"{totalrows} rows ,{totalcolumns} columns")
            print(str(round(time.time() - upload_timer, 2)))
            return response
            
        else:
            return render_template('search.html', user_email = user_email)
         
    else:
        return redirect('/')
    
@app.route('/update', methods=['GET', 'POST'])
def update():
    if 'user' in session:
        user_email = session['email']
        if request.method == 'GET':
            # row_id = request.form['row_id']
            # column_name = request.form['column_name']
            # new_value = request.form['new_value']

            # database_connection = psycopg2.connect(host="localhost",port="5432",database="",user="postgres",password="postgres")
            # cursor_database = database_connection.cursor()
            # query = f"SELECT table_name, column_name FROM information_schema.columns WHERE column_name like '{column_name}'"
            # cursor_database.execute(query)
            # query = f"UPDATE _realtime. SET {column_name} = ? WHERE rowid = {row_id}]"
            # f"SELECT column_name FROM information_schema.columns WHERE table_schema = '_realtime' AND table_name = '{table}'"
            # f"SELECT table_name, column_name FROM information_schema.columns WHERE column_name like '%{search_term[0]}%'"
            return render_template("update.html", user_email = user_email, current_path=request.path)
    else:
        return redirect("/")
    
@app.route('/table_preview', methods=['GET', 'POST'])
def table_preview():
    if 'user' in session:
        user_email = session['email']
        if request.method == 'GET':
            search_term = session.get("search_term", "")

            table_name = request.args.get('type')
            
            # Database connection
            database_connection = psycopg2.connect(host="localhost", port="5432", database="", user="postgres", password="7sJYfI5dHJs27zie2Cpy")
            cursor_database = database_connection.cursor()

            query_tables = f"SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_name = '{table_name}'"
            cursor_database.execute(query_tables)
            tables = cursor_database.fetchall()
            tables = [table[0] for table in tables]

            dfs = []
            for table in tables:
                query_columns = f"SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = '{table}'"
                cursor_database.execute(query_columns)
                columns = cursor_database.fetchall()

                query_rows = f"SELECT * FROM {table}"
                cursor_database.execute(query_rows)
                rows = cursor_database.fetchall()
                
                columns = [column[0] for column in columns]
                df = pd.DataFrame(list(rows), columns=columns)

                # Create descriptives and visualisations
                df_full = pd.DataFrame(list(rows), columns=columns)
                shape = df_full.shape
                stats_rows, stats_columns = shape[0], shape[1]
                metadata_stats = df_full['metadata'].describe()
                metadata_count = metadata_stats[0]
                metadata_unique = metadata_stats[1]
                metadata_top = metadata_stats[2]
                metadata_frequency = metadata_stats[3]
       
                df = df.iloc[:15, :8]
                dfs.append(df)

        tables_html = [df.to_html(classes='table table-bordered', header="true", index=False) for df in dfs]

        return render_template('table_preview.html', tables=tables_html, table_name=table_name, search_term=search_term,
                               stats_rows=stats_rows, stats_columns=stats_columns, metadata_stats=metadata_stats, 
                               metadata_count = metadata_count, metadata_unique = metadata_unique, metadata_top = metadata_top, 
                               metadata_frequency = metadata_frequency, user_email = user_email, current_path=request.path)


@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect('/')

@app.route('/privacy_metrics')
def privacy_metrics():
    if 'user' in session:
        user_email = session['email']

        return render_template('privacy_metrics.html', user_email=user_email,current_path=request.path)
    else:
        return redirect('/')
    
@app.route('/federated_learning')
def federated_learning():
    if 'user' in session:
        user_email = session['email']

        return render_template('federated_learning.html', user_email=user_email,current_path=request.path)
    else:
        return redirect('/')

@app.route('/documentation')
def documentation():
    if 'user' in session:
        user_email = session['email']

        return render_template('documentation.html', user_email=user_email,current_path=request.path)
    else:
        return redirect('/')
    
if __name__ == '__main__':
    app.run(debug=True)