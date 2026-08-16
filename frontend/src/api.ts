// Talks to POST /orders on the order-api service. Base URL is configurable so
// local dev (vite dev server, different origin) can point at a reachable
// host, while the in-cluster build defaults to "" (same-origin, proxied by
// nginx — see frontend/nginx.conf) and needs no CORS handling at all.
const API_BASE = import.meta.env.VITE_API_BASE ?? "";

export interface OrderRequest {
  customer: string;
  sku: string;
  quantity: number;
  amount_cents: number;
}

export interface OrderResponse {
  order_id: string;
  status: string;
  s3_key: string;
  total_amount_cents: number;
  discount_cents: number;
  // Both are free-form strings on the wire (shop.v1.PriceOrderResponse) —
  // nothing on this side enforces a two-value union, and treating them as
  // one is what let an unrecognized value get silently folded into "v2" in
  // the tally. Display them as whatever the backend actually sent.
  rule_applied: string;
  priced_by: string;
}

export class OrderApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "OrderApiError";
  }
}

export async function placeOrder(req: OrderRequest): Promise<OrderResponse> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/orders`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(req),
    });
  } catch (err) {
    // Network failure (service unreachable, DNS, etc) — no HTTP status at all.
    throw new OrderApiError(
      err instanceof Error ? err.message : "network error",
      0,
    );
  }

  if (!res.ok) {
    throw new OrderApiError(`order-api returned ${res.status}`, res.status);
  }

  return (await res.json()) as OrderResponse;
}
