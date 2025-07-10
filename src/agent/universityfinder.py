import pandas as pd
from typing import TypedDict
import os
import csv

class Appstate(TypedDict):
    summary: str


budget = pd.read_csv("budget.csv", header=None, sep=r'\s+')
if budget.shape[1] == 1:
    value = budget.iloc[0, 0]
elif budget.shape[1] > 1:
    value = budget.iloc[0, 1]
else:
    raise ValueError("No data found in budget.csv")

print(f" Budget value: {value}")


df = pd.read_csv("latest_expenses.csv")


df.columns = df.columns.str.strip()

df['value'] = (
    df['value']
    .astype(str)
    .str.replace(r'[$,]', '', regex=True)
    .astype(float)
)

df = df.dropna(subset=['value'])

filtered = df[df['value'] <= value]

print("\n Universities within budget:")
print(filtered)

output_file = "affordable_universities.csv"
filtered[['university', 'label', 'value', 'year']].to_csv(output_file, index=False)

print(f"Saved {len(filtered)} university programs under budget to '{output_file}'")
