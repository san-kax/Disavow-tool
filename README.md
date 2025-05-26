# Disavow Link Generator (Streamlit App)

This app helps SEO professionals generate a Google disavow file by identifying spammy or toxic backlinks from Ahrefs, SEMrush, Majestic, and Bing Webmaster Tools.

## Features
- Upload backlink CSVs from major SEO tools
- Upload existing disavow file and custom suspicious anchor list
- Detect adult, pharma, SEO-spam links and custom patterns
- Export updated disavow file and detailed Excel report

## How to Use

1. Upload your backlink CSV files (you can select multiple).
2. Upload an existing disavow list (.txt) if available.
3. Upload a CSV with `anchor_text` column for suspicious terms.
4. Click **Generate Disavow List**.
5. Download the generated `disavow_list.txt` and `disavow_export.xlsx`.

## Deploy on Streamlit Cloud

1. Fork or clone this repo.
2. Log in to [Streamlit Cloud](https://streamlit.io/cloud).
3. Connect your GitHub and deploy the app from this repository.

## Requirements

See `requirements.txt`.

## License

MIT
