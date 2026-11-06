// Runs the dashboard page's logic without a browser, on synthetic data:
//   node dashboard_smoke.js [generated dashboard.html] [extra .xlsx or .csv file]
// Every tab must render, without "undefined" or "NaN", and sheet text must be escaped.
const fs = require("fs"), path = require("path"), vm = require("vm"), assert = require("assert");
const assets = path.join(__dirname, "..", "dashboard_assets");
const htmlArg = process.argv[2] && process.argv[2] !== "-" ? process.argv[2] : null, extra = process.argv[3];
const page = fs.readFileSync(htmlArg || path.join(assets, "template.html"), "utf8");
const app = page.split('<script id="app">')[1].split("</script>")[0];
const sandbox = { console, TextDecoder, Uint8Array, ArrayBuffer };
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(path.join(assets, "xlsx.full.min.js"), "utf8"), sandbox);
vm.runInContext(app, sandbox);
const D = sandbox.ImageHubDashboard;

function checkAll(label) {
  for (const [tab] of D.TABS) {
    const html = D.renderTab(tab);
    assert.ok(html.length > 50, `${label}/${tab} empty`);
    assert.ok(!/\bundefined\b/.test(html), `${label}/${tab} has undefined: ${html.match(/.{60}undefined.{40}/)}`);
    assert.ok(!/\bNaN\b/.test(html), `${label}/${tab} has NaN: ${html.match(/.{60}NaN.{40}/)}`);
  }
}
// As export.dashboard_layout makes it from datasets/spheroid_example.yaml
// (test_dashboard.py checks that they agree).
const LAYOUT = JSON.parse(fs.readFileSync(path.join(__dirname, "golden", "dashboard_layout.golden"), "utf8"));
const COLUMNS = ["image_file", "original_name", "experiment", "vid", "well", "field", "timepoint_minutes", "day", "channel", "channel_norm", "variant", "match_status", "regions_AA", "regions_unknown", "regions_total", "treatment_raw", "treatment_norm", "concentration", "concentration_unit", "stimulation", "stimulation_norm", "tissue", "Viability (%)", "Target", "Sex", "well_note", "file_status"];
const row = (name, exp, vid, well, min, regAA, regU, treat, conc, unit, viab, sex) => [`images/${name}`, name, exp, vid, well, "1", min, String(min / 1440), "jpg", "jpg", "", "matched", regAA, regU, regAA === "" && regU === "" ? "" : String(+regAA + +regU), treat, treat, conc, unit, "unstimulated", "unstimulated", "PB", viab, "BTK", sex, "", "included"];
const rows = [
  row("a1_0.jpg", "Exp A", "1", "A1", 0, "", "", "ibrutinib", "10", "nM", "80", "male"),
  row("a1_1.jpg", "Exp A", "1", "A1", 1440, "4", "1", "ibrutinib", "10", "nM", "80", "male"),
  row("a2_1.jpg", "Exp A", "1", "A2", 1440, "0", "3", "venetoclax;S-63845", "1;2", "nM", "72.5", "female"),
  row("b1_2.jpg", "Exp B", "2", "B1", 2880, "7", "", "<img src=x onerror=alert(1)>", "5", "ng/mL", "not done", "<b>x</b>"),
  row("b2_2.jpg", "Exp B", "2", "B2", 2880, "", "", "<img src=x onerror=alert(1)>", "5", "ng/mL", "60", "male"),
];
const images = { "images/a1_1.jpg": { src: "data:image/jpeg;base64,AA==", w: 1536, h: 1152 }, "images/a2_1.jpg": { src: "data:image/jpeg;base64,AA==", w: 1536, h: 1152 } };
const annotations = { "images/a1_1.jpg": [
  { label: "AA", shapes: [["ellipse", { cx: 10, cy: 20, rx: 3, ry: 4 }], ["polygon", { points: "1,2 3,4 5,6" }]] },
  { label: "unknown", shapes: [["ellipse", { cx: 9, cy: 9, rx: 3, ry: 4, transform: "rotate(10 9 9)" }]] },
] };

