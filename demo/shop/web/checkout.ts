import { ApiClient as ShopClient } from './client';
import type { CheckoutItem } from './client';

const client = new ShopClient();

export async function submitCheckout(items: CheckoutItem[], method: string) {
  return client.checkout(items, method);
}

export function basketCount(items: CheckoutItem[]): number {
  return items.reduce((count, item) => count + item.quantity, 0);
}
