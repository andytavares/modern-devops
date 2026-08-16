import { placeOrder, OrderApiError, type OrderResponse } from "./api";
import { recordPriced, totalOf, percentOf, colorFor } from "./tally";

interface LogEntry {
  quantity: number;
  totalCents: number | null;
  ruleApplied: string;
  pricedBy: string;
  ok: boolean;
}

interface State {
  counts: Map<string, number>;
  errors: number;
  log: LogEntry[];
}

const MAX_LOG = 20;
const CONTINUOUS_INTERVAL_MS = 500; // 2/sec

const state: State = { counts: new Map(), errors: 0, log: [] };
// Colour assignment persists independently of `state` so a version keeps its
// colour across a render even if it briefly has zero share; reset explicitly
// clears it alongside the counts so a fresh session reassigns from scratch.
let colors = new Map<string, string>();

let continuousTimer: ReturnType<typeof setInterval> | null = null;

const app = document.querySelector<HTMLDivElement>("#app");
if (!app) {
  throw new Error("#app element not found");
}

app.innerHTML = `
  <main>
    <header>
      <h1>Canary Watch</h1>
      <p class="subtitle">Live split of <code>pricing</code> versions, by order.</p>
    </header>

    <section class="tally" aria-label="live version split">
      <div class="tally-bar" id="tally-bar"></div>
      <div class="tally-labels" id="tally-labels"></div>
      <div class="tally-meta">
        <span id="version-count-label"></span>
        <span class="tally-label errors"><strong id="err-count">0</strong> failed (502)</span>
      </div>
    </section>

    <section class="controls">
      <div class="field">
        <label for="quantity">Quantity</label>
        <input type="number" id="quantity" min="1" step="1" value="1" />
      </div>
      <div class="field">
        <label for="amount">Unit amount ($)</label>
        <input type="number" id="amount" min="0" step="0.01" value="19.99" />
      </div>
      <div class="buttons">
        <button id="send-one" type="button">Send order</button>
        <button id="send-twenty" type="button">Send 20 orders</button>
        <button id="toggle-continuous" type="button">Start continuous (2/sec)</button>
        <button id="reset" type="button" class="secondary">Reset counters</button>
      </div>
      <p class="hint">Quantity &ge; 3 crosses the bulk-discount boundary that triggers v2's <code>bulk-10pct</code> rule.</p>
    </section>

    <section class="log-section">
      <h2>Last ${MAX_LOG} orders</h2>
      <table class="log">
        <thead>
          <tr>
            <th>#</th>
            <th>qty</th>
            <th>total</th>
            <th>rule</th>
            <th>priced by</th>
          </tr>
        </thead>
        <tbody id="log-body"></tbody>
      </table>
    </section>
  </main>
`;

const el = <T extends HTMLElement>(id: string): T => {
  const found = document.getElementById(id);
  if (!found) throw new Error(`missing #${id}`);
  return found as T;
};

const quantityInput = el<HTMLInputElement>("quantity");
const amountInput = el<HTMLInputElement>("amount");
const sendOneBtn = el<HTMLButtonElement>("send-one");
const sendTwentyBtn = el<HTMLButtonElement>("send-twenty");
const toggleContinuousBtn = el<HTMLButtonElement>("toggle-continuous");
const resetBtn = el<HTMLButtonElement>("reset");

