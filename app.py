### TO DO ###
# query metadata

# levels of access
# layout
# Open AI

from flask import Flask, session, request, render_template, redirect, url_for, make_response
from flask import jsonify
import matplotlib.pyplot as plt

import numpy as np
from collections import defaultdict
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
import random


app = Flask(__name__)
app.secret_key = os.urandom(1)

SUPABASE_URL = 'http://localhost:8000'
SUPABASE_PUBLIC_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.ewogICJyb2xlIjogImFub24iLAogICJpc3MiOiAic3VwYWJhc2UiLAogICJpYXQiOiAxNzE0ODYwMDAwLAogICJleHAiOiAxODcyNjI2NDAwCn0.87CKUUqmCE6oZhyExthSKEDCGBnuZqhTdOUbgQtxsCE'

supabase = create_client(SUPABASE_URL, SUPABASE_PUBLIC_KEY)
client: Client = supabase
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['ALLOWED_EXTENSIONS'] = {'csv'}

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
    uploaded = False
    columns_dropped = False
    missing_values_reviewed = False
    quasi_identifiers_selected = False
    current_quasi_identifier = False
    all_steps_completed = False
    session['uploaded'] = uploaded
    session['columns_dropped'] = columns_dropped
    session['missing_values_reviewed'] = missing_values_reviewed
    session['quasi_identifiers_selected'] = quasi_identifiers_selected
    session['current_quasi_identifier'] = current_quasi_identifier
    session['all_steps_completed'] = all_steps_completed
    return redirect('/')

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def drop_columns(df, columns_to_drop):
    if columns_to_drop and columns_to_drop[0].lower() != 'none':
        df.drop(columns=columns_to_drop, inplace=True)
        return True
    # Return True if no columns are selected to drop (i.e., proceed to the next step without changing df)
    return True

def calculate_missing_percentages(df):
    missing_percentages = (df.isnull().sum() / len(df)) * 100
    return missing_percentages.to_dict()


def identify_quasi_identifiers_with_distinct_values(df, selected_columns):
    if not selected_columns:
        return {}, {}

    distinct_values = {col: df[col].value_counts().index.tolist() for col in selected_columns}
    quasi_identifier_values = {}
    for col in selected_columns:
        distinct_count = df[col].value_counts()
        total_count = len(df[col])
        percentages = (distinct_count / total_count) * 100
        quasi_identifier_values[col] = [(val, f"{percentages[val]:.2f}") for val in distinct_count.index]
    return distinct_values, quasi_identifier_values


def map_values_and_output_percentages(df, selected_columns, mappings):
    """
    Maps values in the selected columns to other values based on user input,
    including the ability to map to newly created values or remap values after reviewing. Outputs updated percentages.
    """
    for col in selected_columns:
        if col not in df.columns:
            continue

        if col in mappings:
            mapping = mappings[col]
            df[col] = df[col].map(lambda x: mapping.get(x, x))
    
    updated_percentages = {col: (df[col].value_counts(normalize=True) * 100).to_dict() for col in selected_columns}
    return df, updated_percentages

