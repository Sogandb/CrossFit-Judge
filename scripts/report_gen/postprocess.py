"""Post-process the generated docx (per docx skill toc.md rules):
1. Remove empty <w:pgNumType/> elements (docx-js emits them; they confuse WPS).
2. Patch footer PAGE fields with explicit format switch (\\* arabic) for WPS.
"""
import re
import shutil
import sys
import zipfile

SRC = "/home/z/my-project/download/CrossFit-Judge-v1-Code-Review-Report-FA.docx"
TMP = SRC + ".tmp"

def main():
    with zipfile.ZipFile(SRC, "r") as zin:
        items = zin.infolist()
        data = {i.filename: zin.read(i.filename) for i in items}

    changed = []

    # 1. strip empty pgNumType from document.xml
    doc = data["word/document.xml"].decode("utf-8")
    new_doc, n1 = re.subn(r"<w:pgNumType\s*/>", "", doc)
    if n1:
        data["word/document.xml"] = new_doc.encode("utf-8")
        changed.append(f"document.xml: removed {n1} empty pgNumType")

    # 2. patch every footer's bare PAGE instrText with \* arabic
    for name in list(data.keys()):
        if re.match(r"word/footer\d*\.xml$", name):
            xml = data[name].decode("utf-8")
            new_xml, n2 = re.subn(
                r"(<w:instrText[^>]*>)\s*PAGE\s*(</w:instrText>)",
                r"\1 PAGE \\* arabic \\* MERGEFORMAT \2",
                xml,
            )
            if n2:
                data[name] = new_xml.encode("utf-8")
                changed.append(f"{name}: patched {n2} PAGE field(s) with arabic switch")

    with zipfile.ZipFile(TMP, "w", zipfile.ZIP_DEFLATED) as zout:
        for i in items:
            zout.writestr(i, data[i.filename])
    shutil.move(TMP, SRC)

    for c in changed:
        print(" -", c)
    if not changed:
        print(" - nothing to change")

if __name__ == "__main__":
    sys.exit(main())
