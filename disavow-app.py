import streamlit as st
import pandas as pd
import re
from urllib.parse import urlparse
import io

# === PAGE SETUP ===
st.set_page_config(page_title="Disavow Combiner", layout="wide")
st.title("🔗 Disavow Tool")

# === SIDEBAR ===
st.sidebar.header("Upload Required Files")
backlink_files = st.sidebar.file_uploader("Upload backlink CSV files", type="csv", accept_multiple_files=True)
disavow_file = st.sidebar.file_uploader("Upload existing disavow.txt (optional)", type="txt")

# Google Sheet for suspicious anchor list
SHEET_LINK = "https://docs.google.com/spreadsheets/d/1S_fkjSaCQLv5xLMcdqC-Xh2gKn1WazeNs1J14aukx84/edit#gid=147585760"
CSV_EXPORT_URL = "https://docs.google.com/spreadsheets/d/1S_fkjSaCQLv5xLMcdqC-Xh2gKn1WazeNs1J14aukx84/export?format=csv&gid=147585760"
st.sidebar.markdown(f"🛠️ [Edit Suspicious Anchor List]({SHEET_LINK})")

# === FUNCTIONS ===
def fuzzy_match(col_map, keyword):
    keyword = keyword.replace(" ", "").lower()
    for key in col_map:
        if keyword in key.replace(" ", "").lower():
            return col_map[key]
    return None

def normalize_backlink_df(df):
    col_map = {col.lower().strip(): col for col in df.columns}
    ref_url_col = fuzzy_match(col_map, "source url") or fuzzy_match(col_map, "referring page url") or fuzzy_match(col_map, "referring url")
    anchor_col = fuzzy_match(col_map, "anchor") or fuzzy_match(col_map, "anchor text")
    if ref_url_col and anchor_col:
        return df.rename(columns={
            ref_url_col: "referring_page_url",
            anchor_col: "anchor"
        }).assign(**{"left context": "", "right context": ""})
    raise ValueError("Unrecognized format: required backlink columns not found.")

# === BUTTON LOGIC ===
if st.button("🚀 Generate Disavow List"):
    if not backlink_files:
        st.warning("Please upload at least one backlink CSV file.")
    else:
        try:
            # Load suspicious anchor terms from Google Sheet
            suspicious_df = pd.read_csv(CSV_EXPORT_URL)
            suspicious_anchors = set(suspicious_df['anchor_text'].dropna().str.strip().str.lower())

            # Load existing disavow list (if provided)
            if disavow_file:
                disavow_lines = disavow_file.read().decode("utf-8", errors="ignore").splitlines()
                existing_domains = {
                    str(line).strip().replace("domain:", "").lower().replace("www.", "")
                    for line in disavow_lines if str(line).strip().startswith("domain:")
                }
            else:
                existing_domains = set()

            # Normalize all uploaded backlink files
            all_dfs = []
            for file in backlink_files:
                try:
                    df = pd.read_csv(file, encoding="ISO-8859-1", engine="python")
                    if df.empty or len(df.columns) == 0:
                        raise ValueError("Empty or malformed CSV.")
                    norm = normalize_backlink_df(df)
                    all_dfs.append(norm)
                except Exception as e:
                    st.warning(f"⚠️ Skipped {file.name}: {e}")

            df = pd.concat(all_dfs, ignore_index=True)
            df['referring_domain'] = df['referring_page_url'].apply(lambda x: urlparse(str(x)).netloc.lower().replace("www.", ""))
            df["full_context"] = df[["left context", "anchor", "right context"]].astype(str).agg(' '.join, axis=1)
            df["anchor_lower"] = df["anchor"].astype(str).str.strip().str.lower()

            # Define keyword filters
            spam_rules = {
                'adult': re.compile(r'\b(?:' + '|'.join(["porn", "sex", "camgirl", "escort", "xxx", "anal", "nude"]) + r')\b', re.I),
                'pharma': re.compile(r'\b(?:' + '|'.join(["penis", "erectile", "enlargement", "enhancement"]) + r')\b', re.I),
                'seo': re.compile('|'.join(["buy backlinks", "seo tool", "cheap backlinks", "rank booster", "pbn"]), re.I)
            }

            matched = df[
                df['full_context'].str.contains(spam_rules['adult']) |
                df['anchor_lower'].str.contains(spam_rules['pharma']) |
                df['anchor_lower'].str.contains(spam_rules['seo']) |
                df['anchor_lower'].apply(lambda x: any(p in x for p in suspicious_anchors))
            ]

            matched = matched[~matched['referring_domain'].isin(existing_domains)]
            final_domains = sorted(set(matched['referring_domain']))

            # === OUTPUT ===
            st.success(f"🎯 {len(final_domains)} new spammy domains detected.")

            # Save disavow_list.txt to session
            disavow_txt = '\n'.join(["domain:" + d for d in final_domains])
            st.session_state["disavow_txt"] = disavow_txt

            # Save Excel file to session
            excel_output = io.BytesIO()
            with pd.ExcelWriter(excel_output, engine='xlsxwriter') as writer:
                pd.DataFrame(final_domains, columns=["Referring Domain"]).to_excel(writer, sheet_name="Disavow Domains", index=False)
                matched.to_excel(writer, sheet_name="Disavow Details", index=False)
            excel_output.seek(0)
            st.session_state["disavow_xlsx"] = excel_output.read()

        except Exception as e:
            st.error(f"❌ Something went wrong: {e}")

# === SHOW DOWNLOADS IF AVAILABLE ===
if "disavow_txt" in st.session_state and "disavow_xlsx" in st.session_state:
    st.download_button(
        "⬇️ Download disavow_list.txt",
        st.session_state["disavow_txt"],
        file_name="disavow_list.txt",
        key="download_txt_button"
    )
    st.download_button(
        "⬇️ Download disavow_export.xlsx",
        st.session_state["disavow_xlsx"],
        file_name="disavow_export.xlsx",
        key="download_xlsx_button"
    )
