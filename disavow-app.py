
import streamlit as st
import pandas as pd
import re
from urllib.parse import urlparse
import io

st.set_page_config(page_title="Disavow Combiner", layout="wide")
st.title("🔗 Combine & Filter Disavow Domains")

# Upload files
st.sidebar.header("Upload Required Files")
backlink_files = st.sidebar.file_uploader("Upload backlink CSV files", type="csv", accept_multiple_files=True)
anchor_file = st.sidebar.file_uploader("Upload suspicious anchor list (CSV)", type="csv")
disavow_file = st.sidebar.file_uploader("Upload existing disavow.txt", type="txt")

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

if st.button("🚀 Generate Disavow List"):
    if not backlink_files or not anchor_file or not disavow_file:
        st.warning("Please upload all files.")
    else:
        try:
            suspicious_df = pd.read_csv(anchor_file)
            suspicious_anchors = set(suspicious_df['anchor_text'].dropna().str.strip().str.lower())

            disavow_lines = disavow_file.read().decode("utf-8", errors="ignore").splitlines()
            existing_domains = {
                str(line).strip().replace("domain:", "").lower().replace("www.", "")
                for line in disavow_lines if str(line).strip().startswith("domain:")
            }

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

            st.success(f"🎯 {len(final_domains)} new spammy domains detected.")
            st.download_button("⬇️ Download disavow_list.txt", '\n'.join(["domain:" + d for d in final_domains]), file_name="disavow_list.txt")

            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                pd.DataFrame(final_domains, columns=["Referring Domain"]).to_excel(writer, sheet_name="Disavow Domains", index=False)
                matched.to_excel(writer, sheet_name="Disavow Details", index=False)
            st.download_button("⬇️ Download disavow_export.xlsx", output.getvalue(), file_name="disavow_export.xlsx")
        except Exception as e:
            st.error(f"Something went wrong: {e}")