@app.route('/privacy_metrics', methods=['GET', 'POST'])
def privacy_metrics():
    if 'user' in session:
        user_email = session['email']
        uploaded = session.get('uploaded', False)
        columns_dropped = session.get('columns_dropped', False)
        missing_values_reviewed = session.get('missing_values_reviewed', False)
        quasi_identifiers_selected = session.get('quasi_identifiers_selected', False)
        column_names = session.get('column_names', [])
        columns_to_drop = session.get('columns_to_drop', [])
        quasi_identifiers = session.get('quasi_identifiers', [])
        quasi_identifier_values = session.get('quasi_identifier_values', {})
        distinct_values = session.get('distinct_values', {})
        current_quasi_identifier = session.get('current_quasi_identifier')
        mappings = session.get('mappings', {})
        all_steps_completed = session.get('all_steps_completed', False)
        missing_percentages = session.get('missing_percentages', {})
        updated_percentages = session.get('updated_percentages', {})
        message = None

        if request.method == 'POST':
            print("POST request received")
            if 'file' in request.files:
                file = request.files['file']
                if file and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    file.save(filepath)
                    session['uploaded_filepath'] = filepath
                    uploaded = True
                    session['uploaded'] = uploaded
                    df = pd.read_csv(filepath)
                    column_names = df.columns.tolist()
                    session['column_names'] = column_names
                    message = "File imported successfully."

            elif request.form.get('submit_button') == 'submit_columns':
                columns_to_drop = request.form.getlist('columns_to_drop')
                filepath = session.get('uploaded_filepath')
                if not filepath:
                    return jsonify({'error': 'No file uploaded or session expired.'}), 400

                df = pd.read_csv(filepath)
                if drop_columns(df, columns_to_drop):
                    df.to_csv(filepath, index=False)
                    columns_dropped = True
                    session['columns_dropped'] = columns_dropped
                    message = "Direct identifiers dropped successfully."
                    column_names = df.columns.tolist()
                    session['column_names'] = column_names
                    missing_percentages = calculate_missing_percentages(df)
                    session['missing_percentages'] = missing_percentages

            elif request.form.get('submit_button') == 'submit_missing_values':
                columns_to_drop = request.form.getlist('columns_to_drop')
                filepath = session.get('uploaded_filepath')
                if not filepath:
                    return jsonify({'error': 'No file uploaded or session expired.'}), 400

                df = pd.read_csv(filepath)
                if drop_columns(df, columns_to_drop):
                    df.to_csv(filepath, index=False)
                    missing_values_reviewed = True
                    session['missing_values_reviewed'] = missing_values_reviewed
                    message = "Columns with missing values dropped successfully."
                    column_names = df.columns.tolist()
                    session['column_names'] = column_names

            elif request.form.get('submit_button') == 'submit_quasi_identifiers':
                quasi_identifiers = request.form.getlist('quasi_identifiers')
                filepath = session.get('uploaded_filepath')
                if not filepath:
                    return jsonify({'error': 'No file uploaded or session expired.'}), 400

                df = pd.read_csv(filepath)
                if not quasi_identifiers:
                    quasi_identifiers_selected = True
                    session['all_steps_completed'] = True
                    all_steps_completed = session['all_steps_completed']
                    session['quasi_identifiers_selected'] = quasi_identifiers_selected
                    message = "No quasi-identifiers selected. Dataset has been generalized."

                else:
                    distinct_values, quasi_identifier_values = identify_quasi_identifiers_with_distinct_values(df, quasi_identifiers)
                    session['quasi_identifiers'] = quasi_identifiers
                    session['quasi_identifier_values'] = quasi_identifier_values
                    session['distinct_values'] = distinct_values
                    quasi_identifiers_selected = True
                    session['quasi_identifiers_selected'] = quasi_identifiers_selected
                    current_quasi_identifier = quasi_identifiers[0]
                    session['current_quasi_identifier'] = current_quasi_identifier
                    session['current_quasi_identifier_index'] = 0
                    message = "Quasi-identifiers selected"

            elif request.form.get('submit_button') == 'submit_mapping':
                current_quasi_identifier = session.get('current_quasi_identifier')
                filepath = session.get('uploaded_filepath')
                if not filepath:
                    return jsonify({'error': 'No file uploaded or session expired.'}), 400

                if current_quasi_identifier:
                    df = pd.read_csv(filepath)
                    if current_quasi_identifier not in mappings:
                        mappings[current_quasi_identifier] = {}
                    
                    for key in request.form:
                        if key.startswith('mapping_'):
                            _, value = key.rsplit('_', 1)  # Use rsplit to handle multiple underscores
                            mappings[current_quasi_identifier][value] = request.form[key]
                    
                    print(f"Mappings before applying: {mappings}")
                    df, updated_percentages = map_values_and_output_percentages(df, [current_quasi_identifier], mappings)
                    df.to_csv(filepath, index=False)
                    session['mappings'] = mappings
                    quasi_identifier_values[current_quasi_identifier] = updated_percentages[current_quasi_identifier]
                    session['quasi_identifier_values'] = quasi_identifier_values
                    session['updated_percentages'] = updated_percentages  # Store updated percentages in session
                    message = f"Values for '{current_quasi_identifier}' mapped successfully."
                    print(f"Updated DataFrame saved and percentages calculated for {current_quasi_identifier}")

                    current_quasi_identifier_index = session.get('current_quasi_identifier_index', 0)
                    if current_quasi_identifier_index + 1 < len(quasi_identifiers):
                        current_quasi_identifier_index += 1
                        session['current_quasi_identifier_index'] = current_quasi_identifier_index
                        session['current_quasi_identifier'] = quasi_identifiers[current_quasi_identifier_index]
                    else:
                        session['current_quasi_identifier'] = None
                        session['all_steps_completed'] = True
                        message = "All quasi-identifier values mapped successfully."
                        all_steps_completed = session['all_steps_completed']
        
        
        svgScore = random.random()
        print(svgScore)
        return render_template(
            'privacy_metrics.html',
            user_email=user_email,
            current_path=request.path,
            uploaded=uploaded,
            columns_dropped=columns_dropped,
            missing_values_reviewed=missing_values_reviewed,
            quasi_identifiers_selected=quasi_identifiers_selected,
            column_names=column_names,
            columns_to_drop=columns_to_drop,
            quasi_identifiers=quasi_identifiers,
            quasi_identifier_values=quasi_identifier_values,
            distinct_values=distinct_values,
            current_quasi_identifier=session.get('current_quasi_identifier'),
            mappings=mappings,
            message=message,
            all_steps_completed=all_steps_completed,
            missing_percentages=dict(sorted(missing_percentages.items(), key=lambda x:x[1], reverse=True)),
            updated_percentages=dict(sorted(updated_percentages.items(), key=lambda x:x[1], reverse=True)), svgScore=svgScore  # Pass updated percentages to the template
        )
    else:
        return redirect(url_for('login'))




