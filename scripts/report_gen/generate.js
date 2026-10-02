// تولید سند docx گزارش بررسی فنی CrossFit-Judge — فارسی راست‌به‌چپ
// RTL Persian docx generation, following docx skill rules (R1 cover recipe adapted to RTL,
// 3-section architecture, TOC field + placeholders, tables with margins/CLEAR shading).

const path = require("path");
const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, Footer, PageNumber, NumberFormat, AlignmentType, HeadingLevel,
  WidthType, BorderStyle, ShadingType, TableLayoutType, SectionType,
  TableOfContents, PageBreak,
} = require("docx");

const C1 = require("./content1.js");
const C2 = require("./content2.js");

// ---------------------------------------------------------------- palette
const PAL = {
  // body palette
  primary: "16202E", body: "1F2937", secondary: "5B6B7D",
  accent: "C2410C", surface: "F4F6F9",
  // cover palette (R1 dark)
  bg: "101720", titleColor: "F5F7FA", subtitleColor: "AFC0D0",
  metaColor: "C9D6E2", coverAccent: "E8552F", footerColor: "8795A6",
};

const FONT = "Vazirmatn";

// ---------------------------------------------------------------- borders
const NB = { style: BorderStyle.NONE, size: 0, color: "auto" };
const noBorders = { top: NB, bottom: NB, left: NB, right: NB };
const allNoBorders = {
  top: NB, bottom: NB, left: NB, right: NB,
  insideHorizontal: NB, insideVertical: NB,
};

// ---------------------------------------------------------------- run/paragraph helpers
function rtl(text, opts = {}) {
  return new TextRun({
    text,
    rightToLeft: true,
    font: FONT,
    size: opts.size || 24,
    bold: !!opts.bold,
    italics: !!opts.italics,
    color: opts.color || PAL.body,
  });
}

function ltr(text, opts = {}) {
  return new TextRun({
    text,
    font: FONT,
    size: opts.size || 24,
    bold: !!opts.bold,
    color: opts.color || PAL.body,
    characterSpacing: opts.characterSpacing,
  });
}

// body paragraph (justified RTL, 1.3x line spacing, small first-line indent)
function faP(text) {
  return new Paragraph({
    bidirectional: true,
    alignment: AlignmentType.JUSTIFIED,
    spacing: { line: 312, after: 140 },
    indent: { firstLine: 340 },
    children: [rtl(text)],
  });
}

function faH1(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    bidirectional: true,
    alignment: AlignmentType.START,
    spacing: { before: 420, after: 200, line: 380, lineRule: "atLeast" },
    children: [rtl(text, { size: 32, bold: true, color: PAL.primary })],
  });
}

function faH2(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    bidirectional: true,
    alignment: AlignmentType.START,
    spacing: { before: 300, after: 150, line: 340, lineRule: "atLeast" },
    children: [rtl(text, { size: 27, bold: true, color: PAL.primary })],
  });
}

// ---------------------------------------------------------------- tables
const STATUS_STYLE = {
  "موجود": { fill: "EAF6EC", color: "1E6B33" },
  "جزئی": { fill: "FFF6E5", color: "92600A" },
  "غایب": { fill: "FDECEC", color: "A02B2B" },
};

function cellP(text, opts = {}) {
  return new Paragraph({
    bidirectional: true,
    alignment: AlignmentType.START,
    spacing: { line: 276 },
    children: [rtl(text, { size: opts.size || 20, bold: !!opts.bold, color: opts.color || PAL.body })],
  });
}

