export function trackCheckout(orderId) {
  console.info('checkout.completed', orderId);
}

export function onCheckoutComplete(receipt) {
  trackCheckout(receipt.id);
}