@app.route('/consolidated_return', methods=['GET', 'POST'])
def consolidated_return():
    state = request.form.get('state')
    if state == '1':
        uploaded = False
        columns_dropped = False
        missing_values_reviewed = False
        quasi_identifiers_selected = False
        current_quasi_identifier = False
        all_steps_completed = False
        session['uploaded'] = uploaded
        session['columns_dropped'] = columns_dropped
        session['missing_values_reviewed'] = missing_values_reviewed
        session['quasi_identifiers_selected'] = quasi_identifiers_selected
        session['current_quasi_identifier'] = current_quasi_identifier
        session['all_steps_completed'] = all_steps_completed
        return redirect('/privacy_metrics')
    elif state == '2':
        uploaded = True
        columns_dropped = False
        session['uploaded'] = uploaded
        session['columns_dropped'] = columns_dropped
        return redirect('/privacy_metrics')
    elif state == '3':
        uploaded = True
        columns_dropped = True
        missing_values_reviewed = False
        session['uploaded'] = uploaded
        session['columns_dropped'] = columns_dropped
        session['missing_values_reviewed'] = missing_values_reviewed
        return redirect('/privacy_metrics') 
    elif state == '4':
        uploaded = True
        columns_dropped = True
        missing_values_reviewed = True
        quasi_identifiers_selected = False
        current_quasi_identifier = False
        session['uploaded'] = uploaded
        session['columns_dropped'] = columns_dropped
        session['missing_values_reviewed'] = missing_values_reviewed
        session['quasi_identifiers_selected'] = quasi_identifiers_selected
        session['current_quasi_identifier'] = current_quasi_identifier
        return redirect('/privacy_metrics') 
    return redirect('/privacy_metrics') 


