
import streamlit as st
import pandas as pd
import re
from urllib.parse import urlparse
import io

st.set_page_config(page_title="Disavow Generator", layout="wide")
st.title("🔍 Disavow Link Generator")

# --- File Uploads ---
st.sidebar.header("Upload Files")
backlink_files = st.sidebar.file_uploader("Upload backlink CSVs (Ahrefs, SEMrush, Majestic, Bing)", type="csv", accept_multiple_files=True)
disavow_file = st.sidebar.file_uploader("Upload existing disavow .txt file", type="txt")
anchor_file = st.sidebar.file_uploader("Upload suspicious anchor list (.csv)", type="csv")

# --- Helper Functions ---
def normalize_backlink_df(df):
    col_map = {col.lower().strip(): col for col in df.columns}
    if {"referring page url", "anchor"} <= set(col_map):
        return df.rename(columns={
            col_map["referring page url"]: "referring_page_url",
            col_map["anchor"]: "anchor"
        }).assign(**{"left context": "", "right context": ""})
    elif {"source url", "anchor"} <= set(col_map):
        return df.rename(columns={
            col_map["source url"]: "referring_page_url",
            col_map["anchor"]: "anchor"
        }).assign(**{"left context": "", "right context": ""})
    elif {"source url", "anchor text"} <= set(col_map):
        return df.rename(columns={
            col_map["source url"]: "referring_page_url",
            col_map["anchor text"]: "anchor"
        }).assign(**{"left context": "", "right context": ""})
    elif {'﻿"source url"', "anchor text"} <= set(col_map):
        return df.rename(columns={
            col_map['﻿"source url"']: "referring_page_url",
            col_map["anchor text"]: "anchor"
        }).assign(**{"left context": "", "right context": ""})
    else:
        raise ValueError("Unrecognized format")

# --- Main Processing ---
if st.button("🔎 Generate Disavow List"):
    if not backlink_files or not disavow_file or not anchor_file:
        st.warning("Please upload all required files.")
    else:
        suspicious_anchors = set(pd.read_csv(anchor_file)['anchor_text'].dropna().str.strip().str.lower())

        existing_domains = {
            line.strip().replace("domain:", "").lower().replace("www.", "")
            for line in disavow_file if line.strip().startswith("domain:")
        }

        all_dfs = []
        for file in backlink_files:
            try:
                df = pd.read_csv(file, encoding="ISO-8859-1", engine="python")
                norm = normalize_backlink_df(df)
                all_dfs.append(norm)
            except:
                df = pd.read_csv(file, encoding="utf-8", engine="python")
                norm = normalize_backlink_df(df)
                all_dfs.append(norm)

        df = pd.concat(all_dfs, ignore_index=True)
        df['referring_domain'] = df['referring_page_url'].apply(lambda x: urlparse(str(x)).netloc.lower().replace("www.", ""))
        df["full_context"] = df[["left context", "anchor", "right context"]].astype(str).agg(' '.join, axis=1)
        df["anchor_lower"] = df["anchor"].astype(str).str.strip().str.lower()

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

        st.success(f"Found {len(final_domains)} new spammy domains.")
        st.download_button("⬇️ Download disavow_list.txt", '\n'.join(["domain:" + d for d in final_domains]), file_name="disavow_list.txt")

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            pd.DataFrame(final_domains, columns=["Referring Domain"]).to_excel(writer, sheet_name="Disavow Domains", index=False)
            matched.to_excel(writer, sheet_name="Disavow Details", index=False)
        st.download_button("⬇️ Download disavow_export.xlsx", output.getvalue(), file_name="disavow_export.xlsx")
