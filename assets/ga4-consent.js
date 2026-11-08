/* GA4 initialization with explicit, revocable analytics opt-in.
   Nonessential Google Analytics scripts are not loaded unless accepted.
   No personal details are included in custom booking-click event parameters. */
(() => {
  'use strict';
  const measurementId = 'G-ZZWKEPMY3W';
  const key = 'minjae_analytics_choice_v1';
  const styleId = 'analytics-choice-styles';
  const getChoice = () => {
    try { return localStorage.getItem(key); } catch (_) { return null; }
  };
  const saveChoice = (value) => {
    try { localStorage.setItem(key, value); } catch (_) {}
  };
  const clearChoice = () => {
    try { localStorage.removeItem(key); } catch (_) {}
  };
  const loadGA = () => {
    if (window.__minjaeGaLoaded) return;
    window.__minjaeGaLoaded = true;
    window.dataLayer = window.dataLayer || [];
    window.gtag = function () { window.dataLayer.push(arguments); };
    window.gtag('js', new Date());
    window.gtag('config', measurementId, { send_page_view: true });
    const script = document.createElement('script');
    script.async = true;
    script.src = 'https://www.googletagmanager.com/gtag/js?id=' + encodeURIComponent(measurementId);
    document.head.appendChild(script);
  };
  const sheet = document.createElement('style');
  sheet.id = styleId;
  sheet.textContent = [
    '.analytics-choice{position:fixed;left:12px;right:12px;bottom:calc(88px + env(safe-area-inset-bottom,0px));z-index:1100;max-width:560px;margin:auto;background:#f8f7f4;color:#222;box-shadow:0 8px 35px #0003;border:1px solid #ccc6bb;border-radius:8px;padding:15px;font:14px/1.55 Arial,"Noto Sans KR",sans-serif}',
    '.analytics-choice p{margin:0 0 10px;color:#333;font-size:13px;line-height:1.55}',
    '.analytics-choice strong{display:block;margin-bottom:5px;color:#222;font-size:14px}',
    '.analytics-choice-actions{display:flex;gap:9px}',
    '.analytics-choice button{border-radius:5px;border:1px solid #8a8a85;background:#fff;color:#202322;padding:8px 12px;cursor:pointer;flex:1;font:inherit;font-weight:700}',
    '.analytics-choice button[data-accept]{background:#202626;color:#fff;border-color:#202626}',
    '.analytics-settings{display:block;background:transparent;border:0;text-decoration:underline;cursor:pointer;color:inherit;font:inherit;padding:5px 0;margin:6px 0 0}',
    '@media(min-width:701px){.analytics-choice{bottom:20px}}'
  ].join('');
  document.head.appendChild(sheet);
  const banner = document.createElement('div');
  banner.className = 'analytics-choice';
  banner.setAttribute('role', 'region');
  banner.setAttribute('aria-label', '방문 통계 선택');
  banner.innerHTML = '<strong>방문 통계 수집 선택</strong>' +
    '<p>사이트 개선을 위해 Google Analytics로 방문 페이지와 예약 버튼 클릭을 측정합니다. 선택하지 않아도 예약과 사이트 이용에 제한이 없습니다. 동의하면 Google에 관련 이용 정보가 전송될 수 있습니다.</p>' +
    '<div class="analytics-choice-actions"><button type="button" data-reject>동의하지 않음</button><button type="button" data-accept>통계 수집 동의</button></div>';
  const settings = document.createElement('button');
  settings.type = 'button';
  settings.className = 'analytics-settings';
  settings.textContent = '방문 통계 설정';
  settings.setAttribute('aria-label', '방문 통계 수집 설정 변경');
  settings.addEventListener('click', () => { banner.hidden = false; });
  // Footer is present on all four static pages.
  (document.querySelector('footer') || document.body).appendChild(settings);
  document.body.appendChild(banner);
  const choice = getChoice();
  if (choice === 'yes') {
    banner.hidden = true;
    loadGA();
  } else if (choice === 'no') {
    banner.hidden = true;
  }
  banner.querySelector('[data-accept]').addEventListener('click', () => {
    saveChoice('yes');
    banner.hidden = true;
    loadGA();
  });
  banner.querySelector('[data-reject]').addEventListener('click', () => {
    saveChoice('no');
    banner.hidden = true;
    // GA4 has already been loaded in this tab when consent is revoked;
    // immediately disable additional GA collection and reload to stop the tag.
    window['ga-disable-' + measurementId] = true;
    if (window.__minjaeGaLoaded) window.location.reload();
  });
})();
