import xml.etree.ElementTree as ET
import os
import re
from functools import lru_cache
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


def load_ignore_set() -> set[str]:
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ignore_fields.txt')
    try:
        with open(path) as f:
            return {line.strip() for line in f if line.strip() and not line.strip().startswith('#')}
    except FileNotFoundError:
        return set()


@lru_cache(maxsize=None)
def _pattern_regex(pattern: str) -> re.Pattern:
    """Compile a field-ID pattern to a regex. * matches any single dot-delimited segment.
    Also matches subfields (anything after a further dot)."""
    escaped = re.escape(pattern)
    regex_str = escaped.replace(r'\*', r'[^.]+')
    return re.compile('^' + regex_str + r'(\..+)?$')


def is_ignored(fid: str, ignore_set: set[str] | frozenset[str]) -> bool:
    return any(_pattern_regex(p).match(fid) for p in ignore_set)


def build_diff_df(m1: dict, m2: dict, label1: str, label2: str,
                  ignore_set: set[str] | frozenset[str] = frozenset()) -> tuple[pd.DataFrame, int]:
    all_ids = sorted(set(m1['fields']) | set(m2['fields']))
    diff_ids = {
        fid for fid in all_ids
        if m1['fields'].get(fid) != m2['fields'].get(fid)
    }
    # Ignore a field only when it is present in both; absence must always be reported
    visible_ids = {
        fid for fid in diff_ids
        if not (
            is_ignored(fid, ignore_set)
            and m1['fields'].get(fid) is not None
            and m2['fields'].get(fid) is not None
        )
    }
    suppressed = len(diff_ids) - len(visible_ids)
    rows = []
    for fid in sorted(visible_ids):
        # Skip parent fields whose difference is explained by differing subfields
        if any(other.startswith(fid + '.') for other in visible_ids):
            continue
        v1 = m1['fields'].get(fid)
        v2 = m2['fields'].get(fid)
        name = (v1 or v2)[0] if (v1 or v2) else fid
        rows.append({
            'Field ID': fid,
            'Name': name,
            label1: v1[1] if v1 else '〈absent〉',
            label2: v2[1] if v2 else '〈absent〉',
        })
    return pd.DataFrame(rows), suppressed


col1, col2 = st.columns(2)
with col1:
    file1 = st.file_uploader("Upload first XML file", type=["xml", "emvco"], key="f1")
with col2:
    file2 = st.file_uploader("Upload second XML file", type=["xml", "emvco"], key="f2")

ignore_set = load_ignore_set()

with st.sidebar:
    st.header("Ignored fields")
    if st.button("↺ Refresh", help="Reload ignore_fields.txt"):
        st.rerun()
    apply_ignore = st.checkbox("Apply ignore list", value=True,
                               help="Uncheck to compare all fields without any exclusions.")
    if ignore_set:
        st.code("\n".join(sorted(ignore_set)), language=None)
        st.caption(
            "Fields present in both files matching these entries "
            "(and their subfields) are excluded from the diff."
        )
    else:
        st.info("No fields ignored. Add entries to `ignore_fields.txt`.")

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
        active_ignore = ignore_set if apply_ignore else frozenset()
        df, suppressed = build_diff_df(m1, m2, label1, label2, active_ignore)
        indicator = "🔴" if not df.empty else "✅"
        header = (
            f"{indicator} Message {i+1} — "
            f"`{label1}`: **{m1['class']}** (src: {m1['source']})  ↔  "
            f"`{label2}`: **{m2['class']}** (src: {m2['source']})"
        )
        with st.expander(header, expanded=(i == 0 or not df.empty)):
            if df.empty:
                st.success("No differences found." + (
                    f" ({suppressed} suppressed by ignore list)" if suppressed else ""
                ))
            else:
                note = f" — {suppressed} suppressed by ignore list" if suppressed else ""
                st.markdown(f"**{len(df)} differing field(s)**{note}")

                def highlight_absent(val):
                    return 'color: #aaa; font-style: italic;' if val == '〈absent〉' else ''

                st.dataframe(
                    df.style.map(highlight_absent, subset=[label1, label2]),
                    width="stretch",
                    hide_index=True,
                )
else:
    st.info("Upload both XML files above to start the comparison.")
