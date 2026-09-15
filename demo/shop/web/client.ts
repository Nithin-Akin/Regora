export interface CheckoutItem {
  price: number;
  quantity: number;
}

export class ApiClient {
  async checkout(items: CheckoutItem[], paymentMethod: string) {
    return fetch('/checkout', {
      method: 'POST',
      body: JSON.stringify({ items, payment_method: paymentMethod }),
      headers: { 'Content-Type': 'application/json' },
    });
  }

  async profile() {
    return fetch('/profile');
  }
}