@app.route('/federated_learning')
def federated_learning():
    if 'user' in session:
        user_email = session['email']
        return render_template('federated_learning.html', user_email=user_email,current_path=request.path)
    else:
        return redirect('/')
    
df = pd.read_csv('df8.csv')
    
@app.route('/p29score', methods=['GET', 'POST'])
def p29score():
    if 'user' in session:
        user_email = session['email']
        
        if request.method == 'POST':
            quasi_identifiers = request.form.getlist('quasi_identifiers')
            sensitive_attributes = request.form.getlist('sensitive_attributes')

            if quasi_identifiers and sensitive_attributes:
                result = calculate_p29_score(df, quasi_identifiers, sensitive_attributes)
                
                p29result = round(result['P_29 Score'], 3)
                minlresult = round(result['Minimum normalized l-value'], 3)
                maxtresult = float(round(result['Maximum t-value'], 3))
                k_anonresult = result['Minimum k-anonymity']
                reason_result = [reason for reason in result['Reasons']]    
                problems_result = [problem for problem in result['Problematic info']]
                
                return render_template('p29score.html', user_email=user_email, current_path=request.path, result=result, 
                                       columns=df.columns, p29result=p29result, minlresult=minlresult, maxtresult=maxtresult,
                                       k_anonresult=k_anonresult, reason_result=reason_result, problems_result=problems_result)
            else:
                return render_template('p29score.html', user_email=user_email, current_path=request.path, columns=df.columns, error="Please select both quasi-identifiers and sensitive attributes.")
        return render_template('p29score.html', user_email=user_email, current_path=request.path, columns=df.columns)
    else:
        return redirect('/')

