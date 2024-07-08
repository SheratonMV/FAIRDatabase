import pandas as pd
import numpy as np
from collections import defaultdict


# Read the CSV file into a DataFrame
df = pd.read_csv('df8.csv')


# Quasi-identifiers and sensitive attributes
quasi_identifiers = ['race', 'gender', 'age']
sensitive_attributes = ['diag_1', 'diag_2', 'diag_3', 'max_glu_serum', 'A1Cresult', 'readmitted']

# Function to calculate k-anonymity
def calculate_k_anonymity(group):
    return len(group)

# Function to calculate normalized entropy l-diversity for a column
def calculate_normalized_entropy(series):
    # Handle empty series
    if series.empty:
        return 0

    value_counts = series.value_counts(normalize=True)
    total_entropy = 0
    
    for count in value_counts:
        if count > 0:
            total_entropy -= count * np.log2(count)
    
    # Normalize the entropy by the log2 of the number of unique values
    unique_values = series.nunique()
    
    if unique_values == 1:
        return 0
    
    normalized_entropy = total_entropy / np.log2(unique_values)
    return normalized_entropy

# Initialize results dictionary
results = defaultdict(list)

# Group by quasi-identifiers and calculate metrics
grouped = df.groupby(quasi_identifiers)
for name, group in grouped:
    # Calculate k-anonymity
    k_anonymity = calculate_k_anonymity(group)
    
    # Calculate normalized entropy l-diversity for each sensitive attribute
    for attribute in sensitive_attributes:
        normalized_entropy = calculate_normalized_entropy(group[attribute])
        results[f'Normalized Entropy l-diversity_{attribute}'].append(normalized_entropy)
        
    # Append k value and quasi-identifiers combination for this group
    quasi_identifier_values = ', '.join(f"{qi}: {group[qi].iloc[0]}" for qi in quasi_identifiers)
    results['Quasi-identifiers'].append(quasi_identifier_values)
    results['k-anonymity'].append(k_anonymity)

# Convert results to DataFrame for easier viewing
results_df = pd.DataFrame(results)

# Function to calculate t-closeness
def calculate_t_closeness(df, quasi_identifiers, sensitive_attributes):
    """
    Calculate t-closeness for sensitive attributes in a DataFrame grouped by quasi-identifiers using variational distance.
    
    Parameters:
    - df: DataFrame containing quasi-identifiers and sensitive attribute columns.
    - quasi_identifiers: List of column names (quasi-identifiers) in df.
    - sensitive_attributes: List of column names (sensitive attributes) in df.
    
    Returns:
    - DataFrame with t-closeness values for each group of quasi-identifiers and sensitive attributes.
    """
    results = []
    
    # Group by quasi-identifiers and calculate t-closeness for each group
    grouped = df.groupby(quasi_identifiers)
    
    # Calculate global distribution Q for each sensitive attribute
    global_distributions = {}
    for attribute in sensitive_attributes:
        global_distributions[attribute] = calculate_global_distribution(df[attribute])
    
    for group_name, group_df in grouped:
        # Calculate t-closeness for each sensitive attribute in the group
        t_closeness_values = {}
        
        for attribute in sensitive_attributes:
            series = group_df[attribute]
            t_closeness = compute_t_closeness(series, global_distributions[attribute])
            t_closeness_values[f't-closeness_{attribute}'] = t_closeness
        
        # Store the results for this group
        group_result = {
            'Quasi-identifiers': ', '.join(f"{qi}: {value}" for qi, value in zip(quasi_identifiers, group_name)),
            **t_closeness_values
        }
        results.append(group_result)
    
    # Create a DataFrame from results and return
    results_df = pd.DataFrame(results)
    return results_df

def calculate_global_distribution(series):
    """
    Calculate the global distribution Q for a single categorical attribute series.
    
    Parameters:
    - series: Pandas Series representing the attribute values.
    
    Returns:
    - Dictionary representing the global distribution Q.
      Keys are attribute values (categories), values are probabilities.
    """
    class_distribution = series.value_counts(normalize=True)
    global_distribution = class_distribution.to_dict()
    return global_distribution

