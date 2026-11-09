/* First-party booking intent tracking. Never blocks navigation.
   GA4 transmission only occurs after the consent module has initialized gtag.
   This event measures a click, NOT a completed Naver reservation. */
(() => {
  'use strict';
  const eventName = 'naver_booking_click';
  // QA marking is explicit and scoped to the current tab. It does NOT prove
  // that unmarked events came from real customers.
  const qaKey = 'minjae_analytics_qa_v1';
  const getTrafficValidationStatus = () => {
    try {
      const params = new URLSearchParams(window.location.search || '');
      if (params.get('analytics_qa') === '1') {
        window.sessionStorage?.setItem(qaKey, '1');
        return 'qa_marked';
      }
      if (params.get('analytics_qa') === '0') {
        window.sessionStorage?.removeItem(qaKey);
        return 'unclassified';
      }
      return window.sessionStorage?.getItem(qaKey) === '1' ? 'qa_marked' : 'unclassified';
    } catch (_) {
      return 'unclassified';
    }
  };
  const getBookingUrl = (anchor) => {
    try {
      const url = new URL(anchor.href, document.baseURI);
      if (url.hostname !== 'm.booking.naver.com' || !url.pathname.startsWith('/booking/')) return null;
      return url;
    } catch (_) { return null; }
  };
  const getLocation = (anchor) => {
    if (anchor.closest('.mobile-booking-cta')) return 'mobile_sticky';
    if (anchor.closest('header, nav')) return 'header';
    if (anchor.closest('#home, .hero')) return 'hero';
    if (anchor.closest('#visit, .contact, .cta')) return 'content_cta';
    if (anchor.closest('main, article, aside')) return 'article_cta';
    return 'other';
  };
  document.addEventListener('click', (event) => {
    const anchor = event.target && event.target.closest && event.target.closest('a[href]');
    if (!anchor || !getBookingUrl(anchor)) return;
    const data = {
      page_path: window.location.pathname,
      booking_button_location: getLocation(anchor),
      traffic_validation_status: getTrafficValidationStatus()
    };
    document.dispatchEvent(new CustomEvent(eventName, { detail: data }));
    // Refusal / revocation must never be bypassed by this module.
    if (window['ga-disable-G-HJ7ZN6WJWH'] === true) return;
    if (typeof window.gtag === 'function') window.gtag('event', eventName, data);
  }, { passive: true });
})();
