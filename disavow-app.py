import streamlit as st
import pandas as pd
import re
from urllib.parse import urlparse
import io
import tldextract

# === PAGE SETUP ===
st.set_page_config(page_title="Disavow Tool", layout="wide")
st.title("🔗 Disavow Tool")

# === SIDEBAR ===
st.sidebar.header("Upload Required Files")

# upload_key increments on reset, forcing file uploader widgets to re-initialize empty
if "upload_key" not in st.session_state:
    st.session_state["upload_key"] = 0

_backlink_uploads = st.sidebar.file_uploader(
    "Upload backlink CSV files", type="csv", accept_multiple_files=True,
    key=f"backlink_uploader_{st.session_state['upload_key']}"
)
_disavow_upload = st.sidebar.file_uploader(
    "Upload existing disavow.txt (optional)", type="txt",
    key=f"disavow_uploader_{st.session_state['upload_key']}"
)

# Persist uploaded file bytes in session state so they survive reruns
if _backlink_uploads:
    st.session_state["backlink_file_data"] = [
        {"name": f.name, "data": f.read()} for f in _backlink_uploads
    ]
if _disavow_upload:
    st.session_state["disavow_file_data"] = {"name": _disavow_upload.name, "data": _disavow_upload.read()}

class NamedBytesIO(io.BytesIO):
    """BytesIO with a name attribute, compatible with pd.read_csv."""
    def __init__(self, data, name):
        super().__init__(data)
        self.name = name

# Reconstruct seekable file-like objects from session state
backlink_files = [
    NamedBytesIO(f["data"], f["name"])
    for f in st.session_state.get("backlink_file_data", [])
]
_disavow_data = st.session_state.get("disavow_file_data")
disavow_file = NamedBytesIO(_disavow_data["data"], _disavow_data["name"]) if _disavow_data else None

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

def get_root_domain(domain):
    """Extract eTLD+1 (e.g. 'sub.example.co.uk' -> 'example.co.uk')."""
    ext = tldextract.extract(domain)
    if ext.domain and ext.suffix:
        return f"{ext.domain}.{ext.suffix}"
    return domain

def is_already_disavowed(domain, existing_domains, existing_root_domains):
    """Return True if domain or its root domain is already disavowed."""
    if domain in existing_domains:
        return True
    root = get_root_domain(domain)
    return root in existing_domains or root in existing_root_domains

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

# === GENERATE DISAVOW LIST ===
if st.button("🚀 Generate Disavow List"):
    if not backlink_files:
        st.warning("Please upload at least one backlink CSV file.")
    else:
        try:
            suspicious_df = pd.read_csv(CSV_EXPORT_URL)
            suspicious_anchors = set(suspicious_df['anchor_text'].dropna().astype(str).str.strip().str.lower())

            if disavow_file:
                disavow_lines = disavow_file.read().decode("utf-8", errors="ignore").splitlines()
                existing_domains = {
                    str(line).strip().replace("domain:", "").lower().replace("www.", "")
                    for line in disavow_lines if str(line).strip().startswith("domain:")
                }
                # Root domains already disavowed — any subdomain of these is covered
                existing_root_domains = {get_root_domain(d) for d in existing_domains}
            else:
                existing_domains = set()
                existing_root_domains = set()

            all_dfs = []
            for file in backlink_files:
                try:
                    # Try multiple encoding and parsing strategies
                    df = None
                    encodings = ["utf-8", "ISO-8859-1", "latin-1", "cp1252"]
                    engines = ["c", "python"]
                    
                    # Check pandas version for backward compatibility
                    pandas_version = pd.__version__
                    use_on_bad_lines = tuple(map(int, pandas_version.split('.')[:2])) >= (1, 3)
                    
                    for encoding in encodings:
                        for engine in engines:
                            # Try different quoting strategies for malformed CSVs
                            quoting_options = [None, 3, 0] if engine == "python" else [None]
                            
                            for quoting in quoting_options:
                                try:
                                    file.seek(0)  # Reset file pointer
                                    
                                    # Build read_csv parameters
                                    read_params = {
                                        "encoding": encoding,
                                        "engine": engine,
                                        "skipinitialspace": True,
                                    }
                                    
                                    if quoting is not None:
                                        read_params["quoting"] = quoting
                                    
                                    if engine == "c":
                                        read_params["low_memory"] = False
                                    else:
                                        read_params["sep"] = ","
                                    
                                    # Add error handling parameter based on pandas version
                                    if use_on_bad_lines:
                                        read_params["on_bad_lines"] = "skip"
                                    else:
                                        read_params["error_bad_lines"] = False
                                        read_params["warn_bad_lines"] = False
                                    
                                    df = pd.read_csv(file, **read_params)
                                    
                                    if df is not None and not df.empty and len(df.columns) > 0:
                                        break
                                except Exception:
                                    continue
                            
                            if df is not None and not df.empty and len(df.columns) > 0:
                                break
                        if df is not None and not df.empty and len(df.columns) > 0:
                            break
                    
                    if df is None or df.empty or len(df.columns) == 0:
                        raise ValueError("Could not parse CSV with any encoding/engine combination or file is empty.")
                    
                    norm = normalize_backlink_df(df)
                    all_dfs.append(norm)
                except Exception as e:
                    st.warning(f"⚠️ Skipped {file.name}: {e}")

            df = pd.concat(all_dfs, ignore_index=True)
            df['referring_domain'] = df['referring_page_url'].apply(lambda x: urlparse(str(x)).netloc.lower().replace("www.", ""))
            df["full_context"] = df[["left context", "anchor", "right context"]].fillna("").astype(str).agg(' '.join, axis=1)
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

            # Exclude domains already covered (exact match OR root domain already disavowed)
            mask_covered = matched['referring_domain'].apply(
                lambda d: is_already_disavowed(d, existing_domains, existing_root_domains)
            )
            skipped_subdomain_count = int(mask_covered.sum()) - int(matched['referring_domain'].isin(existing_domains).sum())
            matched = matched[~mask_covered]
            final_domains = sorted(set(matched['referring_domain']))

            msg = f"🌟 {len(final_domains)} new spammy domains detected."
            if skipped_subdomain_count > 0:
                msg += f" ({skipped_subdomain_count} subdomain entries skipped — root domain already disavowed)"
            st.success(msg)

            disavow_txt = '\n'.join(["domain:" + d for d in final_domains])
            st.session_state["disavow_txt"] = disavow_txt

            excel_output = io.BytesIO()
            with pd.ExcelWriter(excel_output, engine='xlsxwriter') as writer:
                pd.DataFrame(final_domains, columns=["referring_domain"]).to_excel(writer, sheet_name="Disavow Domains", index=False)
                matched.to_excel(writer, sheet_name="Disavow Details", index=False)
            excel_output.seek(0)
            st.session_state["disavow_xlsx"] = excel_output.read()

        except Exception as e:
            st.error(f"❌ Something went wrong: {e}")