def compute_t_closeness(series, global_distribution):
    """
    Compute t-closeness using the variational distance for a single categorical attribute series.
    
    Parameters:
    - series: Pandas Series representing the attribute values.
    - global_distribution: Dictionary representing the global distribution Q for the specific attribute.
                           Keys are attribute values (categories), values are probabilities.
    
    Returns:
    - t_closeness: Float, t-closeness value for the series with respect to global_distribution.
    """
    class_distribution = series.value_counts(normalize=True)
    combined_index = list(global_distribution.keys())
    class_distribution = class_distribution.reindex(combined_index, fill_value=0)
    
    p_values = class_distribution.values
    q_values = np.array([global_distribution.get(k, 0) for k in combined_index])
    
    t_closeness = 0.5 * np.sum(np.abs(p_values - q_values))
    return t_closeness

# Example usage:
# List of quasi-identifiers and sensitive attribute names
quasi_identifiers = ['race', 'gender', 'age']
sensitive_attributes = ['diag_1', 'diag_2', 'diag_3', 'max_glu_serum', 'A1Cresult', 'readmitted']

# Calculate t-closeness for each group of quasi-identifiers
t_value = calculate_t_closeness(df, quasi_identifiers, sensitive_attributes)

# Extract columns containing 'k-anonyminity'
k_value = results_df[['Quasi-identifiers', 'k-anonymity']].copy()

# Extract columns containing 'Normalized Entropy l-diversity'
l_value_columns = ['Quasi-identifiers'] + [col for col in results_df.columns if col.startswith('Normalized Entropy l-diversity')]
l_value = results_df[l_value_columns].copy()
l_value.min()

#calculate P_29 Score

def calculate_P_29_score(k_value, l_value, t_value, w_k=0.5, w_l=0.25, w_t=0.25):
    reasons = []
    problematic_info = []
    
    # Step 1: Calculate the minimum k-anonymity value
    k_min = k_value['k-anonymity'].min()
    
    # Step 2: Check conditions to set joint privacy score to 0
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
            if t_value[col].dtype != 'object':  # Skip columns with non-numeric values
                problematic_rows = t_value[t_value[col].astype(float) > 0.5]['Quasi-identifiers'].tolist()
                problematic_info.extend([(row, f"t-value exceeds 0.5 for {col}") for row in problematic_rows])
    
    if k_min == 1 or l_value.iloc[:, 1:].eq(0).any().any() or (t_value.iloc[:, 1:].astype(float) > 0.5).any().any():
        return 0.0, problematic_info, reasons, k_min, l_value.iloc[:, 1:].min().min(), t_value.iloc[:, 1:].max().max()
    
    # Step 3: Compute the mean normalized entropy l value for each sensitive attribute across all equivalence classes
    column_means = l_value.iloc[:, 1:].mean()
    normalized_l_value = column_means.mean()
    
    # Step 4: Normalize the t values across columns
    t_value_normalized = t_value.copy()
    for column in t_value.columns[1:]:
        min_val = t_value[column].min()
        max_val = t_value[column].max()
        t_value_normalized[column] = (t_value[column] - min_val) / (max_val - min_val)
    
    # Step 5: Compute the overall normalized t value for the dataset
    normalized_t_value = t_value_normalized.iloc[:, 1:].mean().mean()
    
    # Step 6: Calculate P_29
    P_29_score = w_k * (1 - (1 / k_min)) + w_l * normalized_l_value + w_t * (1 - normalized_t_value)
    
    return P_29_score, problematic_info, reasons, k_min, l_value.iloc[:, 1:].min().min(), t_value.iloc[:, 1:].max().max()


# Sample call to calculate P_29 score
P_29_score, problematic_info, reasons, k_min, min_l_value, max_t_value = calculate_P_29_score(k_value, l_value, t_value)

print("P_29 Score:", P_29_score)
print("Reasons:", reasons)
print("Problematic Information:")
for info in problematic_info:
    print(f"Problem in {info[0]} due to {info[1]}")
print("Minimum k-anonymity:", k_min)
print("Minimum normalized l-value:", min_l_value)
print("Maximum t-value:", max_t_value)

def main():
    result = {"P_29 Score:":P_29_score, 
              "Reasons: ":reasons, 
              "Minimum k-anonymity":k_min,
              "Minimum normalized l-value:":min_l_value,
              "Maximum t-value:":max_t_value}
    return result