import pandas as pd
from typing import TypedDict
import os
import csv

class Appstate(TypedDict):
    summary: str


budget = pd.read_csv("major.csv", header=None, sep=r'\s+')
if budget.shape[1] == 1:
    value = budget.iloc[0, 0]
elif budget.shape[1] > 1:
    value = budget.iloc[0, 1]
else:
    raise ValueError("No data found in major.csv")

print(f" Major: {value}")


df = pd.read_csv("affordable_universities.csv")


df.columns = df.columns.str.strip()

df['university'] = (
    df['university']
    .astype(str)
    .str.replace(r'[$,]', '', regex=True)
    .astype(float)
)

df = df.dropna(subset=['value'])

filtered = df[df['value'] <= value]

print("\n Universities within budget:")
print(filtered)

output_file = "Fianl options.csv"
filtered[['university', 'label', 'value', 'location']].to_csv(output_file, index=False)

print(f"Saved {len(filtered)} university programs under budget to '{output_file}'")