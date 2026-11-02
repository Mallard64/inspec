// Take: pick a defective Screw Bag (two short screws, no long one) and watch Inspec reject it,
// with the masks and the reasons. Uses cached model answers, so the clip is smooth; the live
// model calls are shown in the submission video instead.
//
//   .venv/bin/streamlit run app.py --server.port 8599 --server.headless true
//   node videos/record.mjs --take videos/demos/inspect-kit.mjs --out out/social/inspect-kit

export const url = "http://localhost:8599/?kit=Screw%20Bag";

// Presentation only: hide Streamlit's own toolbar ("Deploy", the running indicator).
export const css = `[data-testid="stHeader"], [data-testid="stToolbar"] { display: none !important; }`;

// Streamlit's selectbox is a React Aria combobox: a text input plus an "Open" chevron button.
const select = (label, part = "[role=group]") => `[...document.querySelectorAll('[data-testid=stSelectbox]')]
  .find((e) => e.innerText.trim().startsWith(${JSON.stringify(label)}))?.querySelector(${JSON.stringify(part)})`;
const option = (prefix) => `[...document.querySelectorAll('[role=option]')]
  .find((e) => e.innerText.trim().startsWith(${JSON.stringify(prefix)}))`;
const heading = (text) => `[...document.querySelectorAll('h2')].find((e) => e.innerText.includes(${JSON.stringify(text)}))`;
const alert = (text) => `[...document.querySelectorAll('[data-testid=stAlert]')].find((e) => e.innerText.includes(${JSON.stringify(text)}))`;
const idle = `document.querySelector('[data-testid=stApp]')?.dataset.testScriptState !== 'running'`;

async function scrollTo(t, expr, top = 24, ms = 900) {
  const b = await t.box(expr);
  await t.wheel(b.y - top, { ms });
}

export async function still(t) {
  await scrollTo(t, heading("Inspect a kit"), 24, 300);
}

export default async function take(t) {
  await t.moveTo(t.width * 0.62, t.height * 0.42, { ms: 200 });
  await t.hold(700);                                             // the packing list and its checks
  await scrollTo(t, heading("Inspect a kit"));
  await t.hold(300);

  await t.clickOn(select("Show me", "button[aria-label=Open]"));
  await t.hold(250);
  await t.clickOn(option("Wrong parts or amounts"), { fx: 0.3 });
  await t.waitFor(`${idle} && (${alert("Reject")}) && !(${alert("Pass")})`);   // not the stale Pass
  await t.hold(400);

  await t.clickOn(select("Image", "input"), { fx: 0.3 });
  await t.type("029", { perChar: 140 });
  await t.hold(250);
  await t.clickOn(option("029"), { fx: 0.3 });
  await t.waitFor(`(${select("Image", "input")})?.value.startsWith('029') && ${idle} && (${alert("Reject")})`);
  await t.hold(500);

  await scrollTo(t, alert("Reject"), 16, 800);                   // verdict, masks and checks in one view
  await t.hover(alert("Reject"), { fx: 0.28, fy: 0.66, dwell: 1300 });         // the reasons
  t.poster();
  await t.hover(`[...document.querySelectorAll('[data-testid=stImage] img')][1]`, { fx: 0.5, fy: 0.4, dwell: 1300 });
  await t.hover(`[...document.querySelectorAll('[data-testid=stMarkdownContainer] p')].find((e) => e.innerText.includes('short screw: found 2'))`,
    { fx: 0.3, dwell: 1300 });                                                 // the failed count
  await t.moveTo(t.width * 0.7, t.height * 0.55, { ms: 700 });
  await t.hold(900);
}
