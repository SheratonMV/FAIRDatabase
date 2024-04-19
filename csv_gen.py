import pandas as pd
import numpy as np
import random
import string
import secrets

char_string = string.ascii_letters + string.digits

def getRandomString(size):
    return ''.join(secrets.choice(char_string) for _ in range(size))
# Function to generate a DataFrame with random number of rows and columns
def generate_data(num_rows, num_cols):
    data = np.random.randint(0, 100, size=(num_rows, num_cols))
    df = pd.DataFrame(data)
    df.columns = [getRandomString(10) for i in range(num_cols)]
    return df

# Generate 5 CSV files
for num_rows in range(0, 5000, 500):
    for num_cols in range(0,20000, 1000):
        df = generate_data(num_rows, num_cols)
        df.to_csv('uploadfolder/randomdata_'+str(num_rows)+'_'+str(num_cols)+'.csv', index=False)