// 1. As made by the plugin.
D.load({ columns: COLUMNS, rows, images, annotations, wells_without_images: [{ experiment: "Exp A", vid: "1", well: "H9" }], info: { created: "now", filter: "{}" }, name: "Synthetic", layout: LAYOUT });
checkAll("full");
assert.deepStrictEqual(D.S.data.wells.length, 4, "wells are grouped");
assert.ok(D.S.data.numeric.includes("Viability (%)"));
assert.ok(!D.S.data.numeric.includes("vid") && !D.S.data.numeric.includes("well"));
assert.ok(D.S.data.categorical.includes("treatment_norm"));
let html = D.renderTab("images");
assert.ok(/<ellipse/.test(html) && /<polygon/.test(html) && /viewBox="0 0 1536 1152"/.test(html), "overlay in image pixels");
assert.ok(/transform="rotate\(10 9 9\)"/.test(html));
html = D.renderTab("flow");
assert.ok(/<circle/.test(html) && /median/.test(html), "dots and median");
assert.ok(/1 wells left out/.test(html), "non-numeric value is reported");
assert.ok(!/<img src=x/.test(html) && /&lt;img src=x/.test(html), "treatment text is escaped");
html = D.renderTab("time");
assert.ok(/<path d="M/.test(html), "line of regions over time");
assert.strictEqual(D.defaultRegionColumn(), "regions_AA");
assert.ok(/<option value="regions_AA" selected>/.test(html), "regions_AA is the default Y");
assert.ok(/regions_total adds annotators together/.test(html), "note on the time series");
{
  const scatter = D.renderTab("scatter");
  assert.ok(/data-ui="scatterX"><option value="[^"]*"[^>]*>[\s\S]*?<option value="regions_AA" selected>/.test(scatter), "regions_AA is the default X");
  assert.ok(/regions_total adds annotators together/.test(scatter), "note on the scatter");
  const flow = D.renderTab("flow");
  assert.ok(/data-ui="flowColour"[\s\S]*?<option value="concentration"/.test(flow), "colour by concentration is offered");
  D.S.ui.flowColour = "concentration";
  const coloured = D.renderTab("flow");
  assert.ok(/concentration: 10 nM/.test(coloured) && /10 nM<\/span>/.test(coloured), "colour and legend carry the unit");
  assert.ok(/5 ng\/mL/.test(coloured), "another unit stays apart");
  assert.ok(!/\bundefined\b|\bNaN\b/.test(coloured));
  D.S.ui = {};
}
// Series that end at the same value: labels stay apart and inside the plot.
{
  const placed = D.dodgeLabels([100, 100, 100, 100], 15, 16, 408);
  [...placed].sort((a, b) => a - b).forEach((y, i, all) => { if (i) assert.ok(y - all[i - 1] >= 15, "gap"); });
  assert.deepStrictEqual(Array.from(D.dodgeLabels([20, 200, 400], 15, 16, 408)), [20, 200, 400], "labels that fit do not move");
  const low = D.dodgeLabels([405, 406, 407], 15, 16, 408);
  assert.ok(Math.max(...low) <= 408 && Math.min(...low) >= 16, "inside the plot at the bottom");
  const top = D.dodgeLabels([1, 2, 3], 15, 16, 408);
  assert.ok(Math.min(...top) >= 16, "inside the plot at the top");
  D.load({ columns: ["experiment", "vid", "well", "timepoint_minutes", "regions_AA", "treatment_norm"], rows: ["a", "b", "c", "d"].flatMap(t => [["E", "1", t + "1", "0", "1", t], ["E", "1", t + "1", "1440", "5", t]]), name: "same end", layout: LAYOUT });
  const lines = D.renderTab("time");
  const ys = [...lines.matchAll(/<text x="\d+(?:\.\d+)?" y="([\d.]+)" data-tip="[abcd]">/g)].map(m => +m[1]).sort((a, b) => a - b);
  assert.strictEqual(ys.length, 4, "four labels");
  assert.strictEqual(D.LABEL_GAP, 18);
  ys.forEach((y, i) => { if (i) assert.ok(y - ys[i - 1] >= D.LABEL_GAP, "rendered labels keep clear space"); });
  D.load({ columns: COLUMNS, rows, images, annotations, wells_without_images: [], info: {}, name: "Synthetic", layout: LAYOUT });
  // Only a total in the file: that is the default, there is nothing else.
  D.load({ columns: ["regions_total", "timepoint_minutes"], rows: [["3", "0"]], name: "t" });
  assert.strictEqual(D.defaultRegionColumn(), "regions_total");
  D.load({ columns: ["regions_total", "regions_BB", "timepoint_minutes"], rows: [["3", "3", "0"]], name: "t" });
  assert.strictEqual(D.defaultRegionColumn(), "regions_BB", "first annotator without AA");
  D.load({ columns: COLUMNS, rows, images, annotations, wells_without_images: [{ experiment: "Exp A", vid: "1", well: "H9" }], info: { created: "now", filter: "{}" }, name: "Synthetic", layout: LAYOUT });
}
html = D.renderTab("time");
html = D.renderTab("scatter");
assert.ok(/<circle/.test(html) && /data-key="Exp A\|1\|A1"/.test(html), "points are clickable");
html = D.renderTab("annot");
assert.ok(/AA: images \/ regions \/ with 0/.test(html) && /2 \/ 4 \/ 1/.test(html), "per annotator with zeros");
html = D.renderTab("overview");
assert.ok(/✓ found/.test(html) && /Wells without images/.test(html), "data check");
assert.ok(/<b>x<\/b>/.test(html) === false, "well text escaped");

// A picked well shows its images; a filter does not repaint a value.
D.S.picked = "Exp A|1|A1";
assert.ok(/1 images with a thumbnail, of 2/.test(D.renderTab("scatter")));
D.S.picked = null;
const before = D.colourMap("treatment_norm").get("ibrutinib");
D.S.ui.flowColour = "treatment_norm"; D.renderTab("flow");
assert.strictEqual(D.colourMap("treatment_norm").get("ibrutinib"), before);
D.S.ui = {};

// 2. Opened by hand: a csv with awkward text, no thumbnails.
const csv = COLUMNS.join(",").replace('"', "") + "\n" + rows.map(r => r.map(c => /[,;<]/.test(c) ? `"${c}"` : c).join(",")).join("\n") + "\nx,y,E,3,C3,1,0,0,jpg,jpg,,matched,,,,µ-drug,µ-drug,1000;3000,µg/mL,,,,2011-06-08,,,,\n";
const fromCsv = D.readBytes("metadata.csv", new TextEncoder().encode(csv).buffer);
D.load({ ...fromCsv, name: "metadata.csv", layout: LAYOUT });
checkAll("csv");
const last = D.S.data.rows[D.S.data.rows.length - 1];
assert.strictEqual(last.treatment_norm, "µ-drug", "utf-8 survives");
assert.strictEqual(last.concentration, "1000;3000", "combination stays text");
assert.strictEqual(last["Viability (%)"], "2011-06-08", "a date stays as written");
assert.ok(/no thumbnails/.test(D.renderTab("images")));
assert.ok(/only known in a dashboard made by the plugin/.test(D.renderTab("overview")));

// 3. A file without the expected columns must not break any tab.
D.load({ columns: ["a", "b"], rows: [["1", "x"], ["2", "y"]], name: "other", layout: LAYOUT });
checkAll("other");
assert.ok(/✕ missing/.test(D.renderTab("overview")));
D.load({ columns: ["experiment", "vid", "well"], rows: [["E", "1", "A1"]], name: "bare", layout: LAYOUT });
checkAll("bare");
assert.strictEqual(D.tabLabel(D.TABS[3]), "Flow endpoints", "the config names a tab");

// Without a layout (a bare page): every row is its own sample, nothing is assumed.
D.load({ columns: COLUMNS, rows, images, annotations, name: "no layout" });
checkAll("no layout");
assert.strictEqual(D.S.data.wells.length, rows.length, "one sample per row");
assert.ok(!/Expected columns/.test(D.renderTab("overview")));
assert.strictEqual(D.tabLabel(D.TABS[3]), "Values per group");
assert.ok(/This dataset has no time column/.test(D.renderTab("time")));

// 4. Without any image-derived value: images per well over time.
const plain = COLUMNS.filter(c => !c.startsWith("regions_"));
const keep = COLUMNS.map((c, i) => (c.startsWith("regions_") ? -1 : i)).filter(i => i >= 0);
D.load({ columns: plain, rows: rows.map(r => keep.map(i => r[i])), name: "no regions", layout: LAYOUT });
checkAll("no regions");
assert.ok(/images per well/.test(D.renderTab("time")));

// 5. Optional: a generated dashboard and another file.
if (htmlArg) {
  const embedded = JSON.parse(page.split('id="embedded" type="application/json">')[1].split("</script>")[0]);
  D.load(embedded);
  checkAll("generated");
  const counts = {};
  for (const [tab] of D.TABS) counts[tab] = (D.renderTab(tab).match(/<(circle|ellipse|polygon|path|img)\b/g) || []).length;
  console.log("generated:", D.S.data.rows.length, "rows,", D.S.data.wells.length, "wells,", Object.keys(D.S.data.images).length, "thumbnails,", D.S.data.numeric.length, "numeric columns; marks per tab", JSON.stringify(counts));
}
if (extra) {
  const bytes = fs.readFileSync(extra);
  const table = D.readBytes(path.basename(extra), bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.length));
  D.load({ ...table, name: path.basename(extra) });
  checkAll("extra");
  console.log("extra file:", D.S.data.rows.length, "rows,", D.S.data.columns.length, "columns,", D.S.data.numeric.length, "numeric");
}
console.log("dashboard smoke: all checks passed");
