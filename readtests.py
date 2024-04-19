import numpy as np
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


SUPABASE_URL = demos.url
SUPABASE_PUBLIC_KEY = demos.service
clientOptions = ClientOptions(postgrest_client_timeout=999999)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_PUBLIC_KEY, clientOptions)
database_connection = psycopg2.connect(host="localhost", port="5432", database="", user="postgres", password=demos.POSTpw)
cursor_database = database_connection.cursor()

# SELECT *
# FROM randomdata_500_1000_20242513298_1
# JOIN randomdata_500_1000_20242513298_2 ON randomdata_500_1000_20242513298_1.rowid = randomdata_500_1000_20242513298_2.rowid;
start = time.time()
# cur.execute("SELECT table1.*, table2.*, table3.*, table4.*, table5.*, table6.*, table7.*, table8.*, table9.*, table10.* FROM table1 INNER JOIN table2 ON table1.table_id = table2.id INNER JOIN table3 ON table2.table_id = table3.id INNER JOIN table4 ON table3.table_id = table4.id INNER JOIN table5 ON table4.table_id = table5.id INNER JOIN table6 ON table5.table_id = table6.id INNER JOIN table7 ON table6.table_id = table7.id INNER JOIN table8 ON table7.table_id = table8.id INNER JOIN table9 ON table8.table_id = table9.id INNER JOIN table10 ON table9.table_id = table10.id")
sql_query = "SELECT tablename FROM pg_tables WHERE schemaname = current_schema()"
cursor_database.execute(sql_query)
database_connection.commit()
tablenames = cursor_database.fetchall()
# res = supabase.table(tablenames[0][0]).select('*, '+tablenames[1][0]+'(*)').eq('rowid', 1).execute()
# if len(res.data[0])>0:
#     print("retrival is success")
#     end = time.time()
for col in range(500, 4500, 500):
    for row in range(1000,17000,1000):
        tabnames = []
        counts = []
        for tname in tablenames:
            if col == int(tname[0].split('_')[1]) and row == int(tname[0].split('_')[2]):

                if int(tname[0].split('_')[-1]) ==1:
                    header = tname[0]
                else:
                    counts.append(int(tname[0].split('_')[-1]))
        counts = np.asarray(counts)
        counts= np.sort(counts)
        tabnames = [header[:-1]+str(i) for i  in counts ]
        query = supabase.table(header).select("*")
        res = supabase.table(header).select("*").eq("rowid", 1).execute()

        if len(res.data[0])>0:
            print("retrival is success")
            end = time.time()

a=1