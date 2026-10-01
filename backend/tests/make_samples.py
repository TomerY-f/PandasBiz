"""Generates sample files mimicking real Israeli bank/card exports, for e2e testing."""
import os

OUT = os.path.join(os.path.dirname(__file__), "samples")
os.makedirs(OUT, exist_ok=True)

# Credit card export (windows-1255, junk rows before header — like Isracard/Max exports)
credit_csv = """פירוט עסקאות לחיוב
כרטיס: 1234
,,,
תאריך עסקה,שם בית עסק,סכום חיוב,ענף,סוג עסקה
15/08/2026,שופרסל דיל חיפה,245.50,מזון,רגילה
17/08/2026,פז חיפה,180.00,דלק,רגילה
02/09/2026,סופר פארם,89.90,פארם,רגילה
11/09/2026,ארומה,32.00,מסעדות,רגילה
"""
with open(os.path.join(OUT, "credit_sample.csv"), "w", encoding="windows-1255") as f:
    f.write(credit_csv)

# Bank export (windows-1255)
bank_csv = """תנועות בחשבון
,,,
תאריך,תיאור פעולה,חובה,זכות,יתרה
01/08/2026,משכורת,,18000.00,25000.00
03/08/2026,העברת שכ"ד משוכר,,4200.00,29200.00
10/08/2026,חיוב כרטיס אשראי,7500.00,,21700.00
15/08/2026,ועד בית - דירה מושכרת,450.00,,21250.00
01/09/2026,משכורת,,18000.00,39250.00
03/09/2026,העברת שכ"ד משוכר,,4200.00,43450.00
"""
with open(os.path.join(OUT, "bank_sample.csv"), "w", encoding="windows-1255") as f:
    f.write(bank_csv)

# E-Trade positions export (UTF-8, English)
etrade_csv = """Account Summary
Positions as of 09/15/2026
Symbol,Quantity,Price Paid $,Last Price $,Description
AAPL,10,150.00,230.00,APPLE INC
VOO,5,380.00,540.00,VANGUARD S&P 500 ETF
"""
with open(os.path.join(OUT, "etrade_sample.csv"), "w", encoding="utf-8") as f:
    f.write(etrade_csv)

print("samples written to", OUT)