const tallyBar = el<HTMLDivElement>("tally-bar");
const tallyLabels = el<HTMLDivElement>("tally-labels");
const versionCountLabel = el<HTMLElement>("version-count-label");
const errCountEl = el<HTMLElement>("err-count");
const logBody = el<HTMLTableSectionElement>("log-body");

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function render(): void {
  const total = totalOf(state.counts);
  const keys = [...state.counts.keys()];

  // One bar segment + one label per distinct version actually seen. An
  // unexpected priced_by value gets its own segment, not a fold into v2.
  tallyBar.innerHTML = keys
    .map((key) => {
      const pct = total === 0 ? 0 : percentOf(state.counts, key);
      const width = total === 0 ? 100 / Math.max(keys.length, 1) : pct;
      return `<div class="tally-segment" style="width:${width}%;background:${colorFor(key, colors)}"></div>`;
    })
    .join("");

  tallyLabels.innerHTML = keys
    .map((key) => {
      const pct = percentOf(state.counts, key);
      const count = state.counts.get(key) ?? 0;
      return `<span class="tally-label" style="color:${colorFor(key, colors)}">
        <strong>${count}</strong> ${escapeHtml(key)} (${pct}%)
      </span>`;
    })
    .join("");

  versionCountLabel.textContent =
    keys.length === 0 ? "no orders yet" : `${keys.length} version${keys.length === 1 ? "" : "s"} seen`;

  errCountEl.textContent = String(state.errors);

  logBody.innerHTML = state.log
    .map((entry, i) => {
      const rowClass = entry.ok ? "" : "row-error";
      const totalDisplay =
        entry.totalCents === null ? "—" : `$${(entry.totalCents / 100).toFixed(2)}`;
      const priced = entry.ok
        ? `<span class="badge" style="background:${colorFor(entry.pricedBy, colors)}22;color:${colorFor(entry.pricedBy, colors)}">${escapeHtml(entry.pricedBy)}</span>`
        : `<span class="badge error">502</span>`;
      return `<tr class="${rowClass}">
        <td>${state.log.length - i}</td>
        <td>${entry.quantity}</td>
        <td>${totalDisplay}</td>
        <td>${escapeHtml(entry.ruleApplied)}</td>
        <td>${priced}</td>
      </tr>`;
    })
    .join("");
}

function pushLog(entry: LogEntry): void {
  state.log.unshift(entry);
  if (state.log.length > MAX_LOG) {
    state.log.length = MAX_LOG;
  }
}

async function sendOrder(): Promise<void> {
  const quantity = Math.max(1, Math.trunc(quantityInput.valueAsNumber || 1));
  const amountDollars = amountInput.valueAsNumber || 0;
  const amountCents = Math.round(amountDollars * 100);

  try {
    const res: OrderResponse = await placeOrder({
      customer: "ada",
      sku: "WIDGET-1",
      quantity,
      amount_cents: amountCents,
    });

    recordPriced(state.counts, res.priced_by);

    pushLog({
      quantity,
      totalCents: res.total_amount_cents,
      ruleApplied: res.rule_applied,
      pricedBy: res.priced_by,
      ok: true,
    });
  } catch (err) {
    state.errors += 1;
    const status = err instanceof OrderApiError ? err.status : 0;
    pushLog({
      quantity,
      totalCents: null,
      ruleApplied: status === 0 ? "network error" : `HTTP ${status}`,
      pricedBy: "—",
      ok: false,
    });
  } finally {
    render();
  }
}

function sendMany(count: number): void {
  for (let i = 0; i < count; i++) {
    void sendOrder();
  }
}

function stopContinuous(): void {
  if (continuousTimer !== null) {
    clearInterval(continuousTimer);
    continuousTimer = null;
  }
  toggleContinuousBtn.textContent = "Start continuous (2/sec)";
  toggleContinuousBtn.classList.remove("active");
}

function startContinuous(): void {
  toggleContinuousBtn.textContent = "Stop continuous";
  toggleContinuousBtn.classList.add("active");
  continuousTimer = setInterval(() => {
    void sendOrder();
  }, CONTINUOUS_INTERVAL_MS);
}

sendOneBtn.addEventListener("click", () => void sendOrder());
sendTwentyBtn.addEventListener("click", () => sendMany(20));
toggleContinuousBtn.addEventListener("click", () => {
  if (continuousTimer === null) {
    startContinuous();
  } else {
    stopContinuous();
  }
});
resetBtn.addEventListener("click", () => {
  state.counts = new Map();
  state.errors = 0;
  state.log = [];
  colors = new Map();
  render();
});

render();
