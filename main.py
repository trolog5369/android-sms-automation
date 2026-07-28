import pandas as pd

# Read Excel
df = pd.read_excel("Ghodnadi Bar Clean.xlsx")

# Read message
with open("message.txt", "r", encoding="utf-8") as file:
    message = file.read()

print("=" * 60)
print("MESSAGE:")
print(message)
print("=" * 60)

print(f"\nTotal Contacts: {len(df)}\n")

print(df.head(10))