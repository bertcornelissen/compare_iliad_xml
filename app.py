import xml.etree.ElementTree as ET
import pandas as pd
import streamlit as st

st.set_page_config(page_title="EMVCo XML Diff", layout="wide")
st.title("EMVCo XML File Comparator")


def extract_messages(file) -> list[dict]:
    tree = ET.parse(file)
    root = tree.getroot()
    messages = []
    for msg in root.findall('.//OnlineMessage'):
        fields = {}
        for field in msg.findall('.//Field'):
            fid = field.get('ID')
            fval = field.findtext('FieldViewable')
            fname = field.findtext('FriendlyName')
            if fid and fval is not None:
                fields[fid] = (fname, fval)
        messages.append({
            'class': msg.get('Class'),
            'source': msg.get('Source'),
            'destination': msg.get('Destination'),
            'fields': fields,
        })
    return messages


def build_diff_df(m1: dict, m2: dict, label1: str, label2: str) -> pd.DataFrame:
    all_ids = sorted(set(m1['fields']) | set(m2['fields']))
    rows = []
    for fid in all_ids:
        v1 = m1['fields'].get(fid)
        v2 = m2['fields'].get(fid)
        if v1 != v2:
            name = (v1 or v2)[0] if (v1 or v2) else fid
            rows.append({
                'Field ID': fid,
                'Name': name,
                label1: v1[1] if v1 else '〈absent〉',
                label2: v2[1] if v2 else '〈absent〉',
            })
    return pd.DataFrame(rows)


col1, col2 = st.columns(2)
with col1:
    file1 = st.file_uploader("Upload first XML file", type=["xml", "emvco"], key="f1")
with col2:
    file2 = st.file_uploader("Upload second XML file", type=["xml", "emvco"], key="f2")

if file1 and file2:
    try:
        msgs1 = extract_messages(file1)
        msgs2 = extract_messages(file2)
    except ET.ParseError as e:
        st.error(f"XML parse error: {e}")
        st.stop()

    label1 = file1.name
    label2 = file2.name

    n = max(len(msgs1), len(msgs2))
    st.markdown(f"**{len(msgs1)}** messages in `{label1}` &nbsp;|&nbsp; **{len(msgs2)}** messages in `{label2}`")

    for i in range(n):
        if i >= len(msgs1):
            st.warning(f"Message {i+1}: only present in **{label2}** ({msgs2[i]['class']})")
            continue
        if i >= len(msgs2):
            st.warning(f"Message {i+1}: only present in **{label1}** ({msgs1[i]['class']})")
            continue

        m1, m2 = msgs1[i], msgs2[i]
        header = (
            f"Message {i+1} — "
            f"`{label1}`: **{m1['class']}** (src: {m1['source']})  ↔  "
            f"`{label2}`: **{m2['class']}** (src: {m2['source']})"
        )
        with st.expander(header, expanded=(i == 0)):
            df = build_diff_df(m1, m2, label1, label2)
            if df.empty:
                st.success("No differences found.")
            else:
                st.markdown(f"**{len(df)} differing field(s)**")

                def highlight_absent(val):
                    return 'color: #aaa; font-style: italic;' if val == '〈absent〉' else ''

                st.dataframe(
                    df.style.map(highlight_absent, subset=[label1, label2]),
                    width="stretch",
                    hide_index=True,
                )
else:
    st.info("Upload both XML files above to start the comparison.")
