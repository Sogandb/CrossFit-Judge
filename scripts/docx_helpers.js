// docx_helpers.js — RTL Persian docx helpers (docx-js)
const {
  Paragraph, TextRun, Table, TableRow, TableCell, HeadingLevel,
  AlignmentType, WidthType, BorderStyle, ShadingType, TableLayoutType,
} = require("docx");

// ── Palette: DM-1 Deep Cyan (docx skill design-system) ──
const PAL = {
  primary: "162235",
  body: "000000",
  secondary: "506070",
  accent: "1B6B7A",
  cover: {
    bg: "162235", accent: "37DCF2",
    titleColor: "FFFFFF", subtitleColor: "B0B8C0",
    metaColor: "90989F", footerColor: "687078",
  },
  table: {
    headerBg: "1B6B7A", headerText: "FFFFFF",
    accentLine: "1B6B7A", innerLine: "C8DDE2", surface: "EDF3F5",
  },
};

const FONT = { ascii: "Tahoma", hAnsi: "Tahoma", cs: "Tahoma", eastAsia: "Tahoma" };

// Persian run (RTL)
function fa(text, o = {}) {
  return new TextRun({
    text, font: FONT, rightToLeft: true,
    size: o.size || 22, bold: !!o.bold, italics: !!o.italics,
    color: o.color || PAL.body,
  });
}

// Latin/technical run (LTR embedded inside RTL paragraph)
function en(text, o = {}) {
  return new TextRun({
    text, font: FONT,
    size: o.size || 22, bold: !!o.bold, italics: !!o.italics,
    color: o.color || PAL.body,
  });
}

// Body paragraph (justified, RTL, first-line indent)
function p(content, o = {}) {
  const runs = Array.isArray(content) ? content : [fa(content, o)];
  return new Paragraph({
    bidirectional: true,
    alignment: o.align || AlignmentType.JUSTIFIED,
    indent: { firstLine: o.noIndent ? 0 : 400 },
    spacing: { line: 312, after: o.after != null ? o.after : 120, before: o.before || 0 },
    keepNext: !!o.keepNext,
    children: runs,
  });
}

// List-like paragraph (start-aligned, no justify per formatting rules; inline marker)
function li(content, o = {}) {
  const runs = Array.isArray(content) ? content : [fa(content, o)];
  return new Paragraph({
    bidirectional: true,
    // default start alignment (right for bidi) — no justification for list items
    indent: { left: 340 },
    spacing: { line: 312, after: 80 },
    children: runs,
  });
}

// Headings (Heading styles required for TOC)
function h1(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1, bidirectional: true,
    spacing: { before: 400, after: 180, line: 380, lineRule: "atLeast" },
    children: [fa(text, { size: 32, bold: true, color: PAL.primary })],
  });
}
function h2(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2, bidirectional: true,
    spacing: { before: 280, after: 140, line: 330, lineRule: "atLeast" },
    children: [fa(text, { size: 26, bold: true, color: PAL.primary })],
  });
}
function h3(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_3, bidirectional: true,
    spacing: { before: 220, after: 110, line: 312 },
    children: [fa(text, { size: 23, bold: true, color: "1E3A50" })],
  });
}

// Table caption (before table, keepNext)
function tableCaption(text) {
  return new Paragraph({
    bidirectional: true, keepNext: true,
    spacing: { before: 160, after: 100, line: 312 },
    children: [fa(text, { size: 21, bold: true, color: PAL.secondary })],
  });
}

// Figure caption (after image)
function figCaption(text) {
  return new Paragraph({
    bidirectional: true, alignment: AlignmentType.CENTER,
    spacing: { before: 80, after: 200, line: 312 },
    children: [fa(text, { size: 21, color: PAL.secondary })],
  });
}

// RTL data table. cols: [{w: percent, header: "…"}], rows: [[cell, …], …]
// Cell content: string (Persian) or {runs:[…], align}
function rtlTable(colPercents, headerCells, dataRows, o = {}) {
  const mkHeaderCell = (text, w) => new TableCell({
    width: { size: w, type: WidthType.PERCENTAGE },
    shading: { type: ShadingType.CLEAR, fill: PAL.table.headerBg },
    margins: { top: 70, bottom: 70, left: 110, right: 110 },
    children: [new Paragraph({
      bidirectional: true, alignment: AlignmentType.CENTER,
      spacing: { line: 300 },
      children: [fa(text, { size: o.headSize || 21, bold: true, color: PAL.table.headerText })],
    })],
  });
  const mkCell = (content, w, iRow) => {
    let runs, align = null;
    if (typeof content === "object" && content !== null && content.runs) {
      runs = content.runs; align = content.align;
    } else {
      runs = [fa(String(content), { size: o.cellSize || 20 })];
    }
    return new TableCell({
      width: { size: w, type: WidthType.PERCENTAGE },
      shading: (iRow % 2 === 1 && o.zebra) ? { type: ShadingType.CLEAR, fill: PAL.table.surface } : undefined,
      margins: { top: 60, bottom: 60, left: 110, right: 110 },
      children: [new Paragraph({
        bidirectional: true,
        alignment: align || AlignmentType.START,
        spacing: { line: 300 },
        children: runs,
      })],
    });
  };
  return new Table({
    visuallyRightToLeft: true,
    width: { size: 100, type: WidthType.PERCENTAGE },
    layout: TableLayoutType.FIXED,
    borders: {
      top: { style: BorderStyle.SINGLE, size: 6, color: PAL.table.accentLine },
      bottom: { style: BorderStyle.SINGLE, size: 6, color: PAL.table.accentLine },
      left: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" },
      right: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" },
      insideHorizontal: { style: BorderStyle.SINGLE, size: 2, color: PAL.table.innerLine },
      insideVertical: { style: BorderStyle.SINGLE, size: 2, color: PAL.table.innerLine },
    },
    rows: [
      new TableRow({
        tableHeader: true, cantSplit: true,
        children: headerCells.map((t, i) => mkHeaderCell(t, colPercents[i])),
      }),
      ...dataRows.map((row, iRow) => new TableRow({
        cantSplit: true,
        children: row.map((c, i) => mkCell(c, colPercents[i], iRow)),
      })),
    ],
  });
}

module.exports = { PAL, FONT, fa, en, p, li, h1, h2, h3, tableCaption, figCaption, rtlTable };
