import os
from supabase import create_client, Client
from flask import Flask, session, request, render_template, redirect, url_for, make_response
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
import asyncio


def bracket_and_comma_remove(loclist):
    loclist = [j.replace('\'', '')  for i in loclist for j in i ]
    return loclist
app = Flask(__name__)
app.secret_key = os.urandom(1)

def pandas_to_postgres_type(dtype):
    if pd.api.types.is_integer_dtype(dtype):
        return 'INTEGER'
    elif pd.api.types.is_float_dtype(dtype):
        return 'REAL'
    elif pd.api.types.is_bool_dtype(dtype):
        return 'BOOLEAN'
    elif pd.api.types.is_datetime64_any_dtype(dtype):
        return 'TIMESTAMP'
    else:
        return 'TEXT'

def filter_characters(string):
    filtered_string = re.sub(r'[^a-zA-Z0-9_]', '_', string)
    return filtered_string

def filter_characters_list(stringlist):
    filtered_string = [re.sub(r'[^a-zA-Z0-9_]', '_', string) for string in stringlist]
    return filtered_string
SUPABASE_URL = 'http://localhost:8000'
#KeyMSI
SUPABASE_PUBLIC_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.ewogICAgInJvbGUiOiAic2VydmljZV9yb2xlIiwKICAgICJpc3MiOiAic3VwYWJhc2UiLAogICAgImlhdCI6IDE2ODc5ODk2MDAsCiAgICAiZXhwIjogMTg0NTg0MjQwMAp9.KP_2X3ZplcvahzTvAb0NlAIkhzmVs-hO3FHIrt7mRO8'
#KeyZ
# SUPABASE_PUBLIC_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.ewogICJyb2xlIjogInNlcnZpY2Vfcm9sZSIsCiAgImlzcyI6ICJzdXBhYmFzZSIsCiAgImlhdCI6IDE3MDE5OTAwMDAsCiAgImV4cCI6IDE4NTk4NDI4MDAKfQ.TtldGEFJ88vn790LrseKISJ9EdEv8GfTDsCsRN_b764'#'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6ImFub24iLCJleHAiOjE5ODM4MTI5OTZ9.CRXP1A7WOeoJeXxjNni43kdQwgnWNReilDMblYTn_I0'
supabase: Client = create_client(SUPABASE_URL, SUPABASE_PUBLIC_KEY)
database_connection = psycopg2.connect(host="localhost", port="5432", database="", user="postgres", password="4ssEP7M09t7g1PM5Y6U3")#"GciOiJIUzI1NiIsInR5cCI6IkpXVCJ9")

sql_query = 'SELECT table_name FROM information_schema.tables WHERE table_schema=\'public\''
cursor_database = database_connection.cursor()
cursor_database.execute(sql_query)
table_names = bracket_and_comma_remove(cursor_database.fetchall())
a =1

@app.route('/')
def home():
    values = ['1','2','3']
    return render_template('list_display.html', values=table_names)

@app.route('/display_sample_table/<name>')
def display_sample_table(name):
    response = supabase.table(name).select("*").range(0, 9).execute()
    rows = response.data
    return render_template('display_sample_table.html', name=name, rows=rows)


@app.route('/edit_table/<name>')
def edit_table(name):
    # Fetch data from the table
    fetch_response = supabase.table(name).select("*").range(0,1).execute()
    data = fetch_response.data

    # Get column headers
    if data:
        column_headers = data[0].keys()
    return render_template('edit_table.html', column_headers=column_headers, data=data)


@app.route('/update_a_row', methods=['POST'])
def update_a_row():
    name = request.form.get('my_input')
    fetch_response = supabase.table(name).select("*").range(0,1).execute()
    data = fetch_response.data

    # Get column headers
    if data:
        column_headers = data[0].keys()
    # Get form data (replace 'column1' and 'column2' with your actual column names)
    colvals = [supabase.table(name).update({colv: request.form.get(colv)}) for colv in column_headers]


    # Update row in the table (replace 'your_table' with your actual table name)
    # update_response = supabase.table('your_table').update({"column1": column1, "column2": column2})

    # Redirect to the edit page (or wherever you want to go after updating)
    return redirect(url_for('edit'))