function mkTable({ title, headers, widths, rows }) {
  const out = [];
  // table caption — keepNext keeps it with the table
  out.push(new Paragraph({
    bidirectional: true,
    alignment: AlignmentType.START,
    keepNext: true,
    spacing: { before: 220, after: 110, line: 312 },
    children: [rtl(title, { size: 21, bold: true, color: PAL.secondary })],
  }));

  const headerRow = new TableRow({
    tableHeader: true,
    cantSplit: true,
    children: headers.map((h, i) => new TableCell({
      width: { size: widths[i], type: WidthType.PERCENTAGE },
      shading: { type: ShadingType.CLEAR, fill: "E8EDF3" },
      margins: { top: 90, bottom: 90, left: 110, right: 110 },
      borders: noBorders,
      children: [cellP(h, { bold: true, size: 20, color: PAL.primary })],
    })),
  });

  const dataRows = rows.map((r) => new TableRow({
    cantSplit: true,
    children: r.map((cellText, i) => {
      const st = STATUS_STYLE[cellText];
      return new TableCell({
        width: { size: widths[i], type: WidthType.PERCENTAGE },
        shading: st ? { type: ShadingType.CLEAR, fill: st.fill } : undefined,
        margins: { top: 80, bottom: 80, left: 110, right: 110 },
        borders: noBorders,
        children: [cellP(cellText, st ? { bold: true, color: st.color } : {})],
      });
    }),
  }));

  out.push(new Table({
    visuallyRightToLeft: true,
    width: { size: 100, type: WidthType.PERCENTAGE },
    layout: TableLayoutType.FIXED,
    borders: {
      top: { style: BorderStyle.SINGLE, size: 6, color: PAL.accent },
      bottom: { style: BorderStyle.SINGLE, size: 6, color: PAL.accent },
      left: NB, right: NB,
      insideHorizontal: { style: BorderStyle.SINGLE, size: 2, color: "D5DBE3" },
      insideVertical: NB,
    },
    rows: [headerRow, ...dataRows],
  }));
  // spacer after table
  out.push(new Paragraph({ spacing: { after: 120, line: 240 }, children: [] }));
  return out;
}

// ---------------------------------------------------------------- cover (R1 adapted to RTL)
function faCalcTitleLayout(title, maxWidthTwips, preferredPt = 38, minPt = 24) {
  // Persian average glyph width ~ 0.55 of a CJK char => pt * 11.5 twips
  const charW = (pt) => pt * 11.5;
  const wrap = (pt) => {
    const cpl = Math.max(4, Math.floor(maxWidthTwips / charW(pt)));
    const words = title.split(" ");
    const lines = [];
    let cur = "";
    for (const w of words) {
      const cand = cur ? cur + " " + w : w;
      if (cand.length <= cpl) { cur = cand; }
      else { if (cur) lines.push(cur); cur = w; }
    }
    if (cur) lines.push(cur);
    return lines;
  };
  let pt = preferredPt;
  let lines = wrap(pt);
  while (lines.length > 3 && pt > minPt) { pt -= 2; lines = wrap(pt); }
  // orphan merge: last line with 1 short word
  if (lines.length > 1 && lines[lines.length - 1].length <= 4) {
    const last = lines.pop();
    lines[lines.length - 1] += " " + last;
  }
  return { titlePt: pt, titleLines: lines };
}

function calcCoverSpacing(params) {
  const {
    titleLineCount = 1, titlePt = 36, hasSubtitle = false,
    hasEnglishLabel = false, metaLineCount = 0,
    fixedHeight = 800, pageHeight = 16838,
  } = params;
  const SAFETY = 1200;
  const usableHeight = pageHeight - SAFETY;
  const titleHeight = titleLineCount * (titlePt * 23 + 200);
  const subtitleHeight = hasSubtitle ? (12 * 23 + 600) : 0;
  const englishLabelHeight = hasEnglishLabel ? (9 * 23 + 600) : 0;
  const metaHeight = metaLineCount * (10 * 23 + 140);
  const implicitParaHeight = 3 * 300;
  const contentHeight = titleHeight + subtitleHeight + englishLabelHeight +
    metaHeight + fixedHeight + implicitParaHeight;
  const remainingSpace = usableHeight - contentHeight;
  const safeRemaining = Math.max(remainingSpace, 400);
  const FOOTER_MIN = 800;
  const rawTop = Math.floor(safeRemaining * 0.45);
  const rawBottom = Math.floor(safeRemaining * 0.45);
  const bottomSpacing = Math.max(rawBottom, FOOTER_MIN);
  const topSpacing = Math.max(rawTop - Math.max(0, FOOTER_MIN - rawBottom), 400);
  const midSpacing = Math.max(safeRemaining - topSpacing - bottomSpacing, 0);
  return { topSpacing, midSpacing, bottomSpacing };
}

