import pandas as pd
import matplotlib

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

df_sav = pd.read_csv("outputs/timer.csv")
rows = df_sav['col'].to_numpy(dtype=int)
cols = df_sav['row'].to_numpy(dtype=int)
time = df_sav['time'].to_numpy(dtype=int)
plt.rcParams['svg.fonttype'] = 'none'


inds = np.where(cols<17000)
rows = rows[inds]
cols = cols[inds]
time = time[inds]

# Assuming series1, series2, and series3 are your data
#Series1
# uniqrows = np.unique(rows)
# plt.figure(figsize=(10,6))
# for unir in uniqrows:
#     lab = str(unir)
#     inds = np.where(rows==unir)
#     x = cols[inds]
#     y = time[inds]
#     plt.plot(x, y, label=lab)

#Series2
uniqcols = np.unique(cols)
plt.figure(figsize=(10,6))
for unir in uniqcols:
    lab = str(unir)
    inds = np.where(cols==unir)
    x = rows[inds]
    y = time[inds]
    plt.plot(x, y, label=lab)



# Adding title and labels
plt.xlabel('Number of rows')
plt.ylabel('Time elapsed (s)')

# Adding legend
plt.legend()

# Show the plot
plt.savefig("outputs/rowsvstime.svg")
