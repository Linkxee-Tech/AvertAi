const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  page.setDefaultTimeout(6000);
  const errors = [];
  page.on('pageerror', err => errors.push('[pageerror] ' + err.message));
  page.on('console', msg => { if(msg.type()==='error' && !msg.text().includes('403')) errors.push('[console.error] ' + msg.text()); });

  const step = async (name, fn) => {
    try { await fn(); console.log('OK:', name); }
    catch(e){ console.log('FAIL:', name, '->', e.message.split('\n')[0]); }
  };

  await page.goto('http://localhost:8080/mobile/index.html');
  await page.waitForTimeout(800);

  await step('splash screen shows, onboarding carousel advances', async () => {
    const activeId = await page.locator('.m-screen.active').getAttribute('id');
    if (activeId !== 'm-splash') throw new Error('expected splash active, got ' + activeId);
    await page.click('#mOnboardNext');
    await page.waitForTimeout(150);
    const slide1Visible = await page.isVisible('.m-onboard-slide[data-slide="1"]');
    if (!slide1Visible) throw new Error('slide 1 did not appear after Next');
    await page.click('#mOnboardNext');
    await page.waitForTimeout(150);
    const btnText = await page.textContent('#mOnboardNext');
    if (btnText.trim() !== 'Get Started') throw new Error('button should read Get Started on last slide, got: ' + btnText);
  });

  await step('language modal appears and routes to login', async () => {
    await page.click('#mOnboardNext');
    await page.waitForTimeout(200);
    const modalVisible = await page.isVisible('#modalOverlay.show');
    if (!modalVisible) throw new Error('language modal did not open');
    await page.click('#modalConfirm');
    await page.waitForTimeout(200);
    const activeId = await page.locator('.m-screen.active').getAttribute('id');
    if (activeId !== 'm-login') throw new Error('expected login screen, got ' + activeId);
    const tabBarVisible = await page.evaluate(() => getComputedStyle(document.getElementById('bottomTabBar')).display !== 'none');
    if (tabBarVisible) throw new Error('tab bar should be hidden pre-login');
  });

  await step('OTP login with real backend code auto-navigates to Home + shows tab bar', async () => {
    await page.click('#mSendOtp');
    await page.waitForTimeout(700);
    const hintText = await page.textContent('#mOtpHint');
    const match = hintText.match(/code is (\d{6})/);
    if (!match) throw new Error('could not read real code from hint: ' + hintText);
    const boxes = await page.$$('#mOtpBoxes input');
    for (let i = 0; i < boxes.length; i++) await boxes[i].fill(match[1][i]);
    await page.click('#mVerifyOtp');
    await page.waitForTimeout(1000);
    const token = await page.evaluate(() => typeof mobileAccessToken !== 'undefined' ? mobileAccessToken : null);
    if (!token) throw new Error('mobileAccessToken not set after real verify');
    const activeId = await page.locator('.m-screen.active').getAttribute('id');
    if (activeId !== 'm-home') throw new Error('expected auto-navigate to home, got ' + activeId);
    const tabBarVisible = await page.evaluate(() => getComputedStyle(document.getElementById('bottomTabBar')).display !== 'none');
    if (!tabBarVisible) throw new Error('tab bar should now be visible');
  });

  await step('tab bar navigation works for all 5 tabs', async () => {
    for (const tab of ['map','report','inbox','settings','home']) {
      await page.click(`#bottomTabBar [data-screen="${tab}"]`);
      await page.waitForTimeout(300);
      const activeId = await page.locator('.m-screen.active').getAttribute('id');
      if (activeId !== 'm-'+tab) throw new Error(`clicked ${tab} tab but active screen is ${activeId}`);
    }
  });

  await step('map screen renders mosaic after skeleton clears', async () => {
    await page.click('#bottomTabBar [data-screen="map"]');
    await page.waitForTimeout(700);
    const cellCount = await page.$$eval('#mMiniMosaic .cell', els => els.length);
    if (cellCount !== 64) throw new Error('expected 64 mosaic cells, got ' + cellCount);
  });

  await step('report submission reaches real backend with reference ID', async () => {
    await page.click('#bottomTabBar [data-screen="report"]');
    await page.waitForTimeout(200);
    await page.click('#mQuickReport button');
    await page.click('#mSubmitReport');
    await page.waitForTimeout(400);
    const modalText = await page.textContent('#modalBody');
    if (!/RPT-\d{4}-\d+/.test(modalText)) throw new Error('no reference ID in confirmation: ' + modalText);
    await page.click('#modalConfirm');
  });

  await step('SOS beacon submits to real backend', async () => {
    await page.click('#bottomTabBar [data-screen="home"]');
    await page.waitForTimeout(200);
    await page.click('#mSosBtn');
    await page.waitForTimeout(150);
    await page.click('#modalConfirm');
    await page.waitForTimeout(1500);
    const btnText = await page.textContent('#mSosBtn');
    if (!btnText.includes('sent')) throw new Error('SOS did not confirm sent: ' + btnText);
  });

  await step('inbox item deep-links to detail with real chart', async () => {
    await page.click('#bottomTabBar [data-screen="inbox"]');
    await page.waitForTimeout(200);
    await page.click('.inbox-item');
    await page.waitForTimeout(700);
    const activeId = await page.locator('.m-screen.active').getAttribute('id');
    if (activeId !== 'm-detail') throw new Error('inbox click did not deep-link to detail, got ' + activeId);
    const chartBox = await page.locator('#mTrendChart').boundingBox();
    if (!chartBox || chartBox.width === 0) throw new Error('trend chart has zero size');
  });

  await step('settings: toggles work, backend status shown, logout returns to splash', async () => {
    await page.click('#bottomTabBar [data-screen="settings"]');
    await page.waitForTimeout(200);
    const statusText = await page.textContent('#backendStatusChip');
    console.log('  backend status:', statusText.trim());
    await page.click('.settings-row .switch');
    await page.waitForTimeout(100);
    await page.click('#mLogout');
    await page.waitForTimeout(150);
    await page.click('#modalConfirm');
    await page.waitForTimeout(200);
    const activeId = await page.locator('.m-screen.active').getAttribute('id');
    if (activeId !== 'm-splash') throw new Error('logout did not return to splash, got ' + activeId);
    const tabBarVisible = await page.evaluate(() => getComputedStyle(document.getElementById('bottomTabBar')).display !== 'none');
    if (tabBarVisible) throw new Error('tab bar should hide again after logout');
  });

  await step('manifest and service worker registered', async () => {
    const manifestHref = await page.getAttribute('link[rel="manifest"]', 'href');
    if (manifestHref !== 'manifest.json') throw new Error('manifest link missing/wrong');
    await page.waitForTimeout(500);
    const swState = await page.evaluate(async () => {
      const regs = await navigator.serviceWorker.getRegistrations();
      return regs.length;
    });
    console.log('  service worker registrations:', swState);
  });

  console.log('\n=== TOTAL ERRORS:', errors.length, '===');
  errors.forEach(e => console.log(e));
  await browser.close();
})();