function buildCoverR1RTL(config) {
  const P = {
    bg: PAL.bg, titleColor: PAL.titleColor, subtitleColor: PAL.subtitleColor,
    metaColor: PAL.metaColor, accent: PAL.coverAccent, footerColor: PAL.footerColor,
  };
  const padR = 1200, padL = 800; // RTL: text anchored to the right

  const availableWidth = 11906 - padR - padL - 300;
  const { titlePt, titleLines } = faCalcTitleLayout(config.title, availableWidth, 38, 24);
  const titleSize = titlePt * 2;

  const spacing = calcCoverSpacing({
    titleLineCount: titleLines.length, titlePt,
    hasSubtitle: true, hasEnglishLabel: true,
    metaLineCount: config.metaLines.length, fixedHeight: 400,
  });

  const accentRight = { style: BorderStyle.SINGLE, size: 8, color: P.accent, space: 12 };
  const children = [];

  // 1. top whitespace (dynamic)
  children.push(new Paragraph({ spacing: { before: spacing.topSpacing } }));

  // 2. English label with accent bottom border (anchored right)
  children.push(new Paragraph({
    bidirectional: true,
    alignment: AlignmentType.START,
    indent: { right: padR, left: padL },
    spacing: { after: 500, line: 280, lineRule: "atLeast" },
    border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: P.accent, space: 8 } },
    children: [new TextRun({
      text: config.englishLabel.split("").join(" "),
      size: 19, color: P.accent, font: FONT, characterSpacing: 30,
    })],
  }));

  // 3. title lines (dynamic size, semantic breaks)
  titleLines.forEach((line, i) => {
    children.push(new Paragraph({
      bidirectional: true,
      alignment: AlignmentType.START,
      indent: { right: padR, left: padL },
      spacing: {
        after: i < titleLines.length - 1 ? 100 : 300,
        line: Math.ceil(titlePt * 23), lineRule: "atLeast",
      },
      children: [rtl(line, { size: titleSize, bold: true, color: P.titleColor })],
    }));
  });

  // 4. subtitle
  children.push(new Paragraph({
    bidirectional: true,
    alignment: AlignmentType.START,
    indent: { right: padR, left: padL },
    spacing: { after: 700, line: 340, lineRule: "atLeast" },
    children: [rtl(config.subtitle, { size: 24, color: P.subtitleColor })],
  }));

  // 5. meta lines with right accent border
  config.metaLines.forEach((line) => {
    children.push(new Paragraph({
      bidirectional: true,
      alignment: AlignmentType.START,
      indent: { right: padR + 200, left: padL },
      spacing: { after: 110, line: 300, lineRule: "atLeast" },
      border: { right: accentRight },
      children: [rtl(line, { size: 21, color: P.metaColor })],
    }));
  });

  // 6. bottom whitespace (dynamic)
  children.push(new Paragraph({ spacing: { before: spacing.bottomSpacing } }));

  // 7. footer with top accent separator
  children.push(new Paragraph({
    bidirectional: true,
    alignment: AlignmentType.START,
    indent: { right: padR, left: padL },
    spacing: { before: 200, line: 260, lineRule: "atLeast" },
    border: { top: { style: BorderStyle.SINGLE, size: 2, color: P.accent, space: 8 } },
    children: [
      rtl(config.footerRight, { size: 16, color: P.footerColor }),
      new TextRun({ text: "        ", size: 16 }),
      new TextRun({ text: config.footerLeft, size: 16, color: P.footerColor, font: FONT }),
    ],
  }));

  // single 16838 wrapper table — the ONLY table on the cover
  return [new Table({
    width: { size: 100, type: WidthType.PERCENTAGE },
    layout: TableLayoutType.FIXED,
    borders: allNoBorders,
    visuallyRightToLeft: true,
    rows: [new TableRow({
      height: { value: 16838, rule: "exact" },
      children: [new TableCell({
        shading: { type: ShadingType.CLEAR, fill: P.bg },
        borders: noBorders,
        margins: { left: 0, right: 0 },
        children,
      })],
    })],
  })];
}

// ---------------------------------------------------------------- content mapping
function renderSection(sec) {
  const out = [faH1(sec.h1)];
  for (const b of sec.blocks || []) {
    if (b.p) out.push(faP(b.p));
    else if (b.h2) out.push(faH2(b.h2));
    else if (b.table) out.push(...mkTable(b.table));
  }
  return out;
}

// ---------------------------------------------------------------- headers/footers
function pageHeader() {
  return new Header({
    children: [new Paragraph({
      bidirectional: true,
      alignment: AlignmentType.START,
      spacing: { after: 60, line: 240 },
      border: { bottom: { style: BorderStyle.SINGLE, size: 2, color: "C9D2DC", space: 4 } },
      children: [rtl("گزارش بررسی فنی سامانه داوری کراس‌فیت — نسخه ۱٫۰", { size: 18, color: "808080" })],
    })],
  });
}

