import xml.etree.ElementTree as ET


def extract_messages(xml_file):
    tree = ET.parse(xml_file)
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


def compare_messages(file1, file2):
    msgs1 = extract_messages(file1)
    msgs2 = extract_messages(file2)
    n = max(len(msgs1), len(msgs2))
    for i in range(n):
        if i >= len(msgs1):
            print(f"\nMessage {i+1}: only in {file2}: {msgs2[i]['class']}")
            continue
        if i >= len(msgs2):
            print(f"\nMessage {i+1}: only in {file1}: {msgs1[i]['class']}")
            continue
        m1, m2 = msgs1[i], msgs2[i]
        print(f"\n{'='*120}")
        print(f"Message {i+1}: [{file1}] {m1['class']}  vs  [{file2}] {m2['class']}")
        print(f"{'='*120}")
        all_ids = sorted(set(m1['fields']) | set(m2['fields']))
        diff_ids = {
            fid for fid in all_ids
            if m1['fields'].get(fid) != m2['fields'].get(fid)
        }
        diffs = []
        for fid in sorted(diff_ids):
            # Skip parent fields whose difference is explained by differing subfields
            if any(other.startswith(fid + '.') for other in diff_ids):
                continue
            v1 = m1['fields'].get(fid)
            v2 = m2['fields'].get(fid)
            name = (v1 or v2)[0] if (v1 or v2) else fid
            val1 = v1[1] if v1 else '<absent>'
            val2 = v2[1] if v2 else '<absent>'
            diffs.append((fid, name, val1, val2))
        if diffs:
            col1, col2, col3, col4 = 38, 43, 35, 35
            header = f"  {'Field ID':<{col1}} {'Name':<{col2}} {file1:<{col3}} {file2:<{col4}}"
            print(header)
            print(f"  {'-'*(col1+col2+col3+col4+6)}")
            for fid, name, val1, val2 in diffs:
                print(f"  {fid:<{col1}} {name:<{col2}} {val1:<{col3}} {val2:<{col4}}")
        else:
            print("  No differences found.")


if __name__ == "__main__":
    compare_messages("IPH.xml", "WLPFO.xml")
