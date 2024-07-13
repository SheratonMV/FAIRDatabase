import pandas as pd

# Load the CSV file into a pandas DataFrame
input_csv = 'uploads/df5.csv'  # Replace with your CSV file path
output_csv = 'df5-short.csv'  # Replace with desired output file path

df = pd.read_csv(input_csv)

# Determine number of columns in the DataFrame
num_columns = len(df.columns)
print(num_columns)

# Remove the last 15 columns
df_trimmed = df.iloc[:, :-35]

# Save the trimmed DataFrame back to a new CSV file
df_trimmed.to_csv(output_csv, index=False)

print(f"Trimmed CSV saved to '{output_csv}'")