# === DOWNLOAD RESULTS ===
if "disavow_txt" in st.session_state and "disavow_xlsx" in st.session_state:
    st.download_button("⬇️ Download disavow_list.txt", st.session_state["disavow_txt"], file_name="disavow_list.txt", key="download_txt_button")
    st.download_button("⬇️ Download disavow_export.xlsx", st.session_state["disavow_xlsx"], file_name="disavow_export.xlsx", key="download_xlsx_button")

# === MERGE REVIEWED EXCEL + EXISTING DISAVOW (STRICT PRESERVE MODE) ===
with st.expander("📎 Merge Reviewed Excel with Existing disavow.txt"):
    reviewed_excel = st.file_uploader("Upload reviewed Excel (Disavow Details tab)", type=["xlsx"], key="merge_reviewed_xlsx")
    existing_disavow = st.file_uploader("Upload previous disavow.txt file", type=["txt"], key="merge_existing_disavow")

    if st.button("📄 Generate Merged disavow.txt"):
        if not reviewed_excel or not existing_disavow:
            st.warning("Please upload both reviewed Excel and previous disavow.txt.")
        else:
            try:
                # Load existing disavow file
                disavow_lines = existing_disavow.read().decode("utf-8", errors="ignore").splitlines()
                preserved_lines = [line for line in disavow_lines if not line.strip().lower().startswith("domain:")]
                existing_domains = {
                    line.strip().lower().replace("domain:", "").replace("www.", "")
                    for line in disavow_lines if line.strip().lower().startswith("domain:")
                }
                existing_root_domains = {get_root_domain(d) for d in existing_domains}

                # Extract referring_page_url domains from reviewed Excel
                xls = pd.ExcelFile(reviewed_excel, engine="openpyxl")
                if "Disavow Details" not in xls.sheet_names:
                    raise ValueError("Sheet 'Disavow Details' not found.")

                df = xls.parse("Disavow Details")
                if "referring_page_url" not in df.columns:
                    raise ValueError("Column 'referring_page_url' not found.")

                reviewed_domains = df["referring_page_url"].dropna().apply(
                    lambda x: urlparse(str(x)).netloc.lower().replace("www.", "")
                )
                reviewed_domains = set(d for d in reviewed_domains if d)

                # Find new domains only — skip if exact match OR root domain already disavowed
                new_domains = sorted(
                    d for d in reviewed_domains
                    if not is_already_disavowed(d, existing_domains, existing_root_domains)
                )
                already_present = {
                    d for d in reviewed_domains
                    if is_already_disavowed(d, existing_domains, existing_root_domains)
                }

                # Final output
                final_lines = disavow_lines + [f"domain:{d}" for d in new_domains]
                final_text = '\n'.join(final_lines)

                st.success(f"""
✅ Merged disavow file created!

• Total reviewed: **{len(reviewed_domains)}**
• Already present: **{len(already_present)}**
• Newly added: **{len(new_domains)}**
""")
                st.download_button("⬇️ Download merged_disavow.txt", final_text, file_name="merged_disavow.txt")

            except Exception as e:
                st.error(f"❌ Error merging files: {e}")

# === Reset App ===
if st.sidebar.button("🔄 Reset App"):
    current_key = st.session_state.get("upload_key", 0)
    st.session_state.clear()
    st.session_state["upload_key"] = current_key + 1  # Forces file uploaders to re-render empty
    st.rerun()
