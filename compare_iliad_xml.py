import xml.etree.ElementTree as ET
import os
import re
from functools import lru_cache
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Compare Iliad XML reports", layout="wide")
st.title("Iliad XML Report Compare")


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
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ignored_fields.txt')
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
                  ignore_set: set[str] | frozenset[str] = frozenset(),
                  show_all: bool = False) -> tuple[pd.DataFrame, int]:
    all_ids = sorted(set(m1['fields']) | set(m2['fields']))
    diff_ids = {
        fid for fid in all_ids
        if m1['fields'].get(fid) != m2['fields'].get(fid)
    }
    # Ignore a field only when it is present in both; absence must always be reported
    visible_diff_ids = {
        fid for fid in diff_ids
        if not (
            is_ignored(fid, ignore_set)
            and m1['fields'].get(fid) is not None
            and m2['fields'].get(fid) is not None
        )
    }
    suppressed = len(diff_ids) - len(visible_diff_ids)
    # Propagate suppression upward: if all differing children of a parent were suppressed by the
    # ignore list, suppress the parent too (process deepest fields first so cascading works).
    suppressed_ids = diff_ids - visible_diff_ids
    for fid in sorted(visible_diff_ids, key=lambda x: x.count('.'), reverse=True):
        v1_chk = m1['fields'].get(fid)
        v2_chk = m2['fields'].get(fid)
        if v1_chk is not None and v2_chk is not None:  # value diff (not presence diff)
            diff_children = {c for c in diff_ids if c.startswith(fid + '.')}
            if diff_children and diff_children.issubset(suppressed_ids):
                visible_diff_ids = visible_diff_ids - {fid}
                suppressed_ids.add(fid)
    suppressed = len(diff_ids) - len(visible_diff_ids)
    # When show_all, also include equal fields (never suppressed)
    candidate_ids = set(all_ids) if show_all else visible_diff_ids
    rows = []
    shown_absent_ids: set[str] = set()  # group IDs shown as absent in one file
    for fid in sorted(candidate_ids):
        is_diff = fid in visible_diff_ids
        v1 = m1['fields'].get(fid)
        v2 = m2['fields'].get(fid)
        if is_diff:
            if v1 is not None and v2 is not None:
                # Value difference: skip parent when subfields explain the change
                if any(other.startswith(fid + '.') for other in visible_diff_ids):
                    continue
            else:
                # Presence difference: skip child when an ancestor group is already shown absent
                parts = fid.split('.')
                if any('.'.join(parts[:d]) in shown_absent_ids for d in range(1, len(parts))):
                    continue
                shown_absent_ids.add(fid)
        name = (v1 or v2)[0] if (v1 or v2) else fid
        rows.append({
            'Field ID': fid,
            'Name': name,
            label1: v1[1] if v1 else '〈absent〉',
            label2: v2[1] if v2 else '〈absent〉',
            '_diff': is_diff,
        })
    return pd.DataFrame(rows), suppressed


col1, col2 = st.columns(2)
with col1:
    # To allow all file types, set type=None. Streamlit does not support '*' wildcard directly.
    file1 = st.file_uploader("Upload first XML file", type=None, key="f1")
with col2:
    # To allow all file types, set type=None. Streamlit does not support '*' wildcard directly.
    file2 = st.file_uploader("Upload second XML file", type=None, key="f2")

ignore_set = load_ignore_set()

with st.sidebar:
    st.header("Ignored fields")
    if st.button("↺ Refresh", help="Reload ignored_fields.txt"):
        st.rerun()
    apply_ignore = st.checkbox("Apply ignore list", value=True,
                               help="Uncheck to compare all fields without any exclusions.")
    show_all = st.checkbox("Show all fields", value=False,
                           help="Show equal fields alongside differences.")
    if ignore_set:
        st.code("\n".join(sorted(ignore_set)), language=None)
        st.caption(
            "Fields present in both files matching these entries "
            "(and their subfields) are excluded from the diff."
        )
    else:
        st.info("No fields ignored. Add entries to `ignored_fields.txt`.")

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
        df, suppressed = build_diff_df(m1, m2, label1, label2, active_ignore, show_all)
        diff_count = df['_diff'].sum() if not df.empty and '_diff' in df.columns else 0
        indicator = "🔴" if diff_count else "✅"
        header = (
            f"{indicator} Message {i+1} — "
            f"`{label1}`: **{m1['class']}** (src: {m1['source']})  ↔  "
            f"`{label2}`: **{m2['class']}** (src: {m2['source']})"
        )
        with st.expander(header, expanded=False):
            if diff_count == 0 and not show_all:
                st.success("No differences found." + (
                    f" ({suppressed} suppressed by ignore list)" if suppressed else ""
                ))
            else:
                note = f" — {suppressed} suppressed by ignore list" if suppressed else ""
                if show_all:
                    st.markdown(f"**{len(df)} field(s)** ({diff_count} differing){note}")
                else:
                    st.markdown(f"**{diff_count} differing field(s)**{note}")

                display_df = df.drop(columns=['_diff']) if '_diff' in df.columns else df
                diff_flags = df['_diff'] if '_diff' in df.columns else pd.Series([True] * len(df), index=df.index)

                def highlight_all(row, flags=diff_flags, lbl1=label1, lbl2=label2):
                    green_soft  = 'background-color: rgba(46,204,113,0.72)'
                    red_soft    = 'background-color: rgba(231,76,60,0.72)'
                    orange_soft = 'background-color: rgba(243,156,18,0.72)'
                    is_d = flags.loc[row.name]
                    styles = []
                    for col in row.index:
                        if col not in (lbl1, lbl2):
                            styles.append('')
                        elif not is_d:
                            styles.append('color: #aaa; font-style: italic;' if row[col] == '〈absent〉' else '')
                        else:
                            v1, v2 = row[lbl1], row[lbl2]
                            if v1 == '〈absent〉' and v2 != '〈absent〉':
                                # Added: colour only the new-value column
                                styles.append(green_soft if col == lbl2 else 'color: #aaa; font-style: italic;')
                            elif v1 != '〈absent〉' and v2 == '〈absent〉':
                                # Removed: colour only the old-value column
                                styles.append(red_soft if col == lbl1 else 'color: #aaa; font-style: italic;')
                            else:
                                # Changed: colour both value columns
                                styles.append(orange_soft)
                    return styles

                st.dataframe(
                    display_df.style.apply(highlight_all, axis=1),
                    width="stretch",
                    hide_index=True,
                    height=(len(display_df) + 1) * 35 + 3,
                )
else:
    st.info("Upload both XML files above to start the comparison.")
