const { Document, Packer, Paragraph, TextRun } = require('docx');
const fs = require('fs');
const doc = new Document({
  sections: [{
    children: [
      new Paragraph({
        bidirectional: true,
        children: [new TextRun({ text: 'TEST', rightToLeft: true, size: 24, bold: true })],
      }),
    ],
  }],
});
Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync('/home/z/my-project/scripts/rtl_test.docx', buf);
  console.log('written');
});