function pageNumFooter() {
  return new Footer({
    children: [new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { line: 240 },
      children: [new TextRun({ children: [PageNumber.CURRENT], size: 18, color: "808080", font: FONT })],
    })],
  });
}

// ---------------------------------------------------------------- assemble document
const coverCfg = {
  title: C1.cover.title.join(" "),
  subtitle: C1.cover.subtitle,
  englishLabel: C1.cover.englishLabel,
  metaLines: C1.cover.metaLines,
  footerLeft: C1.cover.footerLeft,
  footerRight: C1.cover.footerRight,
};

const bodyChildren = [
  ...renderSection(C1.sec1),
  ...renderSection(C1.sec2),
  ...renderSection(C1.sec3),
  ...renderSection(C1.sec4),
  ...renderSection(C2.sec5),
  ...renderSection(C2.sec6),
  ...renderSection(C2.sec7),
  ...renderSection(C2.sec8),
  ...renderSection(C2.sec9),
  ...renderSection(C2.sec10),
  ...renderSection(C2.appendixA),
  ...renderSection(C2.appendixB),
];

const pgSize = { width: 11906, height: 16838 };
const pgMargin = { top: 1440, bottom: 1440, left: 1560, right: 1560 };

const doc = new Document({
  styles: {
    default: {
      document: {
        run: { font: FONT, size: 24, color: PAL.body },
        paragraph: { spacing: { line: 312 } },
      },
      heading1: {
        run: { font: FONT, size: 32, bold: true, color: PAL.primary },
        paragraph: { spacing: { before: 420, after: 200, line: 380 } },
      },
      heading2: {
        run: { font: FONT, size: 27, bold: true, color: PAL.primary },
        paragraph: { spacing: { before: 300, after: 150, line: 340 } },
      },
      heading3: {
        run: { font: FONT, size: 24, bold: true, color: PAL.primary },
        paragraph: { spacing: { before: 240, after: 120, line: 320 } },
      },
    },
  },
  sections: [
    // -------- Section 1: cover (margin 0, no footer, no page number)
    {
      properties: {
        page: { size: pgSize, margin: { top: 0, bottom: 0, left: 0, right: 0 } },
      },
      children: buildCoverR1RTL(coverCfg),
    },
    // -------- Section 2: front matter (TOC) — no page number on TOC page
    {
      properties: {
        type: SectionType.NEXT_PAGE,
        page: { size: pgSize, margin: pgMargin },
      },
      headers: { default: pageHeader() },
      children: [
        new Paragraph({
          bidirectional: true,
          alignment: AlignmentType.CENTER,
          spacing: { before: 480, after: 360, line: 400, lineRule: "atLeast" },
          children: [rtl("فهرست مطالب", { size: 32, bold: true, color: PAL.primary })],
        }),
        new TableOfContents("Table of Contents", {
          hyperlink: true,
          headingStyleRange: "1-2",
        }),
        new Paragraph({
          bidirectional: true,
          alignment: AlignmentType.START,
          spacing: { before: 240, line: 280 },
          children: [rtl(
            "یادآوری: این فهرست با کد فیلد تولید شده است؛ پس از باز کردن سند در ورد، برای به‌روزرسانی شماره صفحه‌ها روی فهرست راست‌کلیک کرده و گزینه به‌روزرسانی فیلد را برگزینید.",
            { size: 18, italics: true, color: "888888" },
          )],
        }),
      ],
    },
    // -------- Section 3: body — Arabic page numbers starting at 1
    {
      properties: {
        type: SectionType.NEXT_PAGE,
        page: {
          size: pgSize, margin: pgMargin,
          pageNumbers: { start: 1, formatType: NumberFormat.DECIMAL },
        },
      },
      headers: { default: pageHeader() },
      footers: { default: pageNumFooter() },
      children: bodyChildren,
    },
  ],
});

const OUT = "/home/z/my-project/download/CrossFit-Judge-v1-Code-Review-Report-FA.docx";
Packer.toBuffer(doc).then((buf) => {
  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  fs.writeFileSync(OUT, buf);
  console.log("WROTE", OUT, buf.length, "bytes");
});
