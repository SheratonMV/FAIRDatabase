import pandas as pd
import psycopg2
import time
import glob
import os
import sys
import re
from supabase import create_client, Client
from uploadfolder import demos
from supabase.lib.client_options import ClientOptions
import asyncio

def filter_characters(string):
    filtered_string = re.sub(r'[^a-zA-Z0-9_]', '_', string)
    return filtered_string

def filter_characters_list(stringlist):
    filtered_string = [re.sub(r'[^a-zA-Z0-9_]', '_', string) for string in stringlist]
    return filtered_string

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


SUPABASE_URL = demos.url
#KeyMSI
SUPABASE_PUBLIC_KEY = demos.service
clientOptions = ClientOptions(postgrest_client_timeout=999999)
# SUPABASE_PUBLIC_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.ewogICJyb2xlIjogInNlcnZpY2Vfcm9sZSIsCiAgImlzcyI6ICJzdXBhYmFzZSIsCiAgImlhdCI6IDE3MDE5OTAwMDAsCiAgImV4cCI6IDE4NTk4NDI4MDAKfQ.TtldGEFJ88vn790LrseKISJ9EdEv8GfTDsCsRN_b764'#'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6ImFub24iLCJleHAiOjE5ODM4MTI5OTZ9.CRXP1A7WOeoJeXxjNni43kdQwgnWNReilDMblYTn_I0'
supabase: Client = create_client(SUPABASE_URL, SUPABASE_PUBLIC_KEY, clientOptions)

database_connection = psycopg2.connect(host="localhost", port="5432", database="", user="postgres", password=demos.POSTpw)
sql_query = "alter role anon set statement_timeout = '3600s';"
cursor_database = database_connection.cursor()
try:
    cursor_database.execute(sql_query)
except:
    print("cant do")
try:
    sql_file = open('del_sql.sql', 'r')
    cursor_database.execute(sql_file.read())
    database_connection.commit()
except:
    print("cant delete all tables")
#advice to create a test schema
for testtrial in range(4,5):
    row_list=[]
    col_list=[]
    time_list =[]
    all_files= glob.glob('uploadfolder/*.csv')
    if not os.path.exists("outputs/timer"+str(testtrial)+".csv"):
        with open("outputs/timer"+str(testtrial)+".csv", 'w') as f:
            f.write("col,row,time\n")
            f.close()

    df_sav = pd.read_csv("outputs/timer"+str(testtrial)+".csv")
    prevlist = df_sav[['col','row']].values.tolist()
    # df_sav = pd.DataFrame({'col':[],'row':[],'time':[]})
    for filename in all_files:
        if '.csv' in filename and 'random' in filename:
            splits = filename.split("_")
            colc = int(splits[1])
            rowc = int(splits[-1].split('.')[0])
            upload_timer = time.time()
            if rowc!=0 and colc!=0 and [colc, rowc] not in prevlist:
                database_connection = psycopg2.connect(host="localhost", port=5432, database="",
                                                       user="postgres", password=demos.POSTpw)
                with open(filename, 'r') as uploaded_file_load:
                    file_loaded_lines = uploaded_file_load.readlines()
                    start = time.time()
                    time_c = time.gmtime()
                    time_c_text = (
                        f"_{time_c.tm_year}{time_c.tm_mon}{time_c.tm_mday}{time_c.tm_hour}{time_c.tm_min}{time_c.tm_sec}")

                    # Connect to database
                    database_connection = psycopg2.connect(host="localhost", port=5432, database="postgres",user="postgres",password=demos.POSTpw)
                    datain = pd.read_csv(filename)
                    allcolumnz = datain.columns
                    column_cutoff = 500
                    counttab = 0
                    for colfin in range(0, len(allcolumnz), column_cutoff):
                        counttab += 1

                        prename = filename.split('\\')[-1]
                        table_name = str(prename.rsplit('.', 1)[0] + time_c_text + '_' + str(counttab))
                        data = datain.iloc[:, colfin:colfin + column_cutoff]
                        columnz = data.columns
                        columns_filtered = [filter_characters(item) for item in columnz]
                        old_cols = data.columns
                        data = data.rename(columns=lambda x: f'"{filter_characters(x)}"')
                        cursor_database = database_connection.cursor()
                        # Table creation query
                        columns_text_c = ", ".join(
                            [f'{column} {pandas_to_postgres_type(data[data.columns[ei]].dtype)}' for ei, column in
                             enumerate(data.columns)])
                        data.columns = filter_characters_list(old_cols)
                        if counttab == 1:
                            sql_query = f"CREATE TABLE IF NOT EXISTS {table_name} (rowid SERIAL PRIMARY KEY, metadata TEXT, {columns_text_c});"
                            prev_table_name = table_name
                        else:
                            sql_query = f"CREATE TABLE IF NOT EXISTS {table_name} (rowid SERIAL PRIMARY KEY, metadata TEXT, {columns_text_c}, CONSTRAINT fk_rel FOREIGN KEY(rowid) REFERENCES {prev_table_name}(rowid));"


                        try:
                            cursor_database.execute(sql_query)
                            a = database_connection.commit()
                        except:
                            print("cant do")
                        result = 0
                        while result!=1:
                            try:
                                result = supabase.table(table_name).select(data.columns[-1]).execute()
                                result = 1
                            except:
                                time.sleep(0.05)

                        # total amount of rows minus the column row
                        data = data.replace('NaN', -1876)
                        data.fillna(-1876, inplace=True)
                        data['metadata'] = 'thes'
                        data['rowid'] = list(data.index)
                        data = data.to_dict(orient='records')
                        result=0
                        while result != 1:
                            try:
                                result = supabase.table(table_name).insert(data).execute()
                                result = 1
                                print("404 fixed, table inserted")
                            except:
                                time.sleep(1)
                        # if counttab!=1:
                        #     try:
                        #         sql_query = f"SELECT * FROM {prev_table_name} JOIN {table_name} ON {prev_table_name}.rowid = {table_name}.rowid;"
                        #     except:
                        #         print("cant link tables")
                        # else:
                        #     prev_table_name = table_name



                    end = time.time()
                    splits = filename.split("_")
                    # df_sav.loc[len(df_sav.index)] = [rowc, colc, end-start]

                    df_sav2 = pd.DataFrame([{'col':colc, 'row':rowc, 'time':end-start}])
                    df_sav = pd.concat([df_sav, df_sav2], ignore_index=True)
                    df_sav.reset_index()
                    print(rowc, colc, end-start)
                    df_sav.to_csv('outputs/timer'+str(testtrial)+'.csv', index=False)
                    try:
                        sql_file = open('del_sql.sql', 'r')
                        cursor_database.execute(sql_file.read())
                        database_connection.commit()
                    except:
                        print("cant delete all tables")
                    database_connection.commit()
                    database_connection.close()
