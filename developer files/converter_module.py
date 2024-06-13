import sys, os
input = "data/sample.fasta"
output_dir = 'data'
def internal_check(input, output):
    a =1

def fasta_convert(input,output):
    """
    adapted from https://github.com/drewk2021/fastatocsv
    Purpose: To convert a .fasta file of >= 1 sequence(s) into a .csv file, with
    two columns, one containing the headline identifier, the other containing the
    sequence.
    Parameters: the input .fasta file path, a string, and the desired .csv output
    path, another string.
    Return: the output path, a string.
    """
    if not os.path.exists(input):
        raise IOError(errno.ENOENT, 'No such file', input)

    # Read in Fasta
    fasta = open(input, 'r')
    fasta_lines = fasta.readlines()
    seq = {}
    seqs = []

    for line in fasta_lines:

        if line[0] == ">": # head line with description
            seqs += [seq] # adding dicitionary to broader list
            seq_local = {}
            seq_head = line.strip(">\n")
            seq_local["seq_type"] = seq_head # identifier
            seq_local["seq"] = "" # actual sequence
            seq = seq_local


        else: # sequence line
            seq["seq"] += line.strip("\n")


    fasta.close()

    # Convert fasta to csv
    seqs.pop(0) # removing first (empty) item in seqs list i.e. fencepost
    csv_lines = ["Properties, Sequence\n"]
    for seq in seqs:
        csv_line = seq["seq_type"] + "," + seq["seq"] + "\n"
        csv_lines += csv_line


    # Output csv file
    csv = open(output, 'w')
    csv.writelines(csv_lines)
    csv.close()
    return output




def convertWithAttributes(input,output):
    if not os.path.exists(input):
        raise IOError(errno.ENOENT, 'No such file', input)

    # Read in Fasta
    fasta = open(input, 'r')
    fasta_lines = fasta.readlines()
    seq = {}
    seqs = []

    for line in fasta_lines:

        if line[0] == ">": # head line with description
            seqs += [seq] # adding dicitionary to broader list
            seq_local = {}
            seq_head = line.strip(">\n").split("|") # seperating the head's attributes
            seq_local["seq_type_list"] = seq_head # identifier
            seq_local["seq"] = "" # actual sequence
            seq = seq_local


        else: # sequence line
            seq["seq"] += line.strip("\n")


    fasta.close()

    # Convert fasta to csv
    seqs.pop(0) # removing first (empty) item in seqs list i.e. fencepost
    csv_lines = []
    for seq in seqs:
        csv_line = ""
        for type in seq["seq_type_list"]:
            csv_line += (type + ",")

        csv_lines += (csv_line + "\n")


    # Output csv file
    csv = open(output, 'w')
    csv.writelines(csv_lines)
    csv.close()
    return output
# convert(input, "data/output.csv")


import sys
import skbio
import pandas as pd

def convert_motu(input_file, output_dir):
    # Read motu.table file using scikit-bio
    table = skbio.io.read(input_file, format='fasta')
    # Select metadata lines (starting with '#') and convert them to a DataFrame
    metadata = pd.DataFrame()
    for line in table.iloc[0].index[::-1][:10]:  # Assuming the first ten lines are metadata
        if line.startswith('#'):
            metadata = metadata.append(pd.Series(str(table.iloc[0, line]).split('\t')[1:], index=line[1:]), ignore_index=True)

    # Drop the first row with indices as it only contains metadata
    table = table.iloc[1:]

    # Write CSV file for the table data
    table.to_csv(output_dir+'/'+os.path.basename("/path/to/file.txt")+'.csv', index=False, header=False)

    # Write TEXT file for the metadata
    metadata.to_markdown(output_dir+'/'+os.path.basename("/path/to/file.txt")+'meta.txt')


convert_motu(input, output_dir)