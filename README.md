# ElectionSMS

A Python-based SMS automation tool designed for election campaign communication. It reads contact data from Excel spreadsheets and sends personalized messages to voters.

## Features

- 📊 Load and parse voter contact lists from Excel files (`.xlsx`)
- 📝 Customizable message templates with multilingual support (Marathi / Hindi / English)
- 📱 Bulk SMS dispatch to voter contact lists
- 📋 Contact list preview and validation

## Requirements

- Python 3.8 or higher
- pandas
- openpyxl

## Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/trolog5369/android-sms-automation.git
   cd ElectionSMS
   ```

2. **Create a virtual environment (recommended):**
   ```bash
   python -m venv .venv
   .venv\Scripts\activate   # Windows
   # source .venv/bin/activate  # macOS / Linux
   ```

3. **Install dependencies:**
   ```bash
   pip install pandas openpyxl
   ```

## Usage

1. Place your contact list Excel file in the project root.
2. Edit `message.txt` with your desired message content.
3. Run the script:
   ```bash
   python main.py
   ```

## Project Structure

```
ElectionSMS/
├── main.py                    # Entry point
├── message.txt                # Message template
├── Ghodnadi Bar Clean.xlsx    # Contact list (Excel)
├── .gitignore
└── README.md
```

## License

This project is for personal / campaign use.
