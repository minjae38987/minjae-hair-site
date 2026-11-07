/* Booking click measurement adapter. No external tracking or network calls by itself.
   If GA4 is configured later, reports an event using the existing gtag instance.
   Navigation is never prevented or delayed; no personal data is collected here. */
(() => {
  const bookingHost = 'm.booking.naver.com';
  const eventName = 'naver_booking_click';
  const identify = (anchor) => {
    try {
      const target = new URL(anchor.href, document.baseURI);
      if (target.hostname !== bookingHost || !target.pathname.startsWith('/booking/')) return null;
      return target;
    } catch (_) { return null; }
  };
  document.addEventListener('click', (event) => {
    const anchor = event.target?.closest?.('a[href]');
    if (!anchor || !identify(anchor)) return;
    const element = anchor.closest('.mobile-booking-cta') ? 'mobile_sticky' :
      anchor.closest('nav, header') ? 'header' :
      anchor.closest('.cta, #visit') ? 'content_cta' : 'other';
    const data = {
      page_path: window.location.pathname,
      booking_button_location: element
    };
    // Useful for debugging, first-party dashboards, and later analytics adapters.
    document.dispatchEvent(new CustomEvent(eventName, { detail: data }));
    if (typeof window.gtag === 'function') {
      window.gtag('event', eventName, data);
    }
  }, { passive: true });
})();