def calculate_p29_score(df, quasi_identifiers, sensitive_attributes):
    def calculate_k_anonymity(group):
        return len(group)

    def calculate_normalized_entropy(series):
        if series.empty:
            return 0
        value_counts = series.value_counts(normalize=True)
        total_entropy = 0
        for count in value_counts:
            if count > 0:
                total_entropy -= count * np.log2(count)
        unique_values = series.nunique()
        if unique_values == 1:
            return 0
        normalized_entropy = total_entropy / np.log2(unique_values)
        return normalized_entropy

    results = defaultdict(list)
    grouped = df.groupby(quasi_identifiers)
    for name, group in grouped:
        k_anonymity = calculate_k_anonymity(group)
        for attribute in sensitive_attributes:
            normalized_entropy = calculate_normalized_entropy(group[attribute])
            results[f'Normalized Entropy l-diversity_{attribute}'].append(normalized_entropy)
        quasi_identifier_values = ', '.join(f"{qi}: {group[qi].iloc[0]}" for qi in quasi_identifiers)
        results['Quasi-identifiers'].append(quasi_identifier_values)
        results['k-anonymity'].append(k_anonymity)

    results_df = pd.DataFrame(results)

    def calculate_t_closeness(df, quasi_identifiers, sensitive_attributes):
        results = []
        grouped = df.groupby(quasi_identifiers)
        global_distributions = {}
        for attribute in sensitive_attributes:
            global_distributions[attribute] = calculate_global_distribution(df[attribute])
        for group_name, group_df in grouped:
            t_closeness_values = {}
            for attribute in sensitive_attributes:
                series = group_df[attribute]
                t_closeness = compute_t_closeness(series, global_distributions[attribute])
                t_closeness_values[f't-closeness_{attribute}'] = t_closeness
            group_result = {
                'Quasi-identifiers': ', '.join(f"{qi}: {value}" for qi, value in zip(quasi_identifiers, group_name)),
                **t_closeness_values
            }
            results.append(group_result)
        results_df = pd.DataFrame(results)
        return results_df

    def calculate_global_distribution(series):
        class_distribution = series.value_counts(normalize=True)
        global_distribution = class_distribution.to_dict()
        return global_distribution

    def compute_t_closeness(series, global_distribution):
        class_distribution = series.value_counts(normalize=True)
        combined_index = list(global_distribution.keys())
        class_distribution = class_distribution.reindex(combined_index, fill_value=0)
        p_values = class_distribution.values
        q_values = np.array([global_distribution.get(k, 0) for k in combined_index])
        t_closeness = 0.5 * np.sum(np.abs(p_values - q_values))
        return t_closeness

    t_value = calculate_t_closeness(df, quasi_identifiers, sensitive_attributes)
    k_value = results_df[['Quasi-identifiers', 'k-anonymity']].copy()
    l_value_columns = ['Quasi-identifiers'] + [col for col in results_df.columns if col.startswith('Normalized Entropy l-diversity')]
    l_value = results_df[l_value_columns].copy()
    l_value.min()

    def calculate_P_29_score(k_value, l_value, t_value, w_k=0.5, w_l=0.25, w_t=0.25):
        reasons = []
        problematic_info = []
        k_min = k_value['k-anonymity'].min()
        if k_min == 1:
            reasons.append("k-anonymity is 1")
            problematic_rows = k_value[k_value['k-anonymity'] == 1]['Quasi-identifiers'].tolist()
            problematic_info.extend([(row, "k-anonymity is 1") for row in problematic_rows])
        if l_value.iloc[:, 1:].eq(0).any().any():
            reasons.append("normalized entropy l-value is 0 for some attribute")
            for col in l_value.columns[1:]:
                problematic_rows = l_value[l_value[col] == 0]['Quasi-identifiers'].tolist()
                problematic_info.extend([(row, f"normalized entropy l-value is 0 for {col}") for row in problematic_rows])
        if (t_value.iloc[:, 1:].astype(float) > 0.5).any().any():
            reasons.append("t-value exceeds 0.5 for some attribute")
            for col in t_value.columns[1:]:
                if t_value[col].dtype != 'object':
                    problematic_rows = t_value[t_value[col].astype(float) > 0.5]['Quasi-identifiers'].tolist()
                    problematic_info.extend([(row, f"t-value exceeds 0.5 for {col}") for row in problematic_rows])
        if k_min == 1 or l_value.iloc[:, 1:].eq(0).any().any() or (t_value.iloc[:, 1:].astype(float) > 0.5).any().any():
            return 0.0, problematic_info, reasons, k_min, l_value.iloc[:, 1:].min().min(), t_value.iloc[:, 1:].max().max()
        column_means = l_value.iloc[:, 1:].mean()
        normalized_l_value = column_means.mean()
        t_value_normalized = t_value.copy()
        for column in t_value.columns[1:]:
            min_val = t_value[column].min()
            max_val = t_value[column].max()
            t_value_normalized[column] = (t_value[column] - min_val) / (max_val - min_val)
        normalized_t_value = t_value_normalized.iloc[:, 1:].mean().mean()
        P_29_score = w_k * (1 - (1 / k_min)) + w_l * normalized_l_value + w_t * (1 - normalized_t_value)
        return P_29_score, problematic_info, reasons, k_min, l_value.iloc[:, 1:].min().min(), t_value.iloc[:, 1:].max().max()

    P_29_score, problematic_info, reasons, k_min, min_l_value, max_t_value = calculate_P_29_score(k_value, l_value, t_value)
    result = {
        "P_29 Score": P_29_score,
        "Problematic info": problematic_info,
        "Reasons": reasons,
        "Minimum k-anonymity": k_min,
        "Minimum normalized l-value": min_l_value,
        "Maximum t-value": max_t_value
    }

    return result




@app.route('/documentation')
def documentation():
    if 'user' in session:
        user_email = session['email']
        return render_template('documentation.html', user_email=user_email,current_path=request.path)
    else:
        return redirect('/')
    
if __name__ == '__main__':
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    app.run(debug=True)