@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if request.method == 'POST':

        uploaded_file = request.files['file']

        if uploaded_file.filename == '':
            return render_template('upload.html', error_message='No file selected.')
        elif not uploaded_file and uploaded_file.filename.endswith('.csv'):
            return render_template('upload.html', error_message='Invalid file format. Please upload a .txt file.')

        elif uploaded_file and uploaded_file.filename.endswith('.csv'):
            upload_timer = time.time()

            uploaded_file.save('uploadfolder/' + secure_filename(uploaded_file.filename))

            with open('uploadfolder/' + secure_filename(uploaded_file.filename), 'r') as uploaded_file_load:
                file_loaded_lines = uploaded_file_load.readlines()

                # Get input from user
                description = request.form['description']
                origin = request.form['origin']

                # Table name creation based on time uploaded
                # cur.execute("""
                #     ALTER TABLE table1
                #     ADD FOREIGN KEY (column1)
                #     REFERENCES table2 (column1)
                # """)
                #
                # conn.commit()

                time_c = time.gmtime()
                time_c_text = (
                    f"_{time_c.tm_year}{time_c.tm_mon}{time_c.tm_mday}{time_c.tm_hour}{time_c.tm_min}{time_c.tm_sec}")


                # Connect to database
                database_connection = psycopg2.connect(host="localhost", port=5432, database="",
                                                       user="postgres", password='4ssEP7M09t7g1PM5Y6U3')#"GciOiJIUzI1NiIsInR5cCI6IkpXVCJ9")#



                datain = pd.read_csv('uploadfolder/' + secure_filename(uploaded_file.filename))
                allcolumnz = datain.columns
                column_cutoff = 500
                counttab = 0
                for colfin in range(0, len(allcolumnz), column_cutoff):
                    counttab +=1
                    table_name = str(secure_filename(uploaded_file.filename)).rsplit('.', 1)[0] + time_c_text + '_' + str(counttab)
                    data = datain.iloc[:, colfin:colfin+column_cutoff]
                    columnz = data.columns
                    columns_filtered = [filter_characters(item) for item in columnz]
                    old_cols = data.columns
                    data = data.rename(columns=lambda x: f'"{filter_characters(x)}"')
                    cursor_database = database_connection.cursor()
                    # Table creation query
                    columns_text_c = ", ".join(
                        [f'{column} {pandas_to_postgres_type(data[data.columns[ei]].dtype)}' for ei, column in enumerate(data.columns)])
                    data.columns=filter_characters_list(old_cols)
                    sql_query = f"CREATE TABLE {table_name} (rowid SERIAL PRIMARY KEY, metadata TEXT, {columns_text_c});"
                    try:
                        cursor_database.execute(sql_query)
                    except:
                        print ("cant do")
                    database_connection.commit()

                    # total amount of rows minus the column row
                    data = data.replace('NaN', -1876)
                    data.fillna(-1876, inplace=True)
                    data['metadata'] = 'thes'
                    data['rowid'] = list(data.index)
                    data = data.to_dict(orient='records')
                    result =supabase.table(table_name).insert(data).execute()
                    print(colfin, colfin + column_cutoff, "done")
                database_connection.commit()
                database_connection.close()

            # Remove file locally
            os.remove('uploadfolder/' + uploaded_file.filename)

            # Clear progress from session
            session.pop('progress', None)

            # Display time
            upload_timer = str(round(time.time() - upload_timer, 2))
            print(
                f"--- {upload_timer.replace('.', ',')[:5]} seconds,  rows, {len(allcolumnz)} columns---")

            return "File uploaded successfully."
    else:
        return render_template('upload.html')



if __name__ == '__main__':
    app.run(debug=True